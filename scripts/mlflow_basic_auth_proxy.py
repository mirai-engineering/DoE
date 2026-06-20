"""Minimal HTTP Basic auth proxy for the Mirai Railway MLflow service.

The public Railway port terminates here. The real MLflow server listens only on
127.0.0.1 and still runs MLflow's built-in ``--app-name basic-auth`` app.
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import os
from collections.abc import Iterable

from aiohttp import ClientSession, web

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _csv_env(name: str) -> set[str]:
    return {part.strip() for part in os.getenv(name, "").split(",") if part.strip()}


def _required_env(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


USERNAME = _required_env("MLFLOW_AUTH_ADMIN_USERNAME")
PASSWORD = _required_env("MLFLOW_AUTH_ADMIN_PASSWORD")
ALLOWED_HOSTS = _csv_env("MLFLOW_ALLOWED_HOSTS")
CORS_ALLOWED_ORIGINS = _csv_env("MLFLOW_CORS_ALLOWED_ORIGINS")
UPSTREAM = os.getenv("MLFLOW_INTERNAL_URL", "http://127.0.0.1:5001").rstrip("/")

if "*" in ALLOWED_HOSTS or not ALLOWED_HOSTS:
    raise RuntimeError("MLFLOW_ALLOWED_HOSTS must be explicit; wildcard is not allowed")
if "*" in CORS_ALLOWED_ORIGINS or not CORS_ALLOWED_ORIGINS:
    raise RuntimeError("MLFLOW_CORS_ALLOWED_ORIGINS must be explicit; wildcard is not allowed")


def _host_without_port(host: str) -> str:
    if host.startswith("[") and "]" in host:
        return host[1 : host.index("]")]
    return host.split(":", 1)[0]


def _cors_headers(origin: str | None) -> dict[str, str]:
    if origin and origin in CORS_ALLOWED_ORIGINS:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Requested-With",
            "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
            "Vary": "Origin",
        }
    return {}


def _unauthorized(origin: str | None) -> web.Response:
    headers = {"WWW-Authenticate": 'Basic realm="mirai-mlflow"'}
    headers.update(_cors_headers(origin))
    return web.Response(status=401, text="Authentication required\n", headers=headers)


def _forbidden(origin: str | None) -> web.Response:
    headers = _cors_headers(origin)
    return web.Response(status=403, text="Forbidden\n", headers=headers)


def _valid_basic_auth(header: str | None) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
    except Exception:
        return False
    supplied_username, sep, supplied_password = decoded.partition(":")
    if not sep:
        return False
    return hmac.compare_digest(supplied_username, USERNAME) and hmac.compare_digest(
        supplied_password, PASSWORD
    )


def _forward_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    forwarded: dict[str, str] = {}
    for key, value in headers:
        lower = key.lower()
        if lower in HOP_BY_HOP_HEADERS or lower == "host":
            continue
        forwarded[key] = value
    forwarded["Host"] = "127.0.0.1"
    return forwarded


async def handle(request: web.Request) -> web.StreamResponse:
    origin = request.headers.get("Origin")

    if request.path == "/health":
        return web.Response(status=200, text="ok\n", headers=_cors_headers(origin))

    host = _host_without_port(request.headers.get("Host", ""))
    if host not in ALLOWED_HOSTS:
        return _forbidden(origin)

    if request.method == "OPTIONS":
        if not _valid_basic_auth(request.headers.get("Authorization")):
            return _unauthorized(origin)
        return web.Response(status=204, headers=_cors_headers(origin))

    if not _valid_basic_auth(request.headers.get("Authorization")):
        return _unauthorized(origin)

    body = await request.read()
    upstream_url = f"{UPSTREAM}{request.rel_url}"
    async with request.app["client"].request(
        request.method,
        upstream_url,
        data=body,
        headers=_forward_headers(request.headers.items()),
        allow_redirects=False,
    ) as upstream_response:
        response_body = await upstream_response.read()
        response_headers = {
            key: value
            for key, value in upstream_response.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS
        }
        response_headers.update(_cors_headers(origin))
        return web.Response(
            status=upstream_response.status,
            body=response_body,
            headers=response_headers,
        )


async def create_app() -> web.Application:
    app = web.Application(client_max_size=1024**3)
    app.router.add_route("*", "/{tail:.*}", handle)
    app["client"] = ClientSession()

    async def close_client(app_: web.Application) -> None:
        await app_["client"].close()

    app.on_cleanup.append(close_client)
    return app


def main() -> None:
    port = int(os.getenv("PORT", "8080"))
    web.run_app(create_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
