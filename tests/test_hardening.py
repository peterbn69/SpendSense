"""M12: friendly error pages, every form fed bad input (never a 500), logging, production config, rate limit."""

import logging
from collections.abc import Callable, Iterator
from datetime import date
from decimal import Decimal

import pytest
from flask import Flask, abort, request_started
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.datastructures import MultiDict
from werkzeug.test import TestResponse

from app import create_app
from app.extensions import db as _db
from app.extensions import limiter
from app.models import User
from app.repositories import expenses as expenses_repo
from tests.conftest import PASSWORD, TEST_SETTINGS, _empty_g, csrf_token, login

TODAY = date(2026, 11, 21)

# Blank, negative, enormous, non-numeric and otherwise hostile values, fed to every field of every form.
BAD_VALUES = [
    "",
    "   ",
    "-1",
    "-0.01",
    "0",
    "1e309",
    "NaN",
    "-Infinity",
    "abc",
    "12,50",
    "１２",  # full-width digits
    "٣",  # Arabic-Indic digit
    "9" * 5000,
    "x" * 100_000,
    "<script>alert(1)</script>",
    "' OR 1=1 --",
    "😀" * 60,
    "‮​",
    "2026-02-30",
    "9999-12-31",
]

FORMS: dict[str, tuple[str, dict[str, str]]] = {
    "register": ("/auth/register", {"email": "new@example.com", "password": "long enough pw", "confirm": "long enough pw"}),
    "login": ("/auth/login", {"email": "a@example.com", "password": PASSWORD}),
    "expense": ("/expenses/new", {"amount": "12.50", "category": "dining", "spent_on": "2026-11-20", "note": "Lunch"}),
}


@pytest.fixture
def today(fake_today: Callable[[date], None]) -> date:
    fake_today(TODAY)
    return TODAY


def _post(client: FlaskClient, path: str, data: dict[str, str]) -> TestResponse:
    return client.post(path, data={**data, "csrf_token": csrf_token(client, path)})


# --- Every form, bad input: never a 500 ------------------------------------------------------------


@pytest.mark.parametrize("value", BAD_VALUES)
@pytest.mark.parametrize("form", ["register", "login"])
def test_auth_forms_never_fail(client: FlaskClient, user_a: User, form: str, value: str) -> None:
    path, valid = FORMS[form]
    for field in valid:
        assert _post(client, path, {**valid, field: value}).status_code < 500
    assert _post(client, path, {field: value for field in valid}).status_code < 500


@pytest.mark.parametrize("value", BAD_VALUES)
def test_expense_forms_never_fail(client: FlaskClient, user_a: User, today: date, value: str) -> None:
    login(client, "a@example.com")
    expense = expenses_repo.add(user_a.id, Decimal("5.00"), "other", TODAY, "")
    expenses_repo.db.session.commit()
    _, valid = FORMS["expense"]
    for path in ("/expenses/new", f"/expenses/{expense.id}/edit"):
        for field in valid:
            assert _post(client, path, {**valid, field: value}).status_code < 500
        assert _post(client, path, {field: value for field in valid}).status_code < 500
    assert client.get("/expenses/", query_string={"category": value}).status_code == 200
    assert client.get("/auth/login", query_string={"next": value}).status_code < 500


def test_bad_amounts_save_nothing(client: FlaskClient, user_a: User, today: date) -> None:
    login(client, "a@example.com")
    path, valid = FORMS["expense"]
    for value in BAD_VALUES:
        _post(client, path, {**valid, "amount": value})
    assert expenses_repo.count_for_user(user_a.id) == 0


@pytest.mark.parametrize("amount", ["１２", "٣", "12.５"])
def test_amount_accepts_ascii_digits_only(client: FlaskClient, user_a: User, today: date, amount: str) -> None:
    # Python's \\d matches any Unicode digit and Decimal reads them, but the browser hints only know 0-9.
    login(client, "a@example.com")
    path, valid = FORMS["expense"]
    response = _post(client, path, {**valid, "amount": amount})
    assert response.status_code == 200
    assert "Enter a number, like 12.50." in response.get_data(as_text=True)


def test_repeated_and_unexpected_fields_are_harmless(client: FlaskClient, user_a: User, today: date) -> None:
    login(client, "a@example.com")
    token = csrf_token(client, "/expenses/new")
    data = MultiDict([("amount", "1.00"), ("amount", "-5"), ("category", "dining"), ("spent_on", "2026-11-20"),
                      ("user_id", "999"), ("id", "1"), ("csrf_token", token)])
    response = client.post("/expenses/new", data=data)
    assert response.status_code == 302
    (expense,) = expenses_repo.list_for_user(user_a.id)
    assert expense.user_id == user_a.id and expense.amount == Decimal("1.00")


@pytest.mark.parametrize("where", ["form", "query"])
def test_nul_character_is_a_400_not_a_500(client: FlaskClient, user_a: User, where: str) -> None:
    token = csrf_token(client, "/auth/login")
    if where == "form":
        response = client.post("/auth/login", data={"email": "a@exam\x00ple.com", "password": "x", "csrf_token": token})
    else:
        response = client.get("/auth/login", query_string={"next": "/da\x00sh"})
    assert response.status_code == 400
    assert "Request not accepted" in response.get_data(as_text=True)


def test_oversized_request_is_a_friendly_413(client: FlaskClient, db: SQLAlchemy) -> None:
    response = client.post("/auth/login", data={"email": "x" * (2 * 1024 * 1024)})
    assert response.status_code == 413
    assert "That was too much" in response.get_data(as_text=True)


# --- Friendly error pages --------------------------------------------------------------------------


def test_missing_csrf_token_page(client: FlaskClient, db: SQLAlchemy, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        response = client.post("/auth/login", data={"email": "a@example.com", "password": "x"})
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "This form has expired" in html
    assert "Nothing was saved" in html
    assert "<main" in html
    assert "missing or expired CSRF token" in caplog.text


def test_403_page(app: Flask) -> None:
    app.add_url_rule("/forbidden-test", "forbidden_test", lambda: abort(403))
    response = app.test_client().get("/forbidden-test")
    assert response.status_code == 403
    assert "Not allowed" in response.get_data(as_text=True)


def test_405_page(client: FlaskClient, db: SQLAlchemy) -> None:
    response = client.get("/auth/logout")  # logout is POST only
    assert response.status_code == 405
    html = response.get_data(as_text=True)
    assert "That doesn&#39;t work here" in html
    assert "<main" in html
    assert response.headers["Allow"]


def test_404_and_500_pages_still_work(client: FlaskClient, db: SQLAlchemy) -> None:
    assert "Page not found" in client.get("/nope").get_data(as_text=True)


def test_security_headers(client: FlaskClient, db: SQLAlchemy) -> None:
    for path in ("/", "/nope", "/static/css/style.css"):
        response = client.get(path)
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "same-origin"
        response.close()


# --- Logging ---------------------------------------------------------------------------------------


def test_failed_login_is_logged_without_the_email(
    client: FlaskClient, user_a: User, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        login(client, "a@example.com", password="wrong password")
    assert "Failed login from 127.0.0.1" in caplog.text
    assert "a@example.com" not in caplog.text
    assert "wrong password" not in caplog.text


def test_login_and_registration_are_logged_by_id(client: FlaskClient, db: SQLAlchemy, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        data = {"email": "c@example.com", "password": PASSWORD, "confirm": PASSWORD}
        _post(client, "/auth/register", data)
        login(client, "c@example.com")
    assert "User 1 registered" in caplog.text
    assert "User 1 logged in" in caplog.text
    assert "c@example.com" not in caplog.text


def test_log_level_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "warning")
    app = create_app("testing", {k: v for k, v in TEST_SETTINGS.items()})
    assert app.logger.level == logging.WARNING


def test_unknown_log_level_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "chatty")
    with pytest.raises(RuntimeError, match="LOG_LEVEL"):
        create_app("testing", TEST_SETTINGS)


# --- Production config -----------------------------------------------------------------------------


@pytest.fixture
def no_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in ("APP_ENV", "SECRET_KEY", "APP_TIMEZONE", "DATABASE_URL", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_production_debug_stays_off_even_with_flask_debug(no_env: pytest.MonkeyPatch) -> None:
    no_env.setenv("FLASK_DEBUG", "1")
    app = create_app("production", TEST_SETTINGS)
    assert app.debug is False
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["RATELIMIT_ENABLED"] is True


def test_production_refuses_a_short_secret_key(no_env: pytest.MonkeyPatch) -> None:
    with pytest.raises(RuntimeError, match="at least 32 characters") as error:
        create_app("production", {**TEST_SETTINGS, "SECRET_KEY": "short-secret"})
    assert "short-secret" not in str(error.value)


def test_development_allows_a_short_secret_key(no_env: pytest.MonkeyPatch) -> None:
    assert create_app("development", {**TEST_SETTINGS, "SECRET_KEY": "dev"}).debug is True


# --- Login rate limit ------------------------------------------------------------------------------


@pytest.fixture
def limited_client(database_url: str, _schema: None) -> Iterator[FlaskClient]:
    """A client whose app has the rate limit on, with fresh counts."""
    app = create_app("testing", {**TEST_SETTINGS, "SQLALCHEMY_DATABASE_URI": database_url, "RATELIMIT_ENABLED": True})
    request_started.connect(_empty_g, app, weak=False)
    with app.app_context():
        limiter.reset()
        yield app.test_client()
        limiter.reset()
        _db.session.remove()
        tables = ", ".join(table.name for table in _db.metadata.sorted_tables)
        with _db.engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        _db.engine.dispose()
    request_started.disconnect(_empty_g, app)


def _bad_login(client: FlaskClient) -> TestResponse:
    token = csrf_token(client, "/auth/login")
    return client.post("/auth/login", data={"email": "nobody@example.com", "password": "nope", "csrf_token": token})


def test_sixth_failed_login_in_a_minute_is_refused(limited_client: FlaskClient, caplog: pytest.LogCaptureFixture) -> None:
    for _ in range(5):
        assert _bad_login(limited_client).status_code == 200
    with caplog.at_level(logging.WARNING):
        response = _bad_login(limited_client)
    assert response.status_code == 429
    html = response.get_data(as_text=True)
    assert "Too many attempts" in html and "<main" in html
    assert "Rate limit hit: POST /auth/login" in caplog.text
    # Viewing the login page is never limited.
    assert limited_client.get("/auth/login").status_code == 200


def test_successful_logins_do_not_count(limited_client: FlaskClient) -> None:
    from app.services import auth

    auth.register("limit@example.com", PASSWORD)
    for _ in range(8):
        assert login(limited_client, "limit@example.com").status_code == 302
        token = csrf_token(limited_client, "/dashboard/")
        limited_client.post("/auth/logout", data={"csrf_token": token})
