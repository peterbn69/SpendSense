"""Calendar-month arithmetic. A month is represented by the date of its first day."""

from datetime import date
from decimal import Decimal


def add_months(month: date, offset: int) -> date:
    # The first day of the month `offset` months from `month` (negative goes back).
    index = month.year * 12 + month.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def month_range(first: date, last: date) -> list[date]:
    # First days of every month from `first` through `last`, inclusive; empty if `first` is after `last`.
    months: list[date] = []
    month = first.replace(day=1)
    end = last.replace(day=1)
    while month <= end:
        months.append(month)
        month = add_months(month, 1)
    return months


def zero_filled(totals: dict[date, Decimal], months: list[date]) -> list[tuple[date, Decimal]]:
    # (month, total) for every month in `months`
    return [(month, totals.get(month, Decimal(0))) for month in months]
