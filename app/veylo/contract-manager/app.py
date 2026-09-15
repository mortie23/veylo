import logging
from flask import Flask, g, redirect, render_template, request, session, url_for

from blueprints.api import api_bp
from blueprints.auth import auth_bp, get_current_user
from blueprints.contracts import contracts_bp
from blueprints.rules import rules_bp
from config import get_settings
from database import init_db
from seed_data import seed_sample_contracts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("veylo-contract-manager")


def create_app() -> Flask:
    app = Flask(__name__)
    settings = get_settings()

    app.config["SECRET_KEY"] = settings.secret_key
    app.config["APP_SETTINGS"] = settings
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    # Ensure tables exist and seed demo data if in SQLite mode
    init_db()
    if settings.is_sqlite:
        seed_sample_contracts(force=False)

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(contracts_bp)
    app.register_blueprint(rules_bp)
    app.register_blueprint(api_bp)

    # Authentication guard
    @app.before_request
    def global_auth_guard():
        # Allow health checks, static assets, and auth endpoints without authentication
        if request.endpoint and (
            request.endpoint.startswith("auth.")
            or request.endpoint == "api.health_check"
            or request.endpoint == "static"
        ):
            return None

        if not settings.is_auth_enabled:
            g.user = get_current_user()
            return None

        user = session.get("user")
        if not user:
            session["next_url"] = request.url
            return redirect(url_for("auth.login"))

        g.user = user
        return None

    # Global template context
    @app.context_processor
    def inject_globals():
        return {
            "config": settings,
            "current_user": session.get("user") or get_current_user(),
        }

    # Error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template("errors/500.html"), 500

    logger.info(f"Veylo Contract Manager initialized (backend: {settings.effective_database_url})")
    return app


app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    app.run(host="0.0.0.0", port=settings.port, debug=settings.debug)
