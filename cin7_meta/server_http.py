"""HTTP transport entry point with ScaleKit OAuth 2.1 authentication."""

from __future__ import annotations

import logging
import os

import jwt
from dotenv import load_dotenv
from fastmcp.server.auth.providers.scalekit import ScalekitProvider
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, Mount

from .server import create_mcp_server
from .utils.session_store import session_store, SESSION_ENABLED, SESSION_TTL_DAYS

load_dotenv()

logger = logging.getLogger("cin7_meta.http_server")

# ScaleKit Configuration. The email allowlist is enforced centrally by the
# standalone `scalekit-interceptor` service (the ScaleKit environment's
# interceptors point at it), so this server only validates OAuth tokens.
SCALEKIT_ENVIRONMENT_URL = os.getenv("SCALEKIT_ENVIRONMENT_URL")
SCALEKIT_RESOURCE_ID = os.getenv("SCALEKIT_RESOURCE_ID")
SERVER_URL = os.getenv("SERVER_URL")

# Session configuration
SESSION_COOKIE_NAME = "mcp_session"


def create_auth_provider() -> ScalekitProvider | None:
    """Create ScaleKit auth provider if configured."""
    required = [SCALEKIT_ENVIRONMENT_URL, SCALEKIT_RESOURCE_ID, SERVER_URL]
    if not all(required):
        logger.warning(
            "ScaleKit OAuth not configured. Set SCALEKIT_ENVIRONMENT_URL, "
            "SCALEKIT_RESOURCE_ID, and SERVER_URL environment variables."
        )
        return None

    return ScalekitProvider(
        environment_url=SCALEKIT_ENVIRONMENT_URL,
        resource_id=SCALEKIT_RESOURCE_ID,
        base_url=SERVER_URL,
    )


def _extract_email_from_token(auth_header: str) -> str | None:
    """Extract user email from JWT token without verification."""
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
        return claims.get("email") or claims.get("sub")
    except jwt.DecodeError as e:
        logger.warning(f"[SESSION] Failed to decode JWT: {e}")
        return None


async def handle_session_create(request: Request) -> Response:
    """Create a session after successful OAuth authentication."""
    if not SESSION_ENABLED:
        return JSONResponse(
            {"error": "Sessions are disabled"},
            status_code=503,
        )

    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return JSONResponse(
            {"error": "Authorization header required"},
            status_code=401,
        )

    email = _extract_email_from_token(auth_header)
    if not email:
        return JSONResponse(
            {"error": "Could not extract email from token"},
            status_code=400,
        )

    session = session_store.create_session(email)
    logger.info(f"[SESSION] Created session for {email}")

    response = JSONResponse({
        "status": "ok",
        "email": email,
        "expires_in_days": SESSION_TTL_DAYS,
    })

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.session_id,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=True,
        samesite="lax",
    )

    return response


async def handle_session_check(request: Request) -> JSONResponse:
    """Check if current session is valid."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)

    if not session_id:
        return JSONResponse({"valid": False, "reason": "no_session"})

    session = session_store.get_session(session_id)
    if not session:
        return JSONResponse({"valid": False, "reason": "expired_or_invalid"})

    return JSONResponse({
        "valid": True,
        "email": session.user_email,
        "expires_at": session.expires_at,
    })


async def handle_session_delete(request: Request) -> Response:
    """Delete current session (logout)."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)

    if session_id:
        session_store.delete_session(session_id)
        logger.info(f"[SESSION] Deleted session {session_id[:8]}...")

    response = JSONResponse({"status": "ok"})
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return response


# Create auth provider and MCP server
auth_provider = create_auth_provider()
mcp = create_mcp_server(auth=auth_provider)


def create_app():
    """Create ASGI app with CORS middleware and session endpoints.

    Email-allowlist gating is handled centrally by the standalone
    `scalekit-interceptor` service, not here.
    """
    mcp_app = mcp.http_app()

    session_routes = [
        Route("/session/create", handle_session_create, methods=["POST"]),
        Route("/session/check", handle_session_check, methods=["GET"]),
        Route("/session/delete", handle_session_delete, methods=["POST", "DELETE"]),
    ]

    app = Starlette(
        routes=[
            *session_routes,
            Mount("/", app=mcp_app),
        ],
        lifespan=mcp_app.lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    return app


app = create_app()


def main() -> None:
    """Run MCP server with HTTP transport and ScaleKit OAuth."""
    import uvicorn

    from .utils.spec_loader import get_spec

    missing = [v for v in ("CIN7_ACCOUNT_ID", "CIN7_API_KEY") if not os.getenv(v)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    # Fail loud at startup if the vendored spec is missing or malformed.
    get_spec()

    if not auth_provider:
        logger.warning("Starting server WITHOUT OAuth authentication!")
    else:
        logger.info(f"ScaleKit environment: {SCALEKIT_ENVIRONMENT_URL}")
        logger.info(f"ScaleKit resource ID: {SCALEKIT_RESOURCE_ID}")

    logger.info("Email allowlist enforced centrally by the scalekit-interceptor service")

    if SESSION_ENABLED:
        logger.info(f"Session persistence enabled with {SESSION_TTL_DAYS} day TTL")
    else:
        logger.info("Session persistence disabled")

    port = int(os.getenv("PORT", "3000"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting Cin7 Core Meta MCP Server on {host}:{port}")
    logger.info(f"Server URL: {SERVER_URL}")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
