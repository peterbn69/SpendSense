from collections.abc import Iterator
from datetime import datetime

import pytest
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, String, Table, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.schema import CreateIndex, CreateTable

from app.extensions import db
from app.models import User


@pytest.fixture
def scratch_tables() -> Iterator[tuple[Table, Table]]:
    """Two throwaway tables on the app's metadata, removed afterwards so they never reach a migration."""
    owners = Table("owners", db.metadata, Column("id", BigInteger, primary_key=True))
    widgets = Table(
        "widgets",
        db.metadata,
        Column("id", BigInteger, primary_key=True),
        Column("owner_id", BigInteger, ForeignKey("owners.id"), nullable=False),
        Column("code", String(10), nullable=False),
        Column("size", String(10), nullable=False),
        UniqueConstraint("owner_id", "code"),
        CheckConstraint("code = lower(code)", name="code_lowercase"),
        Index(None, "owner_id", "size"),
    )
    try:
        yield owners, widgets
    finally:
        db.metadata.remove(widgets)
        db.metadata.remove(owners)


def _ddl(element: object) -> str:
    return str(element.compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]


def test_constraint_names_follow_convention(scratch_tables: tuple[Table, Table]) -> None:
    _, widgets = scratch_tables
    ddl = _ddl(CreateTable(widgets))
    assert "CONSTRAINT pk_widgets PRIMARY KEY" in ddl
    assert "CONSTRAINT fk_widgets_owner_id_owners FOREIGN KEY" in ddl
    assert "CONSTRAINT uq_widgets_owner_id_code UNIQUE" in ddl
    assert "CONSTRAINT ck_widgets_code_lowercase CHECK" in ddl


def test_index_name_follows_convention(scratch_tables: tuple[Table, Table]) -> None:
    _, widgets = scratch_tables
    (index,) = widgets.indexes
    assert _ddl(CreateIndex(index)).startswith("CREATE INDEX ix_widgets_owner_id_size ")


def test_models_share_the_named_metadata() -> None:
    assert db.Model.metadata is db.metadata
    assert db.metadata.naming_convention["ck"] == "ck_%(table_name)s_%(constraint_name)s"


# --- users table: the database rejects bad rows even if the service layer has a bug ---


def _insert_user(database: SQLAlchemy, email: str, password_hash: str | None = "hash") -> User:
    user = User(email=email, password_hash=password_hash)
    database.session.add(user)
    database.session.flush()
    return user


def test_user_gets_id_and_created_at(db: SQLAlchemy) -> None:
    user = _insert_user(db, "a@example.com")
    assert user.id >= 1
    assert isinstance(user.created_at, datetime)
    assert user.created_at.tzinfo is not None


@pytest.mark.parametrize("email", ["A@example.com", "a@EXAMPLE.com", "ÉMILE@example.com"])
def test_uppercase_email_rejected(db: SQLAlchemy, email: str) -> None:
    with pytest.raises(IntegrityError, match="ck_users_email_lowercase"):
        _insert_user(db, email)


def test_duplicate_email_rejected(db: SQLAlchemy) -> None:
    _insert_user(db, "a@example.com")
    with pytest.raises(IntegrityError, match="uq_users_email"):
        _insert_user(db, "a@example.com")


def test_email_longer_than_254_rejected(db: SQLAlchemy) -> None:
    with pytest.raises(DataError):
        _insert_user(db, "a" * 243 + "@example.com")  # 255 characters


def test_email_of_254_accepted(db: SQLAlchemy) -> None:
    assert _insert_user(db, "a" * 242 + "@example.com").id


def test_missing_password_hash_rejected(db: SQLAlchemy) -> None:
    with pytest.raises(IntegrityError, match="password_hash"):
        _insert_user(db, "a@example.com", password_hash=None)
