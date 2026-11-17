from flask import Blueprint, render_template

bp = Blueprint("auth", __name__)


# Placeholders so templates can link with url_for(); M4 and M5 replace them with the real forms.
@bp.get("/register")
def register() -> str:
    return render_template("auth/coming_soon.html", heading="Sign up")


@bp.get("/login")
def login() -> str:
    return render_template("auth/coming_soon.html", heading="Log in")
