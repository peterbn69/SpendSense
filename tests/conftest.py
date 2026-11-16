import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app

# Test-only values passed as overrides, so tests never depend on the developer's environment.
# The database URL is a placeholder that is never connected to; database tests will use TEST_DATABASE_URL.
TEST_SETTINGS = {
    "SECRET_KEY": "test-only-not-a-secret",
    "APP_TIMEZONE": "America/Toronto",
    "SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://placeholder@localhost/not-used",
}


@pytest.fixture
def app() -> Flask:
    return create_app("testing", TEST_SETTINGS)


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()
