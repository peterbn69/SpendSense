import logging
from collections.abc import Mapping
from typing import Any

from flask import Flask, Response, abort, render_template, request
from flask.logging import default_handler
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

from app import models  # noqa: F401
from app.blueprints.auth import bp as auth_bp
from app.blueprints.dashboard import bp as dashboard_bp
from app.blueprints.expenses import bp as expenses_bp
from app.blueprints.public import bp as public_bp
from app.cli import register_commands
from app.config import get_config_class, settings_from_env, validate_settings
from app.extensions import csrf, db, limiter, login_manager, migrate
from app.formatting import register_filters
from app.services import auth

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Friendly wording for HTTP errors without a page of their own
ERROR_PAGES: dict[int, tuple[str, str]] = {
    405: ("That doesn't work here", "That page can't be used this way. Please use the links and buttons on the site."),
    413: ("That was too much", "That submission was too large to accept. Please shorten it and try again."),
    429: ("Too many attempts", "Please wait a minute, then try again."),
}
DEFAULT_ERROR_PAGE = ("Something went wrong", "That request didn't work. Please go back and try again.")

# Headers that cost nothing and close common holes
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}


def create_app(config_name: str | None = None, overrides: Mapping[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(get_config_class(config_name))
    app.config.update(settings_from_env())
    if overrides:
        app.config.update(overrides)
    validate_settings(app.config)

    _configure_logging(app)
    _init_extensions(app)
    _register_blueprints(app)
    _register_request_hooks(app)
    _register_error_handlers(app)
    register_commands(app)
    register_filters(app)
    return app


def _configure_logging(app: Flask) -> None:
    default_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    app.logger.setLevel(str(app.config["LOG_LEVEL"]).upper())


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.user_loader(auth.load_user)


def _register_blueprints(app: Flask) -> None:
    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(expenses_bp, url_prefix="/expenses")


def _register_request_hooks(app: Flask) -> None:
    @app.before_request
    def reject_nul_characters() -> None:
        # PostgreSQL text can't hold a NUL character, so such input would fail at the database as a 500.
        # No real form value contains one; refuse the request up front instead.
        for values in (request.args, request.form):
            if any("\x00" in value for value in values.values() if isinstance(value, str)):
                abort(400)
            if any("\x00" in key for key in values):
                abort(400)

    @app.after_request
    def add_security_headers(response: Response) -> Response:
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(400)
    def bad_request(error: HTTPException) -> tuple[str, int]:
        csrf_failed = isinstance(error, CSRFError)
        if csrf_failed:
            app.logger.warning("Rejected %s %s: missing or expired CSRF token", request.method, request.path)
        return render_template("errors/400.html", csrf_failed=csrf_failed), 400

    @app.errorhandler(403)
    def forbidden(error: HTTPException) -> tuple[str, int]:
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error: HTTPException) -> tuple[str, int]:
        return render_template("errors/404.html"), 404

    @app.errorhandler(429)
    def too_many_requests(error: HTTPException) -> tuple[str, int]:
        app.logger.warning("Rate limit hit: %s %s from %s", request.method, request.path, request.remote_addr)
        heading, message = ERROR_PAGES[429]
        return render_template("errors/error.html", heading=heading, message=message), 429

    @app.errorhandler(HTTPException)
    def other_http_error(error: HTTPException) -> tuple[str, int, list[tuple[str, str]]] | HTTPException:
        code = error.code or 500
        if code < 400:
            return error  # redirects and the like pass through unchanged
        heading, message = ERROR_PAGES.get(code, DEFAULT_ERROR_PAGE)
        # Keep the error's own headers (e.g. Allow on a 405), but not its plain-text Content-Type.
        headers = [(name, value) for name, value in error.get_headers() if name.lower() != "content-type"]
        return render_template("errors/error.html", heading=heading, message=message), code, headers

    @app.errorhandler(500)
    def internal_error(error: HTTPException) -> tuple[str, int]:
        # Flask has already logged the exception with its traceback.
        db.session.rollback()
        return render_template("errors/500.html"), 500
