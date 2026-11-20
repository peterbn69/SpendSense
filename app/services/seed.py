"""
Fake expenses for development: recurring bills, everyday spending, and a few outliers.

The data covers the last `months` completed months plus the current month up to today, so the
dashboard (M9), the forecast (M10) and the anomaly flags (M11) all have something to show.
"""

import random
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

from app import clock
from app.extensions import db
from app.repositories import expenses
from app.repositories.expenses import NewExpense

DEFAULT_MONTHS = 6


class SeedRefusedError(Exception):
    # The user already has expenses and reset was not asked for.

    def __init__(self, existing: int) -> None:
        super().__init__(f"user already has {existing} expenses")
        self.existing = existing


def seed_expenses(user_id: int, *, months: int = DEFAULT_MONTHS, reset: bool = False, rng_seed: int | None = None) -> int:
    # Add fake expenses for one user and commit; returns how many were added.
    existing = expenses.count_for_user(user_id)
    if existing and not reset:
        raise SeedRefusedError(existing)
    if reset:
        expenses.delete_all_for_user(user_id)

    rows = fake_expenses(random.Random(rng_seed), clock.today(), months)
    added = expenses.add_many(user_id, rows)
    db.session.commit()
    return added


def fake_expenses(rng: random.Random, today: date, months: int) -> list[NewExpense]:
    # Expenses from the first day of the month `months` months back through today; none in the future.
    start = _add_months(today.replace(day=1), -months)
    rows: list[NewExpense] = []
    for day in _days(start, today):
        rows.extend(_monthly_bills(day))
        rows.extend(_everyday(rng, day))
        if (day - start).days % 42 == 10:
            rows.append(NewExpense(_cents(rng, 3000, 4500), "health", day, "Haircut"))
    rows.extend(row for row in _one_offs(start) if start <= row.spent_on <= today)
    rows.sort(key=lambda row: row.spent_on)
    return rows


# Fixed bills: (day of month, amount, category, note).
_BILLS: list[tuple[int, str, str, str]] = [
    (1, "1450.00", "housing", "Rent"),
    (1, "156.00", "transport", "Monthly transit pass"),
    (3, "45.00", "health", "Gym membership"),
    (5, "16.99", "subscriptions", "Streaming service"),
    (10, "65.00", "housing", "Internet"),
    (12, "11.99", "subscriptions", "Music streaming"),
    (20, "45.00", "housing", "Phone plan"),
    (25, "9.99", "subscriptions", "Cloud storage"),
]


def _monthly_bills(day: date) -> Iterator[NewExpense]:
    for bill_day, amount, category, note in _BILLS:
        if day.day == bill_day:
            yield NewExpense(Decimal(amount), category, day, note)
    if day.day == 15:
        # The electricity bill varies a little month to month.
        yield NewExpense(Decimal(60 + (day.month * 7) % 45) + Decimal("0.38"), "housing", day, "Electricity")


# Everyday spending: (chance per day, min cents, max cents, category, notes).
_EVERYDAY: list[tuple[float, int, int, str, tuple[str, ...]]] = [
    (0.25, 3500, 14000, "groceries", ("Supermarket", "Farmers market", "Corner store")),
    (0.35, 1200, 5500, "dining", ("Lunch", "Coffee and pastry", "Takeout", "Dinner out")),
    (0.10, 1200, 3500, "transport", ("Rideshare", "Parking")),
    (0.06, 800, 4000, "health", ("Pharmacy",)),
    (0.10, 2000, 15000, "shopping", ("Clothing", "Household items", "Hardware store")),
    (0.10, 1500, 8000, "entertainment", ("Movie tickets", "Concert", "Board game", "Bowling")),
    (0.03, 2000, 6000, "education", ("Books", "Online course")),
    (0.04, 2000, 8000, "other", ("Gift", "Donation")),
]


def _everyday(rng: random.Random, day: date) -> Iterator[NewExpense]:
    for chance, low, high, category, notes in _EVERYDAY:
        if rng.random() < chance:
            yield NewExpense(_cents(rng, low, high), category, day, rng.choice(notes))


def _one_offs(start: date) -> list[NewExpense]:
    # A trip and a few outliers, placed by month offset from the start; dropped if after today.
    def on(month_offset: int, day: int) -> date:
        return _add_months(start, month_offset).replace(day=day)

    return [
        NewExpense(Decimal("385.40"), "groceries", on(1, 18), "Big stock-up for a party"),
        NewExpense(Decimal("420.00"), "travel", on(2, 8), "Flight"),
        NewExpense(Decimal("610.00"), "travel", on(2, 10), "Hotel, 3 nights"),
        NewExpense(Decimal("1299.00"), "shopping", on(3, 9), "New laptop"),
        NewExpense(Decimal("240.00"), "dining", on(4, 22), "Birthday dinner"),
    ]


def _cents(rng: random.Random, low: int, high: int) -> Decimal:
    # A random amount between low and high cents, as a two-place Decimal (no floats involved).
    return Decimal(rng.randint(low, high)).scaleb(-2)


def _days(first: date, last: date) -> Iterator[date]:
    day = first
    while day <= last:
        yield day
        day += timedelta(days=1)


def _add_months(month: date, offset: int) -> date:
    # The first day of the month `offset` months from `month` (negative goes back).
    index = month.year * 12 + month.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)
