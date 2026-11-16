from collections.abc import Iterator

import pytest
from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, String, Table, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.extensions import db


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
