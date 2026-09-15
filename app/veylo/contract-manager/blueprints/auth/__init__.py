import functools
import logging
from flask import Blueprint, g, redirect, request, session, url_for
from config import get_settings

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)


def get_current_user():
    """Retrieves the authenticated user from session or returns mock in offline dev."""
    settings = get_settings()
    if not settings.is_auth_enabled:
        return {
            "name": "Local Developer",
            "email": "dev@veylo.internal",
            "roles": ["Admin"],
            "is_local": True,
        }
    return session.get("user")


def login_required(f):
    """Decorator to enforce Entra ID authentication on protected routes."""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        settings = get_settings()
        if not settings.is_auth_enabled:
            # Bypass authentication in local dev mode when auth is disabled
            g.user = get_current_user()
            return f(*args, **kwargs)

        user = session.get("user")
        if not user:
            # Store target URL in session for post-login redirect
            session["next_url"] = request.url
            return redirect(url_for("auth.login"))

        g.user = user
        return f(*args, **kwargs)

    return decorated_function


# Import routes to register endpoints with the blueprint
from blueprints.auth import routes  # noqa: E402, F401
