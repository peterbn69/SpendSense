from datetime import date
from decimal import Decimal

import pytest

from app.analytics.months import add_months, month_range, zero_filled


@pytest.mark.parametrize(
    ("month", "offset", "expected"),
    [
        (date(2026, 11, 1), 0, date(2026, 11, 1)),
        (date(2026, 11, 1), 1, date(2026, 12, 1)),
        (date(2026, 11, 1), 2, date(2027, 1, 1)),
        (date(2026, 1, 1), -1, date(2025, 12, 1)),
        (date(2026, 3, 31), -1, date(2026, 2, 1)),  # any day of the month works; the result is a first day
        (date(2026, 6, 1), -18, date(2024, 12, 1)),
    ],
)
def test_add_months(month: date, offset: int, expected: date) -> None:
    assert add_months(month, offset) == expected


def test_month_range_crosses_a_year() -> None:
    assert month_range(date(2025, 11, 20), date(2026, 2, 3)) == [
        date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1),
    ]


def test_month_range_single_and_empty() -> None:
    assert month_range(date(2026, 5, 9), date(2026, 5, 30)) == [date(2026, 5, 1)]
    assert month_range(date(2026, 6, 1), date(2026, 5, 1)) == []


def test_zero_filled() -> None:
    months = month_range(date(2026, 9, 1), date(2026, 11, 1))
    assert zero_filled({date(2026, 10, 1): Decimal("5.00"), date(2025, 1, 1): Decimal("9")}, months) == [
        (date(2026, 9, 1), Decimal("0")),
        (date(2026, 10, 1), Decimal("5.00")),
        (date(2026, 11, 1), Decimal("0")),
    ]
