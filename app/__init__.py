from collections.abc import Mapping
from typing import Any

from flask import Flask

from app.blueprints.auth import bp as auth_bp
from app.blueprints.dashboard import bp as dashboard_bp
from app.blueprints.expenses import bp as expenses_bp
from app.blueprints.public import bp as public_bp
from app.config import get_config_class, settings_from_env, validate_settings


def create_app(config_name: str | None = None, overrides: Mapping[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(get_config_class(config_name))
    app.config.update(settings_from_env())
    if overrides:
        app.config.update(overrides)
    validate_settings(app.config)

    _register_blueprints(app)
    return app


def _register_blueprints(app: Flask) -> None:
    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(expenses_bp, url_prefix="/expenses")
