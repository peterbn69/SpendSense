from flask import Blueprint, flash, redirect, render_template, url_for
from werkzeug.wrappers import Response

from app.blueprints.auth.forms import EMAIL_TAKEN_MESSAGE, RegisterForm
from app.services import auth

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=["GET", "POST"])
def register() -> str | Response:
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


@bp.get("/login")
def login() -> str:
    return render_template("auth/coming_soon.html", heading="Log in")
