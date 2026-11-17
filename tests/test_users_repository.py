import pytest
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError

from app.repositories import users


def test_add_assigns_id(db: SQLAlchemy) -> None:
    user = users.add("a@example.com", "hash")
    assert user.id >= 1
    assert user.email == "a@example.com"
    assert user.password_hash == "hash"


def test_get_by_id(db: SQLAlchemy) -> None:
    user = users.add("a@example.com", "hash")
    assert users.get_by_id(user.id) is user


def test_get_by_id_missing_is_none(db: SQLAlchemy) -> None:
    assert users.get_by_id(999_999) is None


def test_get_by_email(db: SQLAlchemy) -> None:
    user = users.add("a@example.com", "hash")
    users.add("b@example.com", "hash")
    assert users.get_by_email("a@example.com") is user


def test_get_by_email_is_exact(db: SQLAlchemy) -> None:
    # Lowercasing is the service's job; the repository does not guess.
    users.add("a@example.com", "hash")
    assert users.get_by_email("A@example.com") is None
    assert users.get_by_email("missing@example.com") is None


def test_add_duplicate_email_fails_at_add(db: SQLAlchemy) -> None:
    users.add("a@example.com", "hash")
    with pytest.raises(IntegrityError):
        users.add("a@example.com", "other")


def test_add_does_not_commit(db: SQLAlchemy) -> None:
    users.add("a@example.com", "hash")
    db.session.rollback()
    assert users.get_by_email("a@example.com") is None
