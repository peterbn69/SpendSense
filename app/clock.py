"""
The one place that knows the current time. "Today" and "this month" are in APP_TIMEZONE.
Call these as clock.today() (not `from app.clock import today`), so tests can fake time by patching this module.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from flask import current_app


def _utc_now() -> datetime:
    return datetime.now(UTC)


def timezone() -> ZoneInfo:
    return ZoneInfo(current_app.config["APP_TIMEZONE"])


def now() -> datetime:
    return _utc_now().astimezone(timezone())


def today() -> date:
    return now().date()


def current_month() -> date:
    # The first day of the current month.
    return today().replace(day=1)
