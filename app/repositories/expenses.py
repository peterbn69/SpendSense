from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import Date, delete, func, select

from app.extensions import db
from app.models import Expense


class NewExpense(NamedTuple):
    amount: Decimal
    category: str
    spent_on: date
    note: str = ""


def add(user_id: int, amount: Decimal, category: str, spent_on: date, note: str = "") -> Expense:
    # Flush, so the expense gets an id and a constraint violation fails here.
    expense = Expense(user_id=user_id, amount=amount, category=category, spent_on=spent_on, note=note)  # pyrefly: ignore[unexpected-keyword]
    db.session.add(expense)
    db.session.flush()
    return expense


def add_many(user_id: int, rows: Iterable[NewExpense]) -> int:
    expenses = [Expense(user_id=user_id, **row._asdict()) for row in rows]  # pyrefly: ignore[unexpected-keyword]
    db.session.add_all(expenses)
    db.session.flush()
    return len(expenses)


def get(user_id: int, expense_id: int) -> Expense | None:
    return db.session.scalar(select(Expense).where(Expense.id == expense_id, Expense.user_id == user_id))


def list_for_user(user_id: int) -> list[Expense]:
    query = select(Expense).where(Expense.user_id == user_id).order_by(Expense.spent_on.desc(), Expense.id.desc())
    return list(db.session.scalars(query))


def count_for_user(user_id: int) -> int:
    return db.session.scalar(select(func.count()).select_from(Expense).where(Expense.user_id == user_id)) or 0


def delete_all_for_user(user_id: int) -> int:
    result = db.session.execute(delete(Expense).where(Expense.user_id == user_id))
    return result.rowcount


def update(user_id: int, expense_id: int, amount: Decimal, category: str, spent_on: date, note: str) -> Expense | None:
    # Change the user's expense and flush; None if it doesn't exist or belongs to someone else.
    expense = get(user_id, expense_id)
    if expense is None:
        return None
    expense.amount, expense.category, expense.spent_on, expense.note = amount, category, spent_on, note
    db.session.flush()
    return expense


def delete_one(user_id: int, expense_id: int) -> bool:
    # Delete the user's expense; False if it doesn't exist or belongs to someone else.
    result = db.session.execute(delete(Expense).where(Expense.id == expense_id, Expense.user_id == user_id))
    return result.rowcount == 1


def monthly_totals(
    user_id: int, exclude_expense_id: int | None = None, since: date | None = None
) -> dict[date, Decimal]:
    # The user's spending per month, keyed by the first day of the month; months with no expenses are absent.
    month = func.date_trunc("month", Expense.spent_on).cast(Date)
    query = select(month, func.sum(Expense.amount)).where(Expense.user_id == user_id).group_by(month)
    if exclude_expense_id is not None:
        query = query.where(Expense.id != exclude_expense_id)
    if since is not None:
        query = query.where(Expense.spent_on >= since)
    return {first_day: total for first_day, total in db.session.execute(query)}


def category_totals(user_id: int, first_day: date, last_day: date) -> dict[str, Decimal]:
    # The user's spending per category between two days, inclusive; categories with no expenses are absent.
    query = (
        select(Expense.category, func.sum(Expense.amount))
        .where(Expense.user_id == user_id, Expense.spent_on >= first_day, Expense.spent_on <= last_day)
        .group_by(Expense.category)
    )
    return {category: total for category, total in db.session.execute(query)}


def first_spent_on(user_id: int) -> date | None:
    # The date of the user's earliest expense, or None if they have none.
    return db.session.scalar(select(func.min(Expense.spent_on)).where(Expense.user_id == user_id))


def monthly_category_totals(user_id: int, before: date) -> dict[tuple[str, date], Decimal]:
    # Spending per (category, first day of month) for expenses before `before`; empty combinations are absent.
    month = func.date_trunc("month", Expense.spent_on).cast(Date)
    query = (
        select(Expense.category, month, func.sum(Expense.amount))
        .where(Expense.user_id == user_id, Expense.spent_on < before)
        .group_by(Expense.category, month)
    )
    return {(category, first_day): total for category, first_day, total in db.session.execute(query)}


def amounts_for_user(user_id: int) -> list[tuple[int, str, Decimal]]:
    # (id, category, amount) for every one of the user's expenses: the input for anomaly flags.
    query = select(Expense.id, Expense.category, Expense.amount).where(Expense.user_id == user_id)
    return [(expense_id, category, amount) for expense_id, category, amount in db.session.execute(query)]


def list_since(user_id: int, since: date) -> list[Expense]:
    # The user's expenses on or after `since`, newest first.
    query = (
        select(Expense)
        .where(Expense.user_id == user_id, Expense.spent_on >= since)
        .order_by(Expense.spent_on.desc(), Expense.id.desc())
    )
    return list(db.session.scalars(query))
