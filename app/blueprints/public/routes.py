from decimal import Decimal

from flask import Blueprint, render_template

from app import clock
from app.formatting import month_key

bp = Blueprint("public", __name__)

# The landing-page demo starts from this sample total for the current month.
DEMO_MONTH_TOTAL = Decimal("412.50")


@bp.get("/")
def index() -> str:
    month = clock.current_month()
    return render_template(
        "public/index.html",
        demo_month=month,
        demo_total=DEMO_MONTH_TOTAL,
        demo_totals={month_key(month): f"{DEMO_MONTH_TOTAL:.2f}"},
    )
