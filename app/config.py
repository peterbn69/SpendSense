import os
from collections.abc import Mapping
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class Config:
    DEBUG = False
    TESTING = False


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True


class ProductionConfig(Config):
    DEBUG = False


CONFIGS: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}

# Settings read from environment variables; all are required.
ENV_SETTINGS = ("SECRET_KEY", "APP_TIMEZONE")


def get_config_class(name: str | None = None) -> type[Config]:
    name = name or os.environ.get("APP_ENV") or "production"
    try:
        return CONFIGS[name]
    except KeyError:
        choices = ", ".join(CONFIGS)
        raise RuntimeError(f"Unknown APP_ENV {name!r}; expected one of: {choices}.") from None


def settings_from_env() -> dict[str, str]:
    return {key: os.environ[key] for key in ENV_SETTINGS if os.environ.get(key)}


def validate_settings(config: Mapping[str, Any]) -> None:
    missing = [key for key in ENV_SETTINGS if not config.get(key)]
    if missing:
        raise RuntimeError(f"Missing required settings: {', '.join(missing)}. Set them as environment variables (see .env.example).")

    timezone = config["APP_TIMEZONE"]
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise RuntimeError(f"APP_TIMEZONE {timezone!r} is not a valid IANA timezone (e.g. America/Toronto).") from None
