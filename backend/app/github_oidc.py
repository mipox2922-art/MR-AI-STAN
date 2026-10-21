"""Verify GitHub Actions OIDC tokens for the unattended MR AI scheduler."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException
from jose import JWTError, jwt

GITHUB_ISSUER = "https://token.actions.githubusercontent.com"
GITHUB_JWKS_URL = f"{GITHUB_ISSUER}/.well-known/jwks"
SCHEDULER_AUDIENCE = "mr-ai-stan-scheduler"
TRUSTED_REPOSITORY = "mipox2922-art/MR-AI-STAN"
TRUSTED_REF = "refs/heads/main"
TRUSTED_WORKFLOW = (
    "mipox2922-art/MR-AI-STAN/.github/workflows/mr-ai-scheduler.yml@refs/heads/main"
)


def _forbidden() -> HTTPException:
    # Never include the received token or untrusted claims in public error text.
    return HTTPException(status_code=403, detail="Forbidden")


async def verify_github_actions_token(token: str) -> dict[str, Any]:
    """Verify signature, issuer, audience, expiry, and the exact trusted workflow."""
    token = str(token or "").strip()
    if not token or len(token) > 16_384:
        raise _forbidden()

    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise _forbidden() from exc

    kid = header.get("kid")
    if header.get("alg") != "RS256" or not isinstance(kid, str) or not kid:
        raise _forbidden()

    # Fetch signing keys from GitHub over TLS. Failure is closed, never bypassed.
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
            response = await client.get(GITHUB_JWKS_URL)
            response.raise_for_status()
            jwks = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="GitHub identity verification is temporarily unavailable",
        ) from exc

    keys = jwks.get("keys", []) if isinstance(jwks, dict) else []
    signing_key = next(
        (
            key
            for key in keys
            if isinstance(key, dict)
            and key.get("kid") == kid
            and key.get("kty") == "RSA"
            and key.get("alg", "RS256") == "RS256"
            and key.get("use", "sig") == "sig"
        ),
        None,
    )
    if signing_key is None:
        raise _forbidden()

    try:
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=SCHEDULER_AUDIENCE,
            issuer=GITHUB_ISSUER,
            options={
                "require_aud": True,
                "require_exp": True,
                "require_iat": True,
                "require_iss": True,
                "require_sub": True,
            },
        )
    except JWTError as exc:
        raise _forbidden() from exc

    # A valid GitHub token from any other repo, branch, or workflow is not enough.
    if (
        claims.get("repository") != TRUSTED_REPOSITORY
        or claims.get("repository_owner") != "mipox2922-art"
        or claims.get("ref") != TRUSTED_REF
        or claims.get("workflow_ref") != TRUSTED_WORKFLOW
        or claims.get("event_name") not in {"schedule", "workflow_dispatch"}
    ):
        raise _forbidden()

    return claims
