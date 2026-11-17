import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app
from tests.conftest import TEST_SETTINGS


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in ("APP_ENV", "SECRET_KEY", "APP_TIMEZONE", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_landing_page_renders(client: FlaskClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert b"See where your money goes" in response.data


def test_unknown_url_is_404(client: FlaskClient) -> None:
    assert client.get("/no-such-page").status_code == 404


def test_all_blueprints_registered(app: Flask) -> None:
    assert set(app.blueprints) == {"public", "auth", "expenses", "dashboard"}


def test_extensions_initialized(app: Flask) -> None:
    assert "sqlalchemy" in app.extensions
    assert "migrate" in app.extensions
    assert "csrf" in app.extensions


def test_testing_config(app: Flask) -> None:
    assert app.testing is True
    assert app.debug is False


def test_production_config_has_debug_off(clean_env: pytest.MonkeyPatch) -> None:
    app = create_app("production", TEST_SETTINGS)
    assert app.debug is False
    assert app.testing is False


def test_app_env_defaults_to_production(clean_env: pytest.MonkeyPatch) -> None:
    app = create_app(overrides=TEST_SETTINGS)
    assert app.debug is False
    assert app.testing is False


def test_app_env_selects_config(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("APP_ENV", "development")
    assert create_app(overrides=TEST_SETTINGS).debug is True


def test_unknown_app_env_fails(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("APP_ENV", "staging")
    with pytest.raises(RuntimeError, match="APP_ENV"):
        create_app(overrides=TEST_SETTINGS)


def test_settings_read_from_environment(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("SECRET_KEY", "from-env")
    clean_env.setenv("APP_TIMEZONE", "Europe/Paris")
    clean_env.setenv("DATABASE_URL", "postgresql+psycopg://env-user@localhost/from-env")
    app = create_app("testing")
    assert app.config["SECRET_KEY"] == "from-env"
    assert app.config["APP_TIMEZONE"] == "Europe/Paris"
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "postgresql+psycopg://env-user@localhost/from-env"


@pytest.mark.parametrize(
    ("config_key", "env_name"),
    [("SECRET_KEY", "SECRET_KEY"), ("APP_TIMEZONE", "APP_TIMEZONE"), ("SQLALCHEMY_DATABASE_URI", "DATABASE_URL")],
)
def test_missing_setting_fails(clean_env: pytest.MonkeyPatch, config_key: str, env_name: str) -> None:
    settings = {key: value for key, value in TEST_SETTINGS.items() if key != config_key}
    with pytest.raises(RuntimeError, match=env_name):
        create_app("testing", settings)


def test_empty_setting_counts_as_missing(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("SECRET_KEY", "")
    settings = {key: value for key, value in TEST_SETTINGS.items() if key != "SECRET_KEY"}
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("testing", settings)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:s3cret-pw@localhost/spendsense",
        "postgres://user:s3cret-pw@localhost/spendsense",
        "postgresql+psycopg2://user:s3cret-pw@localhost/spendsense",
        "sqlite:///s3cret-pw.db",
        "not a url",
    ],
)
def test_database_url_must_use_psycopg(clean_env: pytest.MonkeyPatch, url: str) -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL") as error:
        create_app("testing", {**TEST_SETTINGS, "SQLALCHEMY_DATABASE_URI": url})
    assert "s3cret-pw" not in str(error.value)


@pytest.mark.parametrize("timezone", ["Mars/Olympus_Mons", "../etc/passwd", "not a zone"])
def test_invalid_timezone_fails(clean_env: pytest.MonkeyPatch, timezone: str) -> None:
    with pytest.raises(RuntimeError, match="APP_TIMEZONE"):
        create_app("testing", {**TEST_SETTINGS, "APP_TIMEZONE": timezone})
