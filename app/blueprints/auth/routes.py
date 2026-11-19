from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user
from werkzeug.wrappers import Response

from app.blueprints.auth.forms import (
    EMAIL_TAKEN_MESSAGE,
    LOGIN_FAILED_MESSAGE,
    LoginForm,
    LogoutForm,
    RegisterForm,
)
from app.services import auth

bp = Blueprint("auth", __name__)


@bp.app_context_processor
def inject_logout_form() -> dict[str, LogoutForm]:
    return {"logout_form": LogoutForm()} if current_user.is_authenticated else {}


@bp.route("/register", methods=["GET", "POST"])
def register() -> str | Response:
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = RegisterForm()
    if form.validate_on_submit():
        try:
            auth.register(form.email.data, form.password.data)
        except auth.EmailTakenError:
            form.email.errors.append(EMAIL_TAKEN_MESSAGE)
        else:
            flash("Your account is ready. Log in to start tracking.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login() -> str | Response:
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    next_url = safe_next_url(request.args.get("next"))
    form = LoginForm()
    if form.validate_on_submit():
        user = auth.authenticate(form.email.data, form.password.data)
        if user is not None:
            session.clear()
            login_user(user)
            return redirect(next_url or url_for("dashboard.index"))
        form.form_errors.append(LOGIN_FAILED_MESSAGE)
    return render_template("auth/login.html", form=form, next_url=next_url)


@bp.post("/logout")
def logout() -> Response:
    # CSRFProtect has already checked the token before this runs.
    logout_user()
    flash("You're logged out.", "info")
    return redirect(url_for("public.index"))


def safe_next_url(target: str | None) -> str | None:
    # Return target if it is a path on this site, else None.
    if not target or not target.startswith("/") or target.startswith("//"):
        return None
    # Browsers treat "\" like "/" and drop tabs and newlines, so "/\evil.com" or "/\t/evil.com" become "//evil.com".
    if "\\" in target or any(ord(char) < 32 or ord(char) == 127 for char in target):
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        return None
    return target
