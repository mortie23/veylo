import logging
import os
from flask import Flask, render_template

from blueprints.api import api_bp
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

    # Ensure tables exist and seed demo data if in SQLite mode
    init_db()
    if settings.is_sqlite:
        seed_sample_contracts(force=False)

    # Register Blueprints
    app.register_blueprint(contracts_bp)
    app.register_blueprint(rules_bp)
    app.register_blueprint(api_bp)

    # Global template context
    @app.context_processor
    def inject_globals():
        return {
            "config": settings,
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
