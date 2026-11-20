import random
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest
from click.testing import Result
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from app import categories
from app.models import User
from app.repositories import expenses
from app.services import auth
from app.services.seed import fake_expenses
from tests.conftest import PASSWORD

TODAY = date(2026, 11, 20)
EMAIL = "seed-test@example.com"


@pytest.fixture
def run_seed(app: Flask, db: SQLAlchemy, fake_today: Callable[[date], None]) -> Callable[..., Result]:
    fake_today(TODAY)

    def run(*args: str, input: str | None = None) -> Result:
        return app.test_cli_runner().invoke(args=["seed", "--email", EMAIL, *args], input=input)

    return run


def _new_password() -> str:
    return f"{PASSWORD}\n{PASSWORD}\n"


# --- the generated data ---


def test_fake_data_covers_six_completed_months_and_today() -> None:
    rows = fake_expenses(random.Random(1), TODAY, 6)
    months = {row.spent_on.replace(day=1) for row in rows}
    assert months == {date(2026, m, 1) for m in range(5, 12)}
    assert min(row.spent_on for row in rows) == date(2026, 5, 1)
    assert max(row.spent_on for row in rows) <= TODAY


def test_fake_data_is_valid() -> None:
    rows = fake_expenses(random.Random(2), TODAY, 6)
    assert len(rows) > 150
    for row in rows:
        assert isinstance(row.amount, Decimal)
        assert row.amount > 0 and row.amount == row.amount.quantize(Decimal("0.01"))
        assert row.amount < 1_000_000
        assert categories.is_valid(row.category)
        assert len(row.note) <= 200
    assert {row.category for row in rows} == set(categories.KEYS)


def test_fake_data_is_repeatable_with_a_seed() -> None:
    assert fake_expenses(random.Random(7), TODAY, 6) == fake_expenses(random.Random(7), TODAY, 6)


def test_fake_data_never_in_the_future_early_in_a_month() -> None:
    today = date(2026, 11, 1)
    rows = fake_expenses(random.Random(3), today, 6)
    assert max(row.spent_on for row in rows) == today


def test_fake_data_has_outliers_for_anomaly_detection() -> None:
    notes = {row.note for row in fake_expenses(random.Random(4), TODAY, 6)}
    assert {"New laptop", "Birthday dinner", "Big stock-up for a party"} <= notes


# --- the flask seed command ---


def test_seed_creates_user_and_fills_table(run_seed: Callable[..., Result]) -> None:
    result = run_seed("--random-seed", "1", input=_new_password())
    assert result.exit_code == 0, result.output
    user = auth.find_by_email(EMAIL)
    assert user is not None
    added = expenses.count_for_user(user.id)
    assert added > 150
    assert f"Added {added} expenses" in result.output
    assert auth.authenticate(EMAIL, PASSWORD) is not None


def test_seed_default_email(app: Flask, db: SQLAlchemy, fake_today: Callable[[date], None]) -> None:
    from app.cli import DEFAULT_SEED_EMAIL

    fake_today(TODAY)
    result = app.test_cli_runner().invoke(args=["seed"], input=_new_password())
    assert result.exit_code == 0, result.output
    assert auth.find_by_email(DEFAULT_SEED_EMAIL) is not None


def test_seed_existing_user_needs_no_password(run_seed: Callable[..., Result], db: SQLAlchemy) -> None:
    user = auth.register(EMAIL, PASSWORD)
    result = run_seed()
    assert result.exit_code == 0, result.output
    assert "Password" not in result.output
    assert expenses.count_for_user(user.id) > 0


def test_seed_refuses_to_add_twice(run_seed: Callable[..., Result]) -> None:
    run_seed(input=_new_password())
    user = auth.find_by_email(EMAIL)
    assert user is not None
    before = expenses.count_for_user(user.id)

    result = run_seed()
    assert result.exit_code != 0
    assert "--reset" in result.output
    assert expenses.count_for_user(user.id) == before


def test_seed_reset_replaces_only_that_users_expenses(run_seed: Callable[..., Result], user_b: User) -> None:
    expenses.add(user_b.id, Decimal("5.00"), "other", TODAY)
    run_seed("--random-seed", "1", input=_new_password())
    user = auth.find_by_email(EMAIL)
    assert user is not None
    first = expenses.count_for_user(user.id)

    result = run_seed("--reset", "--random-seed", "1")
    assert result.exit_code == 0, result.output
    assert expenses.count_for_user(user.id) == first
    assert expenses.count_for_user(user_b.id) == 1


def test_seed_months_option(run_seed: Callable[..., Result]) -> None:
    run_seed("--months", "2", input=_new_password())
    user = auth.find_by_email(EMAIL)
    assert user is not None
    months = {e.spent_on.replace(day=1) for e in expenses.list_for_user(user.id)}
    assert months == {date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)}


@pytest.mark.parametrize("months", ["0", "25", "abc"])
def test_seed_rejects_bad_months(run_seed: Callable[..., Result], months: str) -> None:
    result = run_seed("--months", months)
    assert result.exit_code == 2
    assert auth.find_by_email(EMAIL) is None


def test_seed_rejects_bad_email(app: Flask, db: SQLAlchemy) -> None:
    result = app.test_cli_runner().invoke(args=["seed", "--email", "not-an-email"])
    assert result.exit_code == 2


def test_seed_rejects_short_password(run_seed: Callable[..., Result]) -> None:
    result = run_seed(input="short\nshort\n")
    assert result.exit_code != 0
    assert "8 to 128 characters" in result.output
    assert auth.find_by_email(EMAIL) is None


def test_seed_refused_when_not_allowed(run_seed: Callable[..., Result], app: Flask) -> None:
    app.config["ALLOW_SEED"] = False
    result = run_seed(input=_new_password())
    assert result.exit_code != 0
    assert "turned off" in result.output
    assert auth.find_by_email(EMAIL) is None


def test_seed_is_off_in_production_config() -> None:
    from app.config import CONFIGS

    assert CONFIGS["production"].ALLOW_SEED is False
    assert CONFIGS["development"].ALLOW_SEED is True
