import os
from collections.abc import Mapping
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class Config:
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    ALLOW_SEED = False
    MAX_CONTENT_LENGTH = 1024 * 1024
    LOG_LEVEL = "INFO"
    RATELIMIT_ENABLED = True
    RATELIMIT_HEADERS_ENABLED = True


class DevelopmentConfig(Config):
    DEBUG = True
    ALLOW_SEED = True


class TestingConfig(Config):
    TESTING = True
    ALLOW_SEED = True
    RATELIMIT_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


CONFIGS: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}

# Environment variable -> Flask config key. All are required.
ENV_SETTINGS: dict[str, str] = {
    "SECRET_KEY": "SECRET_KEY",
    "APP_TIMEZONE": "APP_TIMEZONE",
    "DATABASE_URL": "SQLALCHEMY_DATABASE_URI",
}

# Optional environment variable -> Flask config key; the config class gives the default.
OPTIONAL_ENV_SETTINGS: dict[str, str] = {
    "LOG_LEVEL": "LOG_LEVEL",
}

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
PRODUCTION_SECRET_KEY_MIN_LENGTH = 32

# psycopg 3 is the only installed driver; a bare postgresql:// would make SQLAlchemy look for psycopg2.
DATABASE_URL_PREFIX = "postgresql+psycopg://"


def get_config_class(name: str | None = None) -> type[Config]:
    name = name or os.environ.get("APP_ENV") or "production"
    try:
        return CONFIGS[name]
    except KeyError:
        choices = ", ".join(CONFIGS)
        raise RuntimeError(f"Unknown APP_ENV {name!r}; expected one of: {choices}.") from None


def settings_from_env() -> dict[str, str]:
    names = {**ENV_SETTINGS, **OPTIONAL_ENV_SETTINGS}
    return {key: os.environ[name] for name, key in names.items() if os.environ.get(name)}


def validate_settings(config: Mapping[str, Any]) -> None:
    missing = [name for name, key in ENV_SETTINGS.items() if not config.get(key)]
    if missing:
        raise RuntimeError(
            f"Missing required settings: {', '.join(missing)}. Set them as environment variables (see .env.example)."
        )

    timezone = config["APP_TIMEZONE"]
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise RuntimeError(f"APP_TIMEZONE {timezone!r} is not a valid IANA timezone (e.g. America/Toronto).") from None

    # The URL holds the database password, so the message never echoes it.
    if not str(config["SQLALCHEMY_DATABASE_URI"]).startswith(DATABASE_URL_PREFIX):
        raise RuntimeError(f"DATABASE_URL must start with {DATABASE_URL_PREFIX!r}.")

    level = str(config.get("LOG_LEVEL", "INFO")).upper()
    if level not in LOG_LEVELS:
        raise RuntimeError(f"LOG_LEVEL {level!r} is not one of: {', '.join(LOG_LEVELS)}.")

    # A short key makes signed session cookies guessable. The message never echoes the key.
    if (
        not config.get("DEBUG")
        and not config.get("TESTING")
        and len(str(config["SECRET_KEY"])) < PRODUCTION_SECRET_KEY_MIN_LENGTH
    ):
        raise RuntimeError(
            f"SECRET_KEY must be at least {PRODUCTION_SECRET_KEY_MIN_LENGTH} characters in production "
            "(see .env.example for how to generate one)."
        )
