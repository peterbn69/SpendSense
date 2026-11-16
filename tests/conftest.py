import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app

# Test-only values passed as overrides, so tests never depend on the developer's environment.
TEST_SETTINGS = {"SECRET_KEY": "test-only-not-a-secret", "APP_TIMEZONE": "America/Toronto"}


@pytest.fixture
def app() -> Flask:
    return create_app("testing", TEST_SETTINGS)


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()
