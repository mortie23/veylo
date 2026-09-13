from flask import Blueprint

contracts_bp = Blueprint("contracts", __name__)

from blueprints.contracts import routes
