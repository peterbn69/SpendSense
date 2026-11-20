from collections.abc import Mapping
from typing import Any

from flask import Flask, render_template
from werkzeug.exceptions import HTTPException

# Imported for its side effect: puts the models' tables on db.metadata for Flask-Migrate.
from app import models
from app.blueprints.auth import bp as auth_bp
from app.blueprints.dashboard import bp as dashboard_bp
from app.blueprints.expenses import bp as expenses_bp
from app.blueprints.public import bp as public_bp
from app.cli import register_commands
from app.config import get_config_class, settings_from_env, validate_settings
from app.extensions import csrf, db, login_manager, migrate
from app.formatting import register_filters
from app.services import auth


def create_app(config_name: str | None = None, overrides: Mapping[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(get_config_class(config_name))
    app.config.update(settings_from_env())
    if overrides:
        app.config.update(overrides)
    validate_settings(app.config)

    _init_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    register_commands(app)
    register_filters(app)
    return app


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.user_loader(auth.load_user)


def _register_blueprints(app: Flask) -> None:
    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(expenses_bp, url_prefix="/expenses")


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(error: HTTPException) -> tuple[str, int]:
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error: HTTPException) -> tuple[str, int]:
        db.session.rollback()
        return render_template("errors/500.html"), 500
