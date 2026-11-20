from collections.abc import Callable
from datetime import UTC, date, datetime

import pytest
from flask import Flask

from app import clock


@pytest.fixture
def utc_now(monkeypatch: pytest.MonkeyPatch) -> Callable[[datetime], None]:
    def set_now(moment: datetime) -> None:
        monkeypatch.setattr(clock, "_utc_now", lambda: moment)

    return set_now


def test_today_is_in_app_timezone(app: Flask, utc_now: Callable[[datetime], None]) -> None:
    # 03:00 UTC on 1 November is still 31 October in Toronto.
    utc_now(datetime(2026, 11, 1, 3, 0, tzinfo=UTC))
    with app.app_context():
        assert clock.today() == date(2026, 10, 31)
        assert clock.current_month() == date(2026, 10, 1)
        assert clock.now().utcoffset() is not None


def test_today_follows_the_configured_timezone(app: Flask, utc_now: Callable[[datetime], None]) -> None:
    utc_now(datetime(2026, 11, 1, 3, 0, tzinfo=UTC))
    app.config["APP_TIMEZONE"] = "Asia/Tokyo"
    with app.app_context():
        assert clock.today() == date(2026, 11, 1)


def test_fake_today_also_moves_current_month(app: Flask, fake_today: Callable[[date], None]) -> None:
    fake_today(date(2026, 2, 17))
    with app.app_context():
        assert clock.today() == date(2026, 2, 17)
        assert clock.current_month() == date(2026, 2, 1)
