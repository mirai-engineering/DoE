from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient


TRUE_VALUES = {"1", "true", "yes", "on"}
PUBLIC_PATHS = {"/", "/health", "/api/health", "/favicon.ico", "/manifest.webmanifest", "/robots.txt"}
PUBLIC_PREFIXES = ("/assets/", "/static/")
DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    clerk_user_id: str
    workspace_id: str | None = None
    claims: dict | None = None


def _env_enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def auth_required() -> bool:
    return _env_enabled("CLERK_AUTH_REQUIRED")


def docs_public() -> bool:
    return _env_enabled("FASTAPI_DOCS_PUBLIC", default=not auth_required())


def is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    if path.startswith(PUBLIC_PREFIXES):
        return True
    if docs_public() and path in DOCS_PATHS:
        return True
    return False


@lru_cache(maxsize=4)
def _jwk_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


def _issuer() -> str | None:
    return os.getenv("CLERK_JWT_ISSUER") or os.getenv("CLERK_ISSUER")


def _jwks_url() -> str | None:
    explicit = os.getenv("CLERK_JWKS_URL")
    if explicit:
        return explicit
    issuer = _issuer()
    if not issuer:
        return None
    return issuer.rstrip("/") + "/.well-known/jwks.json"


def _jwt_leeway_seconds() -> int:
    try:
        return int(os.getenv("CLERK_JWT_LEEWAY_SECONDS", "5"))
    except ValueError:
        return 5


def _workspace_from_claims(claims: dict) -> str | None:
    workspace_id = claims.get("workspace_id")
    return workspace_id if isinstance(workspace_id, str) and workspace_id else None


def authenticate_bearer_token(authorization: str | None) -> AuthenticatedPrincipal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    expected_test_token = os.getenv("CLERK_AUTH_TEST_TOKEN")
    if expected_test_token and token == expected_test_token:
        return AuthenticatedPrincipal(
            clerk_user_id=os.getenv("CLERK_AUTH_TEST_USER_ID", "test_user"),
            workspace_id=os.getenv("CLERK_AUTH_TEST_WORKSPACE_ID", "test_workspace"),
            claims={"sub": os.getenv("CLERK_AUTH_TEST_USER_ID", "test_user")},
        )

    issuer = _issuer()
    jwks_url = _jwks_url()
    if not issuer or not jwks_url:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clerk JWT verification is not configured")

    audience = os.getenv("CLERK_JWT_AUDIENCE")
    try:
        signing_key = _jwk_client(jwks_url).get_signing_key_from_jwt(token)
        decode_kwargs = {
            "algorithms": ["RS256"],
            "issuer": issuer,
            "leeway": _jwt_leeway_seconds(),
            "options": {"verify_aud": bool(audience)},
        }
        if audience:
            decode_kwargs["audience"] = audience
        claims = jwt.decode(token, signing_key.key, **decode_kwargs)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from exc

    subject = claims.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")

    return AuthenticatedPrincipal(clerk_user_id=subject, workspace_id=_workspace_from_claims(claims), claims=claims)


def request_principal(request: Request) -> AuthenticatedPrincipal | None:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        return None
    if not isinstance(principal, AuthenticatedPrincipal):
        return None
    return principal


def principal_workspace_id(principal: AuthenticatedPrincipal | None) -> str | None:
    if principal and principal.workspace_id:
        return principal.workspace_id
    return None
