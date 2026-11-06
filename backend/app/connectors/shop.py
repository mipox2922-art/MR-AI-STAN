from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import settings


class ShopConnectorError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def shop_configuration_status() -> dict[str, Any]:
    base_url = settings.shop_api_base_url.strip().rstrip("/")
    parsed = urlparse(base_url)
    configured = bool(
        settings.shop_api_key.strip()
        and len(settings.shop_api_key.strip()) >= 32
        and parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
    )
    return {
        "configured": configured,
        "base_url": base_url if parsed.scheme == "https" and parsed.hostname else None,
        "status": "CONFIGURED" if configured else "NOT_CONFIGURED",
        "message": (
            "Private 343SHOP API key and HTTPS endpoint are configured; live reachability is checked on demand."
            if configured
            else "Set SHOP_API_KEY (32+ characters) and SHOP_API_BASE_URL to the private 343SHOP API endpoint."
        ),
    }


def _base_url() -> str:
    state = shop_configuration_status()
    if not state["configured"]:
        raise ShopConnectorError(state["message"], 503)
    return str(state["base_url"])


async def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = _base_url() + "/" + path.lstrip("/")
    headers = {
        "Authorization": "Bearer " + settings.shop_api_key.strip(),
        "Accept": "application/json",
        "Cache-Control": "no-store",
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0), follow_redirects=False) as client:
            response = await client.get(url, params=params, headers=headers)
    except httpx.TimeoutException as exc:
        raise ShopConnectorError("343SHOP private API timed out; no store data was verified.", 504) from exc
    except httpx.RequestError as exc:
        raise ShopConnectorError("343SHOP private API could not be reached; no store data was verified.", 502) from exc

    if response.status_code == 401:
        raise ShopConnectorError("343SHOP rejected the private API key. Check that SHOP_API_KEY matches MR_AI_SHOP_API_KEY.", 401)
    if response.status_code == 503:
        raise ShopConnectorError("343SHOP private API is not configured or its order storage is unavailable.", 503)
    if response.status_code >= 400:
        raise ShopConnectorError(f"343SHOP private API returned HTTP {response.status_code}.", 502)
    try:
        data = response.json()
    except ValueError as exc:
        raise ShopConnectorError("343SHOP returned invalid JSON; no store data was verified.", 502) from exc
    if not isinstance(data, dict):
        raise ShopConnectorError("343SHOP returned an unexpected response shape.", 502)
    return data


async def shop_connection_status() -> dict[str, Any]:
    state = shop_configuration_status()
    if not state["configured"]:
        return state
    try:
        health = await _get("health")
    except ShopConnectorError as exc:
        return {
            **state,
            "status": "NOT_CONNECTED",
            "connected": False,
            "message": str(exc),
            "http_status": exc.status_code,
        }
    connected = health.get("status") == "connected" and health.get("store") == "343SHOP"
    return {
        **state,
        "status": "CONNECTED" if connected else "NOT_CONNECTED",
        "connected": connected,
        "api_version": health.get("apiVersion"),
        "capabilities": health.get("capabilities") or [],
        "message": "343SHOP private API health verified." if connected else "343SHOP did not confirm its expected API identity.",
    }


def _safe_product(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": item.get("slug"),
        "name": item.get("name"),
        "nameSw": item.get("nameSw"),
        "description": item.get("description"),
        "descriptionSw": item.get("descriptionSw"),
        "category": item.get("category"),
        "priceCents": item.get("priceCents"),
        "type": item.get("type"),
        "active": item.get("active", True),
        "badge": item.get("badge"),
        "personalizable": item.get("personalizable", False),
    }


def _safe_order(item: dict[str, Any]) -> dict[str, Any]:
    customer = item.get("customer") if isinstance(item.get("customer"), dict) else {}
    totals = item.get("totals") if isinstance(item.get("totals"), dict) else {}
    return {
        "id": item.get("id"),
        "createdAt": item.get("createdAt"),
        "status": item.get("status"),
        # Only customer name is needed for a store briefing; omit contacts and addresses.
        "customerName": customer.get("name"),
        "items": [
            {
                "name": line.get("name"),
                "slug": line.get("slug"),
                "qty": line.get("qty"),
                "lineCents": line.get("lineCents"),
            }
            for line in (item.get("items") or [])[:20]
            if isinstance(line, dict)
        ],
        "totals": {
            "subtotalCents": totals.get("subtotalCents"),
            "shippingCents": totals.get("shippingCents"),
            "totalCents": totals.get("totalCents"),
        },
    }


async def shop_snapshot(product_limit: int = 40, order_limit: int = 20) -> dict[str, Any]:
    """Fetch verified store overview, catalog and recent orders without exposing customer contact data."""
    health = await _get("health")
    if health.get("status") != "connected" or health.get("store") != "343SHOP":
        raise ShopConnectorError("343SHOP health identity check failed.", 502)

    overview, products_payload, orders_payload = await __import__("asyncio").gather(
        _get("overview"),
        _get("products"),
        _get("orders", {"limit": max(1, min(int(order_limit), 100))}),
    )
    raw_products = products_payload.get("products")
    raw_orders = orders_payload.get("orders")
    if not isinstance(raw_products, list) or not isinstance(raw_orders, list):
        raise ShopConnectorError("343SHOP products/orders response shape is invalid.", 502)

    products = [_safe_product(item) for item in raw_products if isinstance(item, dict)]
    orders = [_safe_order(item) for item in raw_orders if isinstance(item, dict)]
    return {
        "status": "COMPLETED",
        "store": "343SHOP",
        "verified": True,
        "generated_at": overview.get("generatedAt"),
        "overview": overview,
        "products": products[: max(1, min(int(product_limit), 100))],
        "products_returned": len(products),
        "orders": orders,
        "orders_returned": len(orders),
        "limitations": overview.get("limitations") or [],
    }
