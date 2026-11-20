from datetime import date
from decimal import Decimal

from flask_sqlalchemy import SQLAlchemy

from app.models import User
from app.repositories import expenses
from app.repositories.expenses import NewExpense


def _add(user: User, spent_on: date = date(2026, 10, 5), amount: str = "10.00") -> int:
    return expenses.add(user.id, Decimal(amount), "groceries", spent_on, "Market").id


def test_add_assigns_id_and_fields(db: SQLAlchemy, user_a: User) -> None:
    expense = expenses.add(user_a.id, Decimal("10.50"), "groceries", date(2026, 10, 5), "Market")
    assert expense.id >= 1
    assert (expense.user_id, expense.amount, expense.category, expense.spent_on, expense.note) == (
        user_a.id, Decimal("10.50"), "groceries", date(2026, 10, 5), "Market",
    )


def test_add_does_not_commit(db: SQLAlchemy, user_a: User) -> None:
    _add(user_a)
    db.session.rollback()
    assert expenses.count_for_user(user_a.id) == 0


def test_get_own_expense(db: SQLAlchemy, user_a: User) -> None:
    expense_id = _add(user_a)
    expense = expenses.get(user_a.id, expense_id)
    assert expense is not None and expense.id == expense_id


def test_get_someone_elses_expense_is_none(db: SQLAlchemy, user_a: User, user_b: User) -> None:
    expense_id = _add(user_a)
    assert expenses.get(user_b.id, expense_id) is None


def test_get_missing_is_none(db: SQLAlchemy, user_a: User) -> None:
    assert expenses.get(user_a.id, 999_999) is None


def test_list_is_own_newest_first(db: SQLAlchemy, user_a: User, user_b: User) -> None:
    older = _add(user_a, date(2026, 9, 1))
    first_same_day = _add(user_a, date(2026, 10, 5))
    second_same_day = _add(user_a, date(2026, 10, 5))
    _add(user_b, date(2026, 10, 6))
    assert [e.id for e in expenses.list_for_user(user_a.id)] == [second_same_day, first_same_day, older]


def test_list_empty(db: SQLAlchemy, user_a: User) -> None:
    assert expenses.list_for_user(user_a.id) == []


def test_add_many_and_count(db: SQLAlchemy, user_a: User, user_b: User) -> None:
    rows = [
        NewExpense(Decimal("1.00"), "other", date(2026, 10, 1)),
        NewExpense(Decimal("2.00"), "dining", date(2026, 10, 2), "Lunch"),
    ]
    assert expenses.add_many(user_a.id, rows) == 2
    assert expenses.count_for_user(user_a.id) == 2
    assert expenses.count_for_user(user_b.id) == 0
    assert [e.note for e in expenses.list_for_user(user_a.id)] == ["Lunch", ""]


def test_delete_all_only_touches_that_user(db: SQLAlchemy, user_a: User, user_b: User) -> None:
    _add(user_a)
    _add(user_a)
    kept = _add(user_b)
    assert expenses.delete_all_for_user(user_a.id) == 2
    assert expenses.count_for_user(user_a.id) == 0
    assert [e.id for e in expenses.list_for_user(user_b.id)] == [kept]
