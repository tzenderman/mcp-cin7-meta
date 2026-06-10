"""HTTP transport entry point with ScaleKit OAuth 2.1 authentication."""

from __future__ import annotations

import json
import logging
import os

import jwt
from dotenv import load_dotenv
from fastmcp.server.auth.providers.scalekit import ScalekitProvider
from scalekit import ScalekitClient
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, Mount

from .server import create_mcp_server
from .utils.session_store import session_store, SESSION_ENABLED, SESSION_TTL_DAYS

load_dotenv()

logger = logging.getLogger("cin7_meta.http_server")

# ScaleKit Configuration
SCALEKIT_ENVIRONMENT_URL = os.getenv("SCALEKIT_ENVIRONMENT_URL")
SCALEKIT_CLIENT_ID = os.getenv("SCALEKIT_CLIENT_ID", "")
SCALEKIT_CLIENT_SECRET = os.getenv("SCALEKIT_CLIENT_SECRET", "")
SCALEKIT_RESOURCE_ID = os.getenv("SCALEKIT_RESOURCE_ID")
SCALEKIT_INTERCEPTOR_SECRET = os.getenv("SCALEKIT_INTERCEPTOR_SECRET", "")
SERVER_URL = os.getenv("SERVER_URL")

# Email allowlist for interceptors (comma-separated)
ALLOWED_EMAILS_RAW = os.getenv("ALLOWED_EMAILS", "")
ALLOWED_EMAILS: set[str] = {
    email.strip().lower()
    for email in ALLOWED_EMAILS_RAW.split(",")
    if email.strip()
}

# Session configuration
SESSION_COOKIE_NAME = "mcp_session"

# Initialize ScaleKit client for interceptor verification
scalekit_client: ScalekitClient | None = None
if SCALEKIT_ENVIRONMENT_URL and SCALEKIT_CLIENT_ID and SCALEKIT_CLIENT_SECRET:
    scalekit_client = ScalekitClient(
        SCALEKIT_ENVIRONMENT_URL,
        SCALEKIT_CLIENT_ID,
        SCALEKIT_CLIENT_SECRET,
    )


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


def is_email_allowed(email: str) -> bool:
    """Check if an email is in the allowlist.

    If ALLOWED_EMAILS is not set or empty, all emails are allowed.
    """
    if not ALLOWED_EMAILS:
        return True
    return email.lower() in ALLOWED_EMAILS


def verify_interceptor_signature(request: Request, body: bytes) -> bool:
    """Verify the interceptor request signature from ScaleKit.

    Returns True if verification passes or if verification is not configured.
    """
    if not SCALEKIT_INTERCEPTOR_SECRET:
        logger.warning("[INTERCEPTOR] No SCALEKIT_INTERCEPTOR_SECRET configured - skipping signature verification")
        return True

    if not scalekit_client:
        logger.warning("[INTERCEPTOR] ScaleKit client not initialized - skipping signature verification")
        return True

    headers = {
        'interceptor-id': request.headers.get('interceptor-id', ''),
        'interceptor-signature': request.headers.get('interceptor-signature', ''),
        'interceptor-timestamp': request.headers.get('interceptor-timestamp', ''),
    }

    try:
        is_valid = scalekit_client.verify_interceptor_payload(
            secret=SCALEKIT_INTERCEPTOR_SECRET,
            headers=headers,
            payload=body,
        )
        if not is_valid:
            logger.warning("[INTERCEPTOR] Invalid signature")
        return is_valid
    except Exception as e:
        logger.error(f"[INTERCEPTOR] Signature verification error: {e}")
        return False


async def handle_pre_signup(request: Request) -> JSONResponse:
    """Handle ScaleKit PRE_SIGNUP interceptor.

    Checks if the user's email is in the allowlist before allowing signup.
    """
    try:
        body = await request.body()

        if not verify_interceptor_signature(request, body):
            return JSONResponse(
                {"decision": "DENY", "error": {"message": "Invalid request signature"}},
            )

        data = json.loads(body)

        user_email = (
            data.get("interceptor_context", {}).get("user_email", "")
            or data.get("data", {}).get("user", {}).get("email", "")
        )
        trigger_point = data.get("trigger_point", "")

        logger.info(f"[INTERCEPTOR] {trigger_point} for email: {user_email}")

        if is_email_allowed(user_email):
            logger.info(f"[INTERCEPTOR] ALLOW signup for: {user_email}")
            return JSONResponse({"decision": "ALLOW"})
        else:
            logger.warning(f"[INTERCEPTOR] DENY signup for: {user_email} (not in allowlist)")
            return JSONResponse({
                "decision": "DENY",
                "error": {"message": "Email not authorized for signup"}
            })

    except Exception as e:
        logger.error(f"[INTERCEPTOR] Error processing PRE_SIGNUP: {e}")
        return JSONResponse({
            "decision": "DENY",
            "error": {"message": "Internal error processing signup"}
        })


async def handle_pre_session_creation(request: Request) -> JSONResponse:
    """Handle ScaleKit PRE_SESSION_CREATION interceptor."""
    try:
        body = await request.body()

        if not verify_interceptor_signature(request, body):
            return JSONResponse(
                {"decision": "DENY", "error": {"message": "Invalid request signature"}},
            )

        data = json.loads(body)

        user_email = (
            data.get("interceptor_context", {}).get("user_email", "")
            or data.get("data", {}).get("user", {}).get("email", "")
        )
        trigger_point = data.get("trigger_point", "")

        logger.info(f"[INTERCEPTOR] {trigger_point} for email: {user_email}")

        if is_email_allowed(user_email):
            logger.info(f"[INTERCEPTOR] ALLOW session for: {user_email}")
            return JSONResponse({"decision": "ALLOW"})
        else:
            logger.warning(f"[INTERCEPTOR] DENY session for: {user_email} (not in allowlist)")
            return JSONResponse({
                "decision": "DENY",
                "error": {"message": "Email not authorized for access"}
            })

    except Exception as e:
        logger.error(f"[INTERCEPTOR] Error processing PRE_SESSION_CREATION: {e}")
        return JSONResponse({
            "decision": "DENY",
            "error": {"message": "Internal error processing session"}
        })


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

    if not is_email_allowed(email):
        logger.warning(f"[SESSION] Denied session for non-allowed email: {email}")
        return JSONResponse(
            {"error": "Email not authorized"},
            status_code=403,
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
    """Create ASGI app with CORS middleware and interceptor endpoints."""
    mcp_app = mcp.http_app()

    interceptor_routes = [
        Route("/auth/interceptors/pre-signup", handle_pre_signup, methods=["POST"]),
        Route("/auth/interceptors/pre-session-creation", handle_pre_session_creation, methods=["POST"]),
    ]

    session_routes = [
        Route("/session/create", handle_session_create, methods=["POST"]),
        Route("/session/check", handle_session_check, methods=["GET"]),
        Route("/session/delete", handle_session_delete, methods=["POST", "DELETE"]),
    ]

    app = Starlette(
        routes=[
            *interceptor_routes,
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

    if ALLOWED_EMAILS:
        logger.info(f"Email allowlist configured with {len(ALLOWED_EMAILS)} email(s)")
    else:
        logger.warning("No ALLOWED_EMAILS configured - all emails permitted")

    if not SCALEKIT_INTERCEPTOR_SECRET:
        logger.warning("No SCALEKIT_INTERCEPTOR_SECRET configured - interceptor signatures will not be verified")

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
