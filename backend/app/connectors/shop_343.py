from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from ..config import settings


class ShopConnectorError(RuntimeError):
    """Safe, user-facing failure from the 343SHOP Worker connector."""


def _base_url() -> str:
    value = str(settings.shop_worker_url or "").strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ShopConnectorError("SHOP_WORKER_URL must be a trusted HTTPS URL.")
    host = parsed.hostname.lower()
    if not (host.endswith(".workers.dev") or host == "343shop.chugastan343.workers.dev"):
        raise ShopConnectorError("SHOP_WORKER_URL host is not an approved Cloudflare Worker host.")
    return value


def shop_connector_status() -> dict[str, Any]:
    """Expose connection readiness without revealing credentials."""
    return {
        "configured": True,
        "worker_url": _base_url() if settings.shop_worker_url else None,
        "owner_dashboard_configured": bool(settings.shop_owner_password),
        "marketplace_mcp_configured": bool(settings.shop_mcp_access_token or settings.shop_mcp_write_token),
        "catalogue_write_configured": bool(settings.shop_mcp_write_token),
        "mode": "CLOUDFLARE_WORKER_API",
        "note": (
            "Public catalogue and marketplace status can be read without owner login. "
            "Owner products, wallet ledger and partner applications require SHOP_OWNER_PASSWORD. "
            "The current 343SHOP Worker does not expose a database-backed customer orders API."
        ),
    }


async def _get_json(client: httpx.AsyncClient, base: str, path: str) -> dict[str, Any]:
    response = await client.get(base + path, headers={"Accept": "application/json"})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ShopConnectorError(f"343SHOP returned an invalid response for {path}.")
    return payload


async def _owner_dashboard_snapshot(
    client: httpx.AsyncClient,
    base: str,
) -> dict[str, Any]:
    password = str(settings.shop_owner_password or "")
    if not password:
        return {"status": "NOT_CONFIGURED", "message": "SHOP_OWNER_PASSWORD haijawekwa kwenye MR AI backend."}

    origin = base
    login = await client.post(
        base + "/api/admin/login",
        headers={"Origin": origin, "Accept": "application/json"},
        json={"password": password},
    )
    if login.status_code != 200:
        if login.status_code in {401, 403}:
            return {"status": "AUTH_FAILED", "message": "343SHOP owner authentication haikukubali credentials zilizowekwa."}
        if login.status_code == 503:
            return {"status": "SHOP_AUTH_NOT_CONFIGURED", "message": "343SHOP OWNER_PASSWORD haijawekwa kwenye Cloudflare Worker."}
        return {"status": "UNAVAILABLE", "message": f"Owner login returned HTTP {login.status_code}."}

    cookie = login.headers.get("set-cookie", "").split(";", 1)[0].strip()
    if not cookie:
        return {"status": "AUTH_FAILED", "message": "Owner login haikurudisha secure session cookie."}

    headers = {"Origin": origin, "Cookie": cookie, "Accept": "application/json"}
    endpoints = {
        "status": "/api/admin/status",
        "products": "/api/admin/products",
        "wallet": "/api/admin/wallet",
        "partner_applications": "/api/admin/partner-applications",
    }
    snapshot: dict[str, Any] = {"status": "CONNECTED"}
    for key, path in endpoints.items():
        try:
            response = await client.get(base + path, headers=headers)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or data.get("ok") is False:
                raise ShopConnectorError("Invalid owner dashboard response.")
            snapshot[key] = data
        except (httpx.HTTPError, ValueError, ShopConnectorError) as exc:
            snapshot[key] = {
                "status": "UNAVAILABLE",
                "error_type": type(exc).__name__,
            }
            snapshot["status"] = "PARTIAL"
    return snapshot


def _product_query(goal: str) -> str | None:
    value = str(goal or "").strip()
    if not re.search(r"\b(search|find|look for|compare|tafuta|nitafutie|linganisha|bidhaa gani)\b", value, re.I):
        return None
    value = re.sub(
        r"^(?:please\s+)?(?:search|find|look\s+for|compare|tafuta|nitafutie|linganisha)\s+",
        "",
        value,
        flags=re.I,
    ).strip(" .,:;-")
    value = re.sub(r"\b(?:on|in|from)\s+343\s*shop\b", "", value, flags=re.I).strip()
    value = re.sub(r"\b(?:in|kwenye)\s+(?:the\s+)?(?:343\s*shop|store|duka)\b", "", value, flags=re.I).strip()
    if len(value) < 2 or value.casefold() in {"products", "bidhaa", "marketplace", "marketplaces"}:
        return None
    return value[:100]


async def inspect_343shop(goal: str) -> dict[str, Any]:
    """
    Read the real 343SHOP Worker, public catalogues and (when configured)
    the owner dashboard. No product, price, stock, order or payment is changed.
    """
    base = _base_url()
    timeout = httpx.Timeout(18.0, connect=6.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        health, mcp_status, marketplace_status, owner_products, sourced_products = await _parallel_public_snapshot(
            client, base
        )
        owner = await _owner_dashboard_snapshot(client, base) if settings.shop_owner_password else {
            "status": "NOT_CONFIGURED",
            "message": "Set SHOP_OWNER_PASSWORD once in the MR AI backend to enable owner-only store management."
        }

        search_result = None
        query = _product_query(goal)
        if query:
            try:
                search_result = await _get_json(
                    client,
                    base,
                    "/api/marketplaces/search?q=" + quote(query, safe=""),
                )
            except (httpx.HTTPError, ValueError, ShopConnectorError) as exc:
                search_result = {"status": "UNAVAILABLE", "error_type": type(exc).__name__}

    public_ok = bool(
        health.get("ok") is True
        and mcp_status.get("ok") is True
        and isinstance(marketplace_status.get("marketplaces"), list)
        and isinstance(owner_products.get("products"), list)
        and isinstance(sourced_products.get("products"), list)
    )
    owner_ok = owner.get("status") == "CONNECTED"
    overall = "COMPLETED" if public_ok and owner_ok else "PARTIAL" if public_ok else "FAILED"

    products = owner.get("products", {}).get("products", []) if isinstance(owner.get("products"), dict) else []
    applications = (
        owner.get("partner_applications", {}).get("applications", [])
        if isinstance(owner.get("partner_applications"), dict) else []
    )
    wallet = owner.get("wallet", {}) if isinstance(owner.get("wallet"), dict) else {}
    marketplace_items = marketplace_status.get("marketplaces") or []

    return {
        "status": overall,
        "verified": overall == "COMPLETED",
        "tool": "343shop_worker_api",
        "worker_url": base,
        "shop_health": health,
        "marketplace_mcp": {
            "ok": mcp_status.get("ok"),
            "tool_count": mcp_status.get("tool_count"),
            "product_database_configured": mcp_status.get("product_database_configured"),
            "writes_enabled": mcp_status.get("writes_enabled"),
        },
        "published_owned_product_count": len(owner_products.get("products") or []),
        "published_sourced_product_count": len(sourced_products.get("products") or []),
        "owner_dashboard": {
            "status": owner.get("status"),
            "product_count": len(products),
            "partner_application_count": len(applications),
            "wallet_balance_tzs": wallet.get("ledger_balance"),
            "wallet_confirmed_transactions": wallet.get("confirmed_count"),
            "payments_live": (owner.get("status") == "CONNECTED" and
                              (owner.get("status", {}).get("payments", {}) if isinstance(owner.get("status"), dict) else {}).get("live_checkout", False)),
            "message": owner.get("message"),
        },
        "marketplaces": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "state": item.get("state"),
                "api_configured": item.get("api_configured"),
                "next_step": item.get("next_step"),
            }
            for item in marketplace_items[:12]
        ],
        "product_search": search_result,
        "order_management": {
            "status": "NOT_AVAILABLE",
            "reason": "343SHOP currently sends customer order requests through WhatsApp and does not expose a database-backed owner orders endpoint.",
        },
        "execution_limits": [
            "This mission action is read-only. It does not publish products, change prices or stock, send WhatsApp messages, confirm payments, or purchase from marketplaces.",
            "Owner products, wallet and partner applications are visible only when SHOP_OWNER_PASSWORD is configured and valid.",
            "External seller listings are not 343SHOP-owned inventory.",
        ],
        "verified": overall == "COMPLETED",
    }


async def _parallel_public_snapshot(
    client: httpx.AsyncClient,
    base: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    import asyncio

    paths = (
        "/api/health",
        "/api/mcp/status",
        "/api/marketplaces/status",
        "/api/store/owner-products",
        "/api/store/products",
    )
    results = await asyncio.gather(
        *(_get_json(client, base, path) for path in paths),
        return_exceptions=True,
    )
    names = ("health", "mcp_status", "marketplace_status", "owner_products", "sourced_products")
    values: list[dict[str, Any]] = []
    for name, result in zip(names, results):
        if isinstance(result, BaseException):
            values.append({"status": "UNAVAILABLE", "error_type": type(result).__name__, "component": name})
        else:
            values.append(result)
    return tuple(values)  # type: ignore[return-value]
