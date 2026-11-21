"""What the dashboard shows: monthly totals and this month's spending per category, ready to draw as bars."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app import categories, clock
from app.analytics.months import add_months, month_range, zero_filled
from app.repositories import expenses

MONTHS_SHOWN = 6  # this month and the 5 before it


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
class Dashboard:
    has_expenses: bool
    current_month: date
    month_total: Decimal  # spent so far this month
    months: list[MonthBar]  # oldest first, zero-filled
    categories: list[Bar]  # this month, largest first; only categories with spending


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
    order = {key: index for index, key in enumerate(categories.KEYS)}
    ranked = sorted(by_category.items(), key=lambda item: (-item[1], order.get(item[0], len(order))))
    category_max = ranked[0][1] if ranked else Decimal("0")
    category_bars = [
        Bar(label=categories.label(key), amount=total, percent=_percent(total, category_max))
        for key, total in ranked
        if total > 0
    ]

    return Dashboard(
        has_expenses=expenses.count_for_user(user_id) > 0,
        current_month=current,
        month_total=sum(by_category.values(), Decimal("0")),
        months=months,
        categories=category_bars,
    )


def _percent(amount: Decimal, largest: Decimal) -> int:
    # Bar length as a whole percent of the largest; any spending gets at least 1% so it stays visible.
    if largest <= 0 or amount <= 0:
        return 0
    percent = int((amount * 100 / largest).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return max(1, min(100, percent))
