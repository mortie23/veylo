from flask import Blueprint

rules_bp = Blueprint("rules", __name__)

from blueprints.rules import routes
