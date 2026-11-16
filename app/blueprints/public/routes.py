from flask import Blueprint, render_template

bp = Blueprint("public", __name__)


@bp.get("/")
def index() -> str:
    return render_template("public/index.html")
