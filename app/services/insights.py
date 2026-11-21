"""
What the dashboard shows:
- Monthly totals
- This month's spending per category and next month's forecast
- Unusual expenses from the last 90 days
- Ready to draw as bars.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app import categories, clock
from app.analytics import forecast as forecasting
from app.analytics.anomaly import Anomaly, flag_unusual
from app.analytics.months import add_months, month_range, zero_filled
from app.models import Expense
from app.repositories import expenses

MONTHS_SHOWN = 6  # this month and the 5 before it
UNUSUAL_DAYS = 90  # the dashboard lists unusual expenses from this many days, today included


@dataclass(frozen=True)
class Bar:
    label: str
    amount: Decimal
    percent: int  # bar length, 0–100, relative to the largest bar in its chart


@dataclass(frozen=True)
class MonthBar(Bar):
    month: date
    is_current: bool


@dataclass(frozen=True)
class Forecast:
    month: date  # the month being forecast (next month)
    months_of_history: int  # completed months from the first expense through last month
    months_needed: int
    total: Decimal | None  # None when there isn't enough history yet
    categories: list[Bar]  # largest first; only forecasts above 0

    @property
    def ready(self) -> bool:
        return self.total is not None


@dataclass(frozen=True)
class UnusualExpense:
    expense: Expense
    anomaly: Anomaly


@dataclass(frozen=True)
class Dashboard:
    has_expenses: bool
    current_month: date
    month_total: Decimal  # spent so far this month
    months: list[MonthBar]  # oldest first, zero-filled
    categories: list[Bar]  # this month, largest first; only categories with spending
    forecast: Forecast
    unusual: list[UnusualExpense]  # last UNUSUAL_DAYS days, newest first
    unusual_days: int


def dashboard(user_id: int) -> Dashboard:
    current = clock.current_month()
    first = add_months(current, -(MONTHS_SHOWN - 1))
    monthly = zero_filled(expenses.monthly_totals(user_id, since=first), month_range(first, current))
    month_max = max((total for _, total in monthly), default=Decimal("0"))
    months = [
        MonthBar(
            label=f"{month:%b} {month.year}",
            amount=total,
            percent=_percent(total, month_max),
            month=month,
            is_current=month == current,
        )
        for month, total in monthly
    ]

    by_category = expenses.category_totals(user_id, current, clock.today())

    return Dashboard(
        has_expenses=expenses.count_for_user(user_id) > 0,
        current_month=current,
        month_total=sum(by_category.values(), Decimal("0")),
        months=months,
        categories=_ranked_bars(by_category),
        forecast=next_month_forecast(user_id),
        unusual=recent_unusual(user_id),
        unusual_days=UNUSUAL_DAYS,
    )


def unusual_expenses(user_id: int) -> dict[int, Anomaly]:
    return flag_unusual(expenses.amounts_for_user(user_id))


def recent_unusual(user_id: int) -> list[UnusualExpense]:
    flags = unusual_expenses(user_id)
    if not flags:
        return []
    since = clock.today() - timedelta(days=UNUSUAL_DAYS - 1)
    return [UnusualExpense(e, flags[e.id]) for e in expenses.list_since(user_id, since) if e.id in flags]


def next_month_forecast(user_id: int) -> Forecast:
    # Each category's forecast for next month, from completed months only (this month is left out).

    current = clock.current_month()
    last_complete = add_months(current, -1)
    first_day = expenses.first_spent_on(user_id)
    history_months = month_range(first_day, last_complete) if first_day else []
    needed = forecasting.WINDOW

    if len(history_months) < needed:
        return Forecast(add_months(current, 1), len(history_months), needed, total=None, categories=[])

    totals = expenses.monthly_category_totals(user_id, before=current)
    by_category: dict[str, Decimal] = {}
    for key in categories.KEYS:
        history = [amount for _, amount in zero_filled(_one_category(totals, key), history_months)]
        predicted = forecasting.forecast(history)
        if predicted is not None:
            by_category[key] = predicted

    return Forecast(
        month=add_months(current, 1),
        months_of_history=len(history_months),
        months_needed=needed,
        # The sum of the rounded category forecasts, so the total matches the bars shown.
        total=sum(by_category.values(), Decimal("0.00")),
        categories=_ranked_bars(by_category),
    )


def _one_category(totals: dict[tuple[str, date], Decimal], key: str) -> dict[date, Decimal]:
    return {month: amount for (category, month), amount in totals.items() if category == key}


def _ranked_bars(totals: dict[str, Decimal]) -> list[Bar]:
    # Categories above 0, largest first; ties keep the fixed category order.
    order = {key: index for index, key in enumerate(categories.KEYS)}
    ranked = sorted(
        ((key, total) for key, total in totals.items() if total > 0),
        key=lambda item: (-item[1], order.get(item[0], len(order))),
    )
    largest = ranked[0][1] if ranked else Decimal("0")
    return [Bar(label=categories.label(key), amount=total, percent=_percent(total, largest)) for key, total in ranked]


def _percent(amount: Decimal, largest: Decimal) -> int:
    # Bar length as a whole percent of the largest; any spending gets at least 1% so it stays visible.
    if largest <= 0 or amount <= 0:
        return 0
    percent = int((amount * 100 / largest).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return max(1, min(100, percent))
