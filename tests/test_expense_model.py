"""The expenses table rejects bad rows at the database, even if the form and service layers have a bug."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, select
from sqlalchemy.exc import DataError, IntegrityError

from app import categories
from app.models import Expense, User


def _insert(database: SQLAlchemy, user: User, **fields: object) -> Expense:
    values: dict[str, object] = {"amount": Decimal("12.34"), "category": "dining", "spent_on": date(2026, 10, 5)}
    values.update(fields)
    expense = Expense(user_id=user.id, **values)
    database.session.add(expense)
    database.session.flush()
    return expense


def test_insert_gets_id_defaults_and_timestamps(db: SQLAlchemy, user_a: User) -> None:
    expense = _insert(db, user_a)
    db.session.refresh(expense)
    assert expense.id >= 1
    assert expense.note == ""
    assert isinstance(expense.created_at, datetime) and expense.created_at.tzinfo is not None
    assert expense.updated_at == expense.created_at


def test_amount_round_trips_as_decimal(db: SQLAlchemy, user_a: User) -> None:
    expense = _insert(db, user_a, amount=Decimal("1234567890.12"))
    db.session.expire_all()
    stored = db.session.scalar(select(Expense.amount).where(Expense.id == expense.id))
    assert stored == Decimal("1234567890.12")
    assert isinstance(stored, Decimal)


@pytest.mark.parametrize("amount", [Decimal("-0.01"), Decimal("0"), Decimal("-50.00")])
def test_non_positive_amount_rejected(db: SQLAlchemy, user_a: User, amount: Decimal) -> None:
    with pytest.raises(IntegrityError, match="ck_expenses_amount_positive"):
        _insert(db, user_a, amount=amount)


def test_amount_too_large_for_numeric_12_2_rejected(db: SQLAlchemy, user_a: User) -> None:
    with pytest.raises(DataError):
        _insert(db, user_a, amount=Decimal("10000000000.00"))


@pytest.mark.parametrize("category", ["rent", "Dining", "", "food"])
def test_unknown_category_rejected(db: SQLAlchemy, user_a: User, category: str) -> None:
    with pytest.raises(IntegrityError, match="ck_expenses_category_known"):
        _insert(db, user_a, category=category)


@pytest.mark.parametrize("category", categories.KEYS)
def test_every_known_category_accepted(db: SQLAlchemy, user_a: User, category: str) -> None:
    assert _insert(db, user_a, category=category).id


@pytest.mark.parametrize("field", ["amount", "category", "spent_on"])
def test_required_fields(db: SQLAlchemy, user_a: User, field: str) -> None:
    with pytest.raises(IntegrityError, match=field):
        _insert(db, user_a, **{field: None})


def test_note_longer_than_200_rejected(db: SQLAlchemy, user_a: User) -> None:
    with pytest.raises(DataError):
        _insert(db, user_a, note="x" * 201)


def test_note_of_200_accepted(db: SQLAlchemy, user_a: User) -> None:
    assert _insert(db, user_a, note="x" * 200).id


def test_unknown_user_rejected(db: SQLAlchemy) -> None:
    with pytest.raises(IntegrityError, match="fk_expenses_user_id_users"):
        db.session.add(Expense(user_id=999_999, amount=Decimal("1.00"), category="other", spent_on=date(2026, 1, 1)))
        db.session.flush()


def test_deleting_a_user_deletes_their_expenses(db: SQLAlchemy, user_a: User, user_b: User) -> None:
    _insert(db, user_a)
    kept = _insert(db, user_b)
    db.session.commit()
    db.session.delete(user_a)
    db.session.commit()
    assert db.session.scalars(select(Expense.id)).all() == [kept.id]


def test_updated_at_changes_on_update(db: SQLAlchemy, user_a: User) -> None:
    expense = _insert(db, user_a)
    db.session.commit()
    created = expense.created_at

    expense.note = "changed"
    db.session.commit()
    assert expense.updated_at > created
    assert expense.created_at == created


def test_user_and_date_index_exists(db: SQLAlchemy) -> None:
    indexes = {index["name"]: index["column_names"] for index in inspect(db.engine).get_indexes("expenses")}
    assert indexes == {"ix_expenses_user_id_spent_on": ["user_id", "spent_on"]}
