from datetime import date
from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.wrappers import Response

from app import clock
from app.blueprints.expenses.forms import (
    DATE_INVALID_MESSAGE,
    CategoryFilterForm,
    DeleteForm,
    ExpenseForm,
)
from app.formatting import month_totals_for_script
from app.models import Expense
from app.services import expenses, insights
from app.services.expenses import MAX_EXPENSE_ID

bp = Blueprint("expenses", __name__)

# Ids outside BIGINT never match a route, so they get the 404 page before reaching the database.
_ID = f"<int(min=1, max={MAX_EXPENSE_ID}):expense_id>"


@bp.get("/")
@login_required
def index() -> str:
    # The filter is a GET form, so it works without JS: non-matching expenses are rendered with the hidden
    # attribute, and category-filter.js just toggles that attribute when JS is on.
    filter_form = CategoryFilterForm(request.args)
    if not filter_form.validate():
        filter_form.category.data = ""
    selected = filter_form.category.data
    items = expenses.list_expenses(current_user.id)
    shown = sum(1 for item in items if not selected or item.category == selected)
    return render_template(
        "expenses/list.html",
        expenses=items,
        filter_form=filter_form,
        selected=selected,
        shown=shown,
        unusual=insights.unusual_expenses(current_user.id),
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create() -> str | Response:
    form = ExpenseForm()
    if form.validate_on_submit():
        try:
            expenses.create(current_user.id, form.amount.amount, form.category.data, form.spent_on.data, form.note.data)
        except expenses.ExpenseRuleError as error:
            getattr(form, error.field).errors.append(error.message)
        else:
            flash("Expense added.", "success")
            return redirect(url_for("expenses.index"))
    return _render_form(form, "Add expense", url_for("expenses.create"))


@bp.route(f"/{_ID}/edit", methods=["GET", "POST"])
@login_required
def edit(expense_id: int) -> str | Response:
    expense = expenses.get_expense(current_user.id, expense_id)
    if expense is None:
        abort(404)

    form = ExpenseForm(obj=expense)
    if form.validate_on_submit():
        try:
            updated = expenses.update(
                current_user.id, expense_id, form.amount.amount, form.category.data, form.spent_on.data, form.note.data
            )
        except expenses.ExpenseRuleError as error:
            getattr(form, error.field).errors.append(error.message)
        else:
            if updated is None:
                abort(404)
            flash("Expense updated.", "success")
            return redirect(url_for("expenses.index"))
    return _render_form(form, "Edit expense", url_for("expenses.edit", expense_id=expense_id), expense)


@bp.route(f"/{_ID}/delete", methods=["GET", "POST"])
@login_required
def delete(expense_id: int) -> str | Response:
    expense = expenses.get_expense(current_user.id, expense_id)
    if expense is None:
        abort(404)

    form = DeleteForm()
    # CSRFProtect has already rejected a POST without a valid token, so a GET only shows the question.
    if form.validate_on_submit():
        if not expenses.delete(current_user.id, expense_id):
            abort(404)
        flash("Expense deleted.", "success")
        return redirect(url_for("expenses.index"))
    return render_template("expenses/confirm_delete.html", form=form, expense=expense)


def _render_form(form: ExpenseForm, title: str, action: str, expense: Expense | None = None) -> str:
    totals = expenses.month_totals(current_user.id, exclude_expense_id=expense.id if expense else None)
    shown_day = form.spent_on.data if isinstance(form.spent_on.data, date) else clock.today()
    month = shown_day.replace(day=1)

    # The no-JS text matches what the script shows on load: the month's spending plus a valid typed amount.
    start_total = totals.get(month, Decimal(0))
    try:
        start_total += expenses.parse_amount(form.amount._value())
    except expenses.ExpenseRuleError:
        pass

    return render_template(
        "expenses/form.html",
        form=form,
        title=title,
        action=action,
        expense=expense,
        month_totals=month_totals_for_script(totals),
        month=month,
        start_total=start_total,
        validation=_validation_rules(),
    )


def _validation_rules() -> dict[str, object]:
    # The server's rules and messages, handed to live-validation.js so the hints say exactly what the server would.
    return {
        "amount": {
            "required": expenses.AMOUNT_REQUIRED_MESSAGE,
            "format": expenses.AMOUNT_FORMAT_MESSAGE,
            "positive": expenses.AMOUNT_POSITIVE_MESSAGE,
            "places": expenses.AMOUNT_PLACES_MESSAGE,
            "limit": expenses.AMOUNT_LIMIT_MESSAGE,
        },
        "category": {"required": expenses.CATEGORY_MESSAGE},
        "spent_on": {
            "required": expenses.DATE_REQUIRED_MESSAGE,
            "invalid": DATE_INVALID_MESSAGE,
            "future": expenses.DATE_FUTURE_MESSAGE,
            "too_early": expenses.DATE_TOO_EARLY_MESSAGE,
            "min": expenses.MIN_DATE.isoformat(),
            "max": clock.today().isoformat(),
        },
        "note": {"too_long": expenses.NOTE_LENGTH_MESSAGE, "max_length": expenses.NOTE_MAX_LENGTH},
    }
