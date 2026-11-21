from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.services import insights

bp = Blueprint("dashboard", __name__)


@bp.get("/")
@login_required
def index() -> str:
    return render_template("dashboard/index.html", dashboard=insights.dashboard(current_user.id))
