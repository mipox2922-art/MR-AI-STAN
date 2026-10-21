import asyncio
import base64
import time

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
from fastapi import HTTPException
from jose import jwt

from app import github_oidc


def _base64url_integer(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _signed_token(repository="mipox2922-art/MR-AI-STAN", workflow_ref=None):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    public_numbers = private_key.public_key().public_numbers()
    public_jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": "test-key",
        "n": _base64url_integer(public_numbers.n),
        "e": _base64url_integer(public_numbers.e),
    }
    now = int(time.time())
    claims = {
        "iss": github_oidc.GITHUB_ISSUER,
        "aud": github_oidc.SCHEDULER_AUDIENCE,
        "iat": now - 2,
        "exp": now + 120,
        "sub": "repo:mipox2922-art/MR-AI-STAN:ref:refs/heads/main",
        "repository": repository,
        "repository_owner": "mipox2922-art",
        "ref": "refs/heads/main",
        "workflow_ref": workflow_ref or github_oidc.TRUSTED_WORKFLOW,
        "event_name": "schedule",
    }
    token = jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "test-key"})
    return token, public_jwk


class _Response:
    def __init__(self, keys):
        self._keys = keys

    def raise_for_status(self):
        return None

    def json(self):
        return {"keys": self._keys}


class _AsyncClient:
    def __init__(self, keys, **kwargs):
        self._keys = keys

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, url):
        assert url == github_oidc.GITHUB_JWKS_URL
        return _Response(self._keys)


def test_github_oidc_accepts_only_signed_trusted_scheduler_workflow(monkeypatch):
    token, public_jwk = _signed_token()
    monkeypatch.setattr(
        github_oidc.httpx,
        "AsyncClient",
        lambda **kwargs: _AsyncClient([public_jwk], **kwargs),
    )

    claims = asyncio.run(github_oidc.verify_github_actions_token(token))
    assert claims["repository"] == github_oidc.TRUSTED_REPOSITORY
    assert claims["workflow_ref"] == github_oidc.TRUSTED_WORKFLOW


def test_github_oidc_rejects_a_different_repository(monkeypatch):
    token, public_jwk = _signed_token(repository="attacker/other-repository")
    monkeypatch.setattr(
        github_oidc.httpx,
        "AsyncClient",
        lambda **kwargs: _AsyncClient([public_jwk], **kwargs),
    )

    try:
        asyncio.run(github_oidc.verify_github_actions_token(token))
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Token from a different repository must be rejected")


def test_github_oidc_rejects_a_different_workflow(monkeypatch):
    token, public_jwk = _signed_token(workflow_ref="mipox2922-art/MR-AI-STAN/.github/workflows/ci.yml@refs/heads/main")
    monkeypatch.setattr(
        github_oidc.httpx,
        "AsyncClient",
        lambda **kwargs: _AsyncClient([public_jwk], **kwargs),
    )

    try:
        asyncio.run(github_oidc.verify_github_actions_token(token))
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("A different workflow must not be authorized")
