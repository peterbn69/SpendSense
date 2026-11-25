import os
import re
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

import pytest
from dotenv import dotenv_values
from flask import Flask, g, request_started
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import make_url, text
from werkzeug.test import TestResponse

from app import clock, create_app
from app.extensions import db as _db
from app.models import User
from app.services import auth

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# Test-only values passed as overrides, so tests never depend on the developer's environment.
# The database URL is a placeholder for tests that build their own app; it is never connected to.
TEST_SETTINGS = {
    "SECRET_KEY": "test-only-not-a-secret-0123456789abcdef",
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
    request_started.connect(_empty_g, app, weak=False)
    yield app
    request_started.disconnect(_empty_g, app)
    with app.app_context():
        _db.engine.dispose()


def _empty_g(sender: Flask, **extra: object) -> None:
    """Start every request with an empty g, as in production.

    The db fixture keeps one app context open and test requests reuse it, so without this, values
    cached in g (Flask-Login's current user, Flask-WTF's CSRF token) would leak from one request to the next.
    """
    for key in list(g):
        g.pop(key)


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


PASSWORD = "correct horse"


def csrf_token(client: FlaskClient, path: str) -> str:
    """GET a page and return the CSRF token from its form."""
    html = client.get(path).get_data(as_text=True)
    match = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', html)
    assert match, f"no CSRF token on {path}"
    return match.group(1)


def login(client: FlaskClient, email: str, password: str = PASSWORD, next_url: str | None = None) -> TestResponse:
    data = {"email": email, "password": password, "csrf_token": csrf_token(client, "/auth/login")}
    query = {} if next_url is None else {"next": next_url}
    return client.post("/auth/login", query_string=query, data=data)


@pytest.fixture
def user_a(db: SQLAlchemy) -> User:
    return auth.register("a@example.com", PASSWORD)


@pytest.fixture
def user_b(db: SQLAlchemy) -> User:
    return auth.register("b@example.com", PASSWORD)


@pytest.fixture
def fake_today(monkeypatch: pytest.MonkeyPatch) -> Callable[[date], None]:
    """Call fake_today(date(...)) to fix clock.today() (and so clock.current_month()) for the test."""

    def set_today(day: date) -> None:
        monkeypatch.setattr(clock, "today", lambda: day)

    return set_today
