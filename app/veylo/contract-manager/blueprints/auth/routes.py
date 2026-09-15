import logging
import secrets
from urllib.parse import quote
from flask import (
    flash,
    redirect,
    request,
    session,
    url_for,
)
import msal

from blueprints.auth import auth_bp
from config import get_settings

logger = logging.getLogger(__name__)


def _build_msal_app(cache=None):
    """Initializes MSAL ConfidentialClientApplication."""
    settings = get_settings()
    return msal.ConfidentialClientApplication(
        client_id=settings.entra_client_id,
        client_credential=settings.entra_client_secret,
        authority=settings.entra_authority,
        token_cache=cache,
    )


def _get_redirect_uri() -> str:
    """Determines the OIDC redirect URI."""
    settings = get_settings()
    if settings.entra_redirect_uri:
        return settings.entra_redirect_uri
    return request.url_root.rstrip("/") + url_for("auth.callback")


@auth_bp.route("/auth/login", methods=["GET"])
def login():
    """Initiates Entra ID OAuth2 / OIDC authorization code flow."""
    settings = get_settings()
    if not settings.is_auth_enabled:
        flash("Authentication is disabled in local development mode.", "info")
        return redirect(url_for("contracts.index"))

    # Generate state and nonce for CSRF protection
    state = secrets.token_urlsafe(32)
    session["auth_state"] = state

    redirect_uri = _get_redirect_uri()
    msal_app = _build_msal_app()

    auth_url = msal_app.get_authorization_request_url(
        scopes=["User.Read"],
        state=state,
        redirect_uri=redirect_uri,
        prompt="select_account",  # Allows seamless SSO while supporting account selection if needed
    )

    logger.info(f"[Auth] Redirecting user to Entra ID login: {redirect_uri}")
    return redirect(auth_url)


@auth_bp.route("/auth/callback", methods=["GET"])
def callback():
    """Handles the redirect from Entra ID with the authorization code."""
    settings = get_settings()
    if not settings.is_auth_enabled:
        return redirect(url_for("contracts.index"))

    # Verify state matches session
    expected_state = session.pop("auth_state", None)
    received_state = request.args.get("state")

    if not received_state or received_state != expected_state:
        logger.warning("[Auth] State mismatch in auth callback. Possible CSRF.")
        flash("Authentication state validation failed. Please try again.", "danger")
        return redirect(url_for("contracts.index"))

    if "error" in request.args:
        error_desc = request.args.get("error_description", request.args["error"])
        logger.warning(f"[Auth] Entra ID authentication returned error: {error_desc}")
        flash(f"Sign in failed: {error_desc}", "danger")
        return redirect(url_for("contracts.index"))

    code = request.args.get("code")
    if not code:
        flash("Missing authorization code from identity provider.", "danger")
        return redirect(url_for("contracts.index"))

    redirect_uri = _get_redirect_uri()
    msal_app = _build_msal_app()

    result = msal_app.acquire_token_by_authorization_code(
        code=code,
        scopes=["User.Read"],
        redirect_uri=redirect_uri,
    )

    if "error" in result:
        err_msg = result.get("error_description", result.get("error"))
        logger.error(f"[Auth] Token acquisition failed: {err_msg}")
        flash(f"Failed to acquire security token: {err_msg}", "danger")
        return redirect(url_for("contracts.index"))

    # Validate ID token claims
    id_claims = result.get("id_token_claims", {})
    tenant_id = id_claims.get("tid")

    # Tenant verification
    if settings.entra_tenant_id and tenant_id != settings.entra_tenant_id:
        logger.warning(f"[Auth] Tenant ID mismatch: received {tenant_id}, expected {settings.entra_tenant_id}")
        flash("Access denied: You are not a member of the authorized directory.", "danger")
        return redirect(url_for("contracts.index"))

    # Establish authenticated session
    user_info = {
        "name": id_claims.get("name", "Authenticated User"),
        "email": id_claims.get("preferred_username") or id_claims.get("email", ""),
        "oid": id_claims.get("oid", ""),
        "roles": id_claims.get("roles", []),
        "is_local": False,
    }
    session["user"] = user_info
    logger.info(f"[Auth] User successfully authenticated via Entra ID: {user_info['email']}")

    flash(f"Signed in as {user_info['name']}", "success")
    next_url = session.pop("next_url", None)
    return redirect(next_url or url_for("contracts.index"))


@auth_bp.route("/auth/logout", methods=["GET", "POST"])
def logout():
    """Clears local session and redirects to Microsoft sign-out endpoint."""
    settings = get_settings()
    session.clear()
    flash("You have been signed out.", "info")

    if settings.is_auth_enabled:
        post_logout_redirect = request.url_root
        logout_url = (
            f"{settings.entra_authority}/oauth2/v2.0/logout"
            f"?post_logout_redirect_uri={quote(post_logout_redirect)}"
        )
        return redirect(logout_url)

    return redirect(url_for("contracts.index"))
