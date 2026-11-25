import pytest
from argon2 import PasswordHasher
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, select
from werkzeug.test import TestResponse

from app.extensions import db as _db
from app.models import User
from app.repositories import users
from app.services import auth
from tests.conftest import PASSWORD, csrf_token

REGISTER = "/auth/register"


def post_register(client: FlaskClient, **fields: str) -> TestResponse:
    data = {"email": "peter@x.com", "password": PASSWORD, "confirm": PASSWORD, **fields}
    data["csrf_token"] = csrf_token(client, REGISTER)
    return client.post(REGISTER, data=data)


def user_count() -> int:
    return _db.session.scalar(select(func.count()).select_from(User)) or 0


# --- Service -------------------------------------------------------------------------------------


def test_register_stores_argon2_hash_not_password(db: SQLAlchemy) -> None:
    user = auth.register("peter@x.com", PASSWORD)
    db.session.expire_all()

    stored = users.get_by_id(user.id)
    assert stored is not None
    assert stored.password_hash != PASSWORD
    assert PASSWORD not in stored.password_hash
    assert stored.password_hash.startswith("$argon2id$")
    assert PasswordHasher().verify(stored.password_hash, PASSWORD)


def test_same_password_gets_different_hashes(db: SQLAlchemy) -> None:
    first = auth.register("a@x.com", PASSWORD)
    second = auth.register("b@x.com", PASSWORD)
    assert first.password_hash != second.password_hash  # salted


def test_register_lowercases_and_trims_email(db: SQLAlchemy) -> None:
    user = auth.register("  Peter@X.COM ", PASSWORD)
    assert user.email == "peter@x.com"


def test_register_commits(db: SQLAlchemy) -> None:
    auth.register("peter@x.com", PASSWORD)
    db.session.rollback()
    assert users.get_by_email("peter@x.com") is not None


def test_register_rejects_email_differing_only_in_case(db: SQLAlchemy) -> None:
    auth.register("peter@x.com", PASSWORD)
    with pytest.raises(auth.EmailTakenError):
        auth.register("Peter@x.com", "another password")
    assert user_count() == 1


def test_register_catches_unique_violation_from_race(db: SQLAlchemy, monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate another request inserting the same email between the check and the insert.
    auth.register("peter@x.com", PASSWORD)
    monkeypatch.setattr(users, "get_by_email", lambda email: None)
    with pytest.raises(auth.EmailTakenError):
        auth.register("peter@x.com", PASSWORD)
    monkeypatch.undo()
    # The session was rolled back and is usable again.
    assert users.get_by_email("peter@x.com") is not None
    assert user_count() == 1


def test_is_email_registered_ignores_case(db: SQLAlchemy) -> None:
    assert not auth.is_email_registered("peter@x.com")
    auth.register("peter@x.com", PASSWORD)
    assert auth.is_email_registered(" PETER@x.com")


# --- Route ---------------------------------------------------------------------------------------


def test_register_page_has_form(client: FlaskClient, db: SQLAlchemy) -> None:
    response = client.get(REGISTER)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<h1 id="register-title">Sign up</h1>' in html
    assert 'name="csrf_token"' in html
    for name in ("email", "password", "confirm"):
        assert f'name="{name}"' in html
    assert 'aria-current="page"' in html


def test_register_success_redirects_to_login_with_message(client: FlaskClient, db: SQLAlchemy) -> None:
    response = post_register(client, email="Peter@X.com")
    assert response.status_code == 302
    assert response.headers["Location"] == "/auth/login"

    user = users.get_by_email("peter@x.com")
    assert user is not None
    assert user.password_hash != PASSWORD

    html = client.get("/auth/login").get_data(as_text=True)
    assert "Your account is ready" in html


def test_duplicate_email_rejected_case_insensitively(client: FlaskClient, db: SQLAlchemy) -> None:
    assert post_register(client, email="peter@x.com").status_code == 302

    response = post_register(client, email="Peter@x.com")
    assert response.status_code == 200
    assert "An account with this email already exists" in response.get_data(as_text=True)
    assert user_count() == 1


def test_duplicate_caught_at_database_shows_form_error(
    client: FlaskClient, db: SQLAlchemy, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The form's check misses a concurrent sign-up; the service's IntegrityError handling still answers clearly.
    auth.register("peter@x.com", PASSWORD)
    monkeypatch.setattr(auth, "is_email_registered", lambda email: False)
    monkeypatch.setattr(users, "get_by_email", lambda email: None)

    response = post_register(client, email="peter@x.com")
    assert response.status_code == 200
    assert "An account with this email already exists" in response.get_data(as_text=True)


def test_password_is_not_echoed_back(client: FlaskClient, db: SQLAlchemy) -> None:
    response = post_register(client, confirm="something else")
    html = response.get_data(as_text=True)
    assert PASSWORD not in html
    assert "something else" not in html


def test_email_is_kept_after_error(client: FlaskClient, db: SQLAlchemy) -> None:
    html = post_register(client, email="kept@x.com", password="short", confirm="short").get_data(as_text=True)
    assert 'value="kept@x.com"' in html


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"email": ""}, "Enter your email address."),
        ({"email": "   "}, "Enter your email address."),
        ({"email": "not-an-email"}, "Enter a valid email address"),
        ({"email": "a@b"}, "Enter a valid email address"),
        ({"email": "a" * 250 + "@x.com"}, "Use at most 254 characters."),
        ({"email": "<script>alert(1)</script>@x.com"}, "Enter a valid email address"),
        ({"password": "", "confirm": ""}, "Choose a password."),
        ({"password": "1234567", "confirm": "1234567"}, "Use 8 to 128 characters."),
        ({"password": "x" * 129, "confirm": "x" * 129}, "Use 8 to 128 characters."),
        ({"confirm": ""}, "Type your password again."),
        ({"confirm": PASSWORD + "!"}, "The passwords don&#39;t match."),
    ],
)
def test_invalid_input_is_rejected(client: FlaskClient, db: SQLAlchemy, fields: dict[str, str], message: str) -> None:
    response = post_register(client, **fields)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert message in html
    assert 'aria-invalid="true"' in html
    assert "<script>alert(1)</script>" not in html
    assert user_count() == 0


def test_password_of_exactly_8_characters_is_accepted(client: FlaskClient, db: SQLAlchemy) -> None:
    assert post_register(client, password="12345678", confirm="12345678").status_code == 302


def test_missing_fields_do_not_crash(client: FlaskClient, db: SQLAlchemy) -> None:
    token = csrf_token(client, REGISTER)
    response = client.post(REGISTER, data={"csrf_token": token})
    assert response.status_code == 200
    assert user_count() == 0


def test_enormous_input_does_not_crash(client: FlaskClient, db: SQLAlchemy) -> None:
    big = "x" * 100_000
    response = post_register(client, email=big + "@x.com", password=big, confirm=big)
    assert response.status_code in (200, 413)
    assert user_count() == 0


def test_post_without_csrf_token_is_rejected(client: FlaskClient, db: SQLAlchemy) -> None:
    response = client.post(REGISTER, data={"email": "peter@x.com", "password": PASSWORD, "confirm": PASSWORD})
    assert response.status_code == 400
    assert user_count() == 0


def test_post_with_wrong_csrf_token_is_rejected(client: FlaskClient, db: SQLAlchemy) -> None:
    csrf_token(client, REGISTER)  # start a session
    data = {"email": "peter@x.com", "password": PASSWORD, "confirm": PASSWORD, "csrf_token": "forged"}
    assert client.post(REGISTER, data=data).status_code == 400
    assert user_count() == 0
