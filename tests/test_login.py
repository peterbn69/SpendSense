from urllib.parse import parse_qs, urlsplit

import pytest
from argon2 import PasswordHasher
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy

from app import create_app
from app.blueprints.auth.forms import LOGIN_FAILED_MESSAGE
from app.blueprints.auth.routes import safe_next_url
from app.models import User
from app.repositories import users
from app.services import auth
from tests.conftest import PASSWORD, TEST_SETTINGS, csrf_token, login

DASHBOARD = "/dashboard/"
LOGIN_FAILED_HTML = LOGIN_FAILED_MESSAGE


def is_logged_in(client: FlaskClient) -> bool:
    return client.get(DASHBOARD).status_code == 200


# --- Done when: a logged-out user can't reach the dashboard --------------------------------------


def test_logged_out_user_cannot_reach_dashboard(client: FlaskClient, db: SQLAlchemy) -> None:
    response = client.get(DASHBOARD)
    assert response.status_code == 302
    location = urlsplit(response.headers["Location"])
    assert location.path == "/auth/login"
    assert parse_qs(location.query) == {"next": [DASHBOARD]}

    html = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "Log in to see that page." in html


def test_dashboard_without_trailing_slash_is_also_protected(client: FlaskClient, db: SQLAlchemy) -> None:
    response = client.get("/dashboard", follow_redirects=True)
    assert response.request.path == "/auth/login"


# --- Logging in ----------------------------------------------------------------------------------


def test_login_page_has_form(client: FlaskClient, db: SQLAlchemy) -> None:
    response = client.get("/auth/login")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="csrf_token"' in html
    assert 'name="email"' in html
    assert 'name="password"' in html
    assert 'aria-current="page"' in html


def test_login_success_goes_to_dashboard(client: FlaskClient, user_a: User) -> None:
    response = login(client, "a@example.com")
    assert response.status_code == 302
    assert response.headers["Location"] == DASHBOARD

    html = client.get(DASHBOARD).get_data(as_text=True)
    assert "a@example.com" in html


def test_login_email_ignores_case_and_spaces(client: FlaskClient, user_a: User) -> None:
    assert login(client, "  A@Example.COM ").status_code == 302
    assert is_logged_in(client)


def test_each_user_sees_their_own_session(client: FlaskClient, user_a: User, user_b: User) -> None:
    login(client, "b@example.com")
    html = client.get(DASHBOARD).get_data(as_text=True)
    assert "b@example.com" in html
    assert "a@example.com" not in html


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("a@example.com", "wrong password"),
        ("a@example.com", PASSWORD.upper()),
        ("nobody@example.com", PASSWORD),
        ("not-an-email", PASSWORD),
        ("a@example.com", "x" * 10_000),
    ],
)
def test_every_login_failure_shows_one_generic_message(
    client: FlaskClient, user_a: User, email: str, password: str
) -> None:
    response = login(client, email, password)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert html.count(LOGIN_FAILED_HTML) == 1
    assert 'role="alert"' in html
    assert password not in html
    assert not is_logged_in(client)


def test_wrong_password_and_unknown_email_look_the_same(client: FlaskClient, user_a: User) -> None:
    def error_box(response_html: str) -> str:
        start = response_html.index('<p class="form-error"')
        return response_html[start : response_html.index("</p>", start)]

    wrong_password = login(client, "a@example.com", "wrong password").get_data(as_text=True)
    unknown_email = login(client, "nobody@example.com", "wrong password").get_data(as_text=True)
    assert error_box(wrong_password) == error_box(unknown_email)


@pytest.mark.parametrize(
    ("email", "password", "message"),
    [
        ("", PASSWORD, "Enter your email address."),
        ("   ", PASSWORD, "Enter your email address."),
        ("a@example.com", "", "Enter your password."),
    ],
)
def test_blank_fields_are_rejected(client: FlaskClient, user_a: User, email: str, password: str, message: str) -> None:
    response = login(client, email, password)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert message in html
    assert LOGIN_FAILED_HTML not in html
    assert not is_logged_in(client)


def test_missing_and_enormous_fields_do_not_crash(client: FlaskClient, user_a: User) -> None:
    token = csrf_token(client, "/auth/login")
    assert client.post("/auth/login", data={"csrf_token": token}).status_code == 200

    big = "x" * 100_000
    response = client.post("/auth/login", data={"csrf_token": token, "email": big, "password": big})
    assert response.status_code in (200, 413)
    assert not is_logged_in(client)


def test_login_without_csrf_token_is_rejected(client: FlaskClient, user_a: User) -> None:
    response = client.post("/auth/login", data={"email": "a@example.com", "password": PASSWORD})
    assert response.status_code == 400
    assert not is_logged_in(client)


@pytest.mark.parametrize("path", ["/auth/login", "/auth/register"])
def test_logged_in_user_is_sent_to_dashboard(client: FlaskClient, user_a: User, path: str) -> None:
    login(client, "a@example.com")
    response = client.get(path)
    assert response.status_code == 302
    assert response.headers["Location"] == DASHBOARD


# --- The next redirect ---------------------------------------------------------------------------


def test_login_returns_to_the_protected_page(client: FlaskClient, user_a: User) -> None:
    login_location = client.get(DASHBOARD).headers["Location"]
    (next_url,) = parse_qs(urlsplit(login_location).query)["next"]

    response = login(client, "a@example.com", next_url=next_url)
    assert response.headers["Location"] == DASHBOARD


def test_next_survives_a_failed_attempt(client: FlaskClient, user_a: User) -> None:
    html = login(client, "a@example.com", "wrong password", next_url="/dashboard/?month=2026-10").get_data(as_text=True)
    assert 'action="/auth/login?next=/dashboard/?month%3D2026-10"' in html


def test_safe_next_is_followed(client: FlaskClient, user_a: User) -> None:
    response = login(client, "a@example.com", next_url="/dashboard/?month=2026-10")
    assert response.headers["Location"] == "/dashboard/?month=2026-10"


UNSAFE_NEXT = [
    "https://evil.example/",
    "http://evil.example",
    "//evil.example",
    "///evil.example",
    "/\\evil.example",
    "\\\\evil.example",
    "/\t/evil.example",
    "/\n/evil.example",
    "javascript:alert(1)",
    "evil.example",
    "dashboard/",
    "",
]


@pytest.mark.parametrize("next_url", UNSAFE_NEXT)
def test_unsafe_next_goes_to_dashboard(client: FlaskClient, user_a: User, next_url: str) -> None:
    response = login(client, "a@example.com", next_url=next_url)
    assert response.status_code == 302
    assert response.headers["Location"] == DASHBOARD


@pytest.mark.parametrize("next_url", UNSAFE_NEXT)
def test_safe_next_url_rejects(next_url: str) -> None:
    assert safe_next_url(next_url) is None


@pytest.mark.parametrize("next_url", ["/", "/dashboard/", "/expenses/3/edit?x=1", "/a%2F%2Fb"])
def test_safe_next_url_accepts(next_url: str) -> None:
    assert safe_next_url(next_url) == next_url


def test_safe_next_url_none() -> None:
    assert safe_next_url(None) is None


# --- Logging out ---------------------------------------------------------------------------------


def test_logout_is_a_post_with_csrf(client: FlaskClient, user_a: User) -> None:
    login(client, "a@example.com")
    token = csrf_token(client, DASHBOARD)  # from the nav's logout form

    response = client.post("/auth/logout", data={"csrf_token": token})
    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert "You&#39;re logged out." in client.get("/").get_data(as_text=True)
    assert client.get(DASHBOARD).status_code == 302


def test_logout_by_get_is_not_allowed(client: FlaskClient, user_a: User) -> None:
    login(client, "a@example.com")
    assert client.get("/auth/logout").status_code == 405
    assert is_logged_in(client)


def test_logout_without_csrf_token_is_rejected(client: FlaskClient, user_a: User) -> None:
    login(client, "a@example.com")
    assert client.post("/auth/logout").status_code == 400
    assert is_logged_in(client)


def test_nav_follows_login_state(client: FlaskClient, user_a: User) -> None:
    def nav(path: str) -> str:
        html = client.get(path).get_data(as_text=True)
        return html[html.index("<nav") : html.index("</nav>")]

    assert 'href="/auth/login"' in nav("/")
    assert "Log out" not in nav("/")

    login(client, "a@example.com")
    assert 'action="/auth/logout"' in nav("/")
    assert 'href="/dashboard/"' in nav("/")
    assert 'href="/auth/login"' not in nav("/")


# --- Service -------------------------------------------------------------------------------------


def test_authenticate(db: SQLAlchemy, user_a: User) -> None:
    assert auth.authenticate("A@example.com", PASSWORD) is user_a
    assert auth.authenticate("a@example.com", "wrong password") is None
    assert auth.authenticate("nobody@example.com", PASSWORD) is None


def test_unknown_email_still_runs_argon2(db: SQLAlchemy, monkeypatch: pytest.MonkeyPatch) -> None:
    checked: list[str] = []
    real_verify = auth._verify

    def spy(password_hash: str, password: str) -> bool:
        checked.append(password_hash)
        return real_verify(password_hash, password)

    monkeypatch.setattr(auth, "_verify", spy)
    assert auth.authenticate("nobody@example.com", PASSWORD) is None
    assert len(checked) == 1
    assert checked[0].startswith("$argon2id$")


def test_corrupt_stored_hash_fails_closed(db: SQLAlchemy) -> None:
    users.add("broken@example.com", "not-an-argon2-hash")
    assert auth.authenticate("broken@example.com", PASSWORD) is None


def test_outdated_hash_is_upgraded_on_login(db: SQLAlchemy) -> None:
    old_hash = PasswordHasher(time_cost=1, memory_cost=8192).hash(PASSWORD)
    user = users.add("old@example.com", old_hash)
    db.session.commit()

    assert auth.authenticate("old@example.com", PASSWORD) is user
    db.session.expire_all()
    new_hash = users.get_by_email("old@example.com").password_hash  # type: ignore[union-attr]
    assert new_hash != old_hash
    assert not PasswordHasher().check_needs_rehash(new_hash)


@pytest.mark.parametrize("user_id", ["", "abc", "0", "-1", "1.5", "99999999999999999999999"])
def test_load_user_rejects_bad_ids(db: SQLAlchemy, user_id: str) -> None:
    assert auth.load_user(user_id) is None


def test_load_user(db: SQLAlchemy, user_a: User) -> None:
    assert auth.load_user(str(user_a.id)) is user_a
    assert auth.load_user(str(user_a.id + 1000)) is None


# --- Session cookie ------------------------------------------------------------------------------


def test_session_cookie_flags_after_login(client: FlaskClient, user_a: User) -> None:
    response = login(client, "a@example.com")
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Secure" not in cookie  # testing runs over plain http


def test_production_session_cookie_is_secure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    app = create_app("production", TEST_SETTINGS)
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
