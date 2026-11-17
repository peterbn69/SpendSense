import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from dotenv import dotenv_values
from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import make_url, text

from app import create_app
from app.extensions import db as _db

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# Test-only values passed as overrides, so tests never depend on the developer's environment.
# The database URL is a placeholder for tests that build their own app; it is never connected to.
TEST_SETTINGS = {
    "SECRET_KEY": "test-only-not-a-secret",
    "APP_TIMEZONE": "America/Toronto",
    "SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://placeholder@localhost/not-used",
}


def _setting(name: str) -> str | None:
    """Read one setting from the environment, else from .env, without loading the rest of .env."""
    return os.environ.get(name) or dotenv_values(ENV_FILE).get(name)


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _setting("TEST_DATABASE_URL")
    if not url:
        pytest.fail("TEST_DATABASE_URL is not set. Add it to .env (see .env.example).", pytrace=False)

    # Tests empty every table, so never let them point at the development database.
    dev_url = _setting("DATABASE_URL")
    if dev_url:
        test, dev = make_url(url), make_url(dev_url)
        if (test.host, test.port, test.database) == (dev.host, dev.port, dev.database):
            pytest.fail("TEST_DATABASE_URL points at the DATABASE_URL database; use a separate one.", pytrace=False)
    return url


@pytest.fixture
def app(database_url: str) -> Iterator[Flask]:
    app = create_app("testing", {**TEST_SETTINGS, "SQLALCHEMY_DATABASE_URI": database_url})
    yield app
    with app.app_context():
        _db.engine.dispose()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture(scope="session")
def _schema(database_url: str) -> Iterator[None]:
    """Build the tables from the models once per run, on a fresh test database."""
    app = create_app("testing", {**TEST_SETTINGS, "SQLALCHEMY_DATABASE_URI": database_url})
    with app.app_context():
        _db.drop_all()
        _db.create_all()
        yield
        _db.engine.dispose()


@pytest.fixture
def db(app: Flask, _schema: None) -> Iterator[SQLAlchemy]:
    """The database inside an app context; every table is emptied after the test."""
    with app.app_context():
        yield _db
        _db.session.remove()
        quote = _db.engine.dialect.identifier_preparer.quote
        tables = ", ".join(quote(table.name) for table in _db.metadata.sorted_tables)
        if tables:
            with _db.engine.begin() as connection:
                connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
