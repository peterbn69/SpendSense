from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import delete, func, select

from app.extensions import db
from app.models import Expense


class NewExpense(NamedTuple):
    amount: Decimal
    category: str
    spent_on: date
    note: str = ""


def add(user_id: int, amount: Decimal, category: str, spent_on: date, note: str = "") -> Expense:
    # Flush, so the expense gets an id and a constraint violation fails here.
    expense = Expense(user_id=user_id, amount=amount, category=category, spent_on=spent_on, note=note)
    db.session.add(expense)
    db.session.flush()
    return expense


def add_many(user_id: int, rows: Iterable[NewExpense]) -> int:
    expenses = [Expense(user_id=user_id, **row._asdict()) for row in rows]
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
