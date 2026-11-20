from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from werkzeug.wrappers import Response

from app.blueprints.expenses.forms import DeleteForm, ExpenseForm
from app.services import expenses
from app.services.expenses import MAX_EXPENSE_ID

bp = Blueprint("expenses", __name__)

# Ids outside BIGINT never match a route, so they get the 404 page before reaching the database.
_ID = f"<int(min=1, max={MAX_EXPENSE_ID}):expense_id>"


@bp.get("/")
@login_required
def index() -> str:
    return render_template("expenses/list.html", expenses=expenses.list_expenses(current_user.id))


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
    return render_template("expenses/form.html", form=form, title="Add expense", action=url_for("expenses.create"))


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
    action = url_for("expenses.edit", expense_id=expense_id)
    return render_template("expenses/form.html", form=form, title="Edit expense", action=action, expense=expense)


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
