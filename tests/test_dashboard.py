import re
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy

from app.models import User
from app.repositories import expenses as expenses_repo
from app.services import insights
from tests.conftest import login

TODAY = date(2026, 2, 14)  # a February, so the 6 months shown cross a year


@pytest.fixture
def today(fake_today: Callable[[date], None]) -> date:
    fake_today(TODAY)
    return TODAY


def _add(user: User, amount: str, spent_on: date, category: str = "groceries") -> None:
    expenses_repo.add(user.id, Decimal(amount), category, spent_on, "")
    expenses_repo.db.session.commit()


def _page(client: FlaskClient) -> str:
    return client.get("/dashboard/").get_data(as_text=True)


# --- Queries ---------------------------------------------------------------------------------------


def test_monthly_totals_since(db: SQLAlchemy, user_a: User) -> None:
    _add(user_a, "1.00", date(2025, 8, 31))
    _add(user_a, "2.00", date(2025, 9, 1))
    _add(user_a, "3.00", date(2025, 9, 30))
    assert expenses_repo.monthly_totals(user_a.id, since=date(2025, 9, 1)) == {date(2025, 9, 1): Decimal("5.00")}


def test_category_totals_between_two_days(db: SQLAlchemy, user_a: User, user_b: User) -> None:
    _add(user_a, "1.00", date(2026, 1, 31), "dining")  # day before: left out
    _add(user_a, "2.00", date(2026, 2, 1), "dining")
    _add(user_a, "3.50", date(2026, 2, 14), "dining")
    _add(user_a, "4.00", date(2026, 2, 10), "travel")
    _add(user_a, "5.00", date(2026, 2, 15), "travel")  # day after: left out
    _add(user_b, "99.00", date(2026, 2, 5), "dining")
    assert expenses_repo.category_totals(user_a.id, date(2026, 2, 1), date(2026, 2, 14)) == {
        "dining": Decimal("5.50"),
        "travel": Decimal("4.00"),
    }


# --- Service ---------------------------------------------------------------------------------------


def test_new_user_has_an_empty_dashboard(db: SQLAlchemy, user_a: User, today: date) -> None:
    board = insights.dashboard(user_a.id)
    assert board.has_expenses is False
    assert board.month_total == Decimal("0")
    assert board.categories == []
    assert [bar.amount for bar in board.months] == [Decimal("0")] * 6
    assert all(bar.percent == 0 for bar in board.months)


def test_six_months_zero_filled_across_a_year(db: SQLAlchemy, user_a: User, user_b: User, today: date) -> None:
    _add(user_a, "500.00", date(2025, 8, 20))  # 7 months ago: not shown
    _add(user_a, "100.00", date(2025, 9, 1))
    _add(user_a, "50.00", date(2025, 12, 31))
    _add(user_a, "25.00", date(2026, 2, 3))
    _add(user_b, "1000.00", date(2025, 10, 10))

    board = insights.dashboard(user_a.id)
    assert [(bar.label, bar.amount, bar.percent, bar.is_current) for bar in board.months] == [
        ("Sep 2025", Decimal("100.00"), 100, False),
        ("Oct 2025", Decimal("0"), 0, False),
        ("Nov 2025", Decimal("0"), 0, False),
        ("Dec 2025", Decimal("50.00"), 50, False),
        ("Jan 2026", Decimal("0"), 0, False),
        ("Feb 2026", Decimal("25.00"), 25, True),
    ]
    assert board.has_expenses is True


def test_this_month_by_category_largest_first(db: SQLAlchemy, user_a: User, today: date) -> None:
    _add(user_a, "10.00", date(2026, 2, 1), "dining")
    _add(user_a, "30.00", date(2026, 2, 2), "groceries")
    _add(user_a, "10.00", date(2026, 2, 14), "housing")  # ties keep the fixed category order
    _add(user_a, "999.00", date(2026, 1, 31), "travel")  # last month: not in this month's breakdown

    board = insights.dashboard(user_a.id)
    assert [(bar.label, bar.amount, bar.percent) for bar in board.categories] == [
        ("Groceries", Decimal("30.00"), 100),
        ("Housing & utilities", Decimal("10.00"), 33),
        ("Dining out", Decimal("10.00"), 33),
    ]
    assert board.month_total == Decimal("50.00")
    assert board.current_month == date(2026, 2, 1)


def test_tiny_amounts_still_get_a_visible_bar(db: SQLAlchemy, user_a: User, today: date) -> None:
    _add(user_a, "999999.99", date(2026, 2, 1), "travel")
    _add(user_a, "0.01", date(2026, 2, 1), "other")
    percents = {bar.label: bar.percent for bar in insights.dashboard(user_a.id).categories}
    assert percents == {"Travel": 100, "Other": 1}


def test_old_expenses_only_still_count_as_having_expenses(db: SQLAlchemy, user_a: User, today: date) -> None:
    _add(user_a, "10.00", date(2024, 1, 1))
    board = insights.dashboard(user_a.id)
    assert board.has_expenses is True
    assert board.categories == []
    assert all(bar.amount == 0 for bar in board.months)


# --- Page ------------------------------------------------------------------------------------------


def test_new_user_sees_the_empty_state(client: FlaskClient, user_a: User, today: date) -> None:
    login(client, "a@example.com")
    page = _page(client)
    assert "Nothing to show yet" in page
    assert 'href="/expenses/new"' in page
    assert 'class="bars"' not in page


def test_dashboard_shows_both_charts(client: FlaskClient, user_a: User, user_b: User, today: date) -> None:
    _add(user_a, "1234.50", date(2026, 2, 3), "housing")
    _add(user_a, "65.25", date(2026, 2, 9), "dining")
    _add(user_a, "300.00", date(2025, 12, 1), "travel")
    _add(user_b, "777.77", date(2026, 2, 3), "shopping")
    login(client, "a@example.com")
    page = _page(client)

    assert "February 2026" in page
    assert "Spent so far: <strong>$1,299.75</strong>" in page
    assert "Housing &amp; utilities" in page and "Dining out" in page
    assert "$65.25" in page
    assert "Shopping" not in page and "$777.77" not in page  # user B's spending
    for label in ("Sep 2025", "Oct 2025", "Nov 2025", "Dec 2025", "Jan 2026", "Feb 2026"):
        assert label in page
    assert "(so far)" in page
    assert page.index("Housing &amp; utilities") < page.index("Dining out")
    widths = [int(w) for w in re.findall(r'class="bar-fill" style="width: (\d+)%"', page)]
    # This month by category (housing, dining), then Sep–Feb: Dec is 300 of February's 1,299.75.
    assert widths == [100, 5, 0, 0, 0, 23, 0, 100]
    assert "Nothing to show yet" not in page


def test_no_spending_this_month_says_so(client: FlaskClient, user_a: User, today: date) -> None:
    _add(user_a, "40.00", date(2025, 11, 5))
    login(client, "a@example.com")
    page = _page(client)
    assert "Nothing spent yet this month." in page
    assert "Spent so far: <strong>$0.00</strong>" in page
    assert "Last 6 months" in page


def test_bars_are_readable_without_css(client: FlaskClient, user_a: User, today: date) -> None:
    _add(user_a, "12.00", date(2026, 2, 1), "health")
    login(client, "a@example.com")
    page = _page(client)
    row = re.search(r'<li class="bar-row">.*?</li>', page, re.S)
    assert row
    text = " ".join(re.sub(r"<[^>]+>", " ", row.group(0)).split())
    assert text == "Health & personal care $12.00".replace("&", "&amp;")
    assert 'class="bar-track" aria-hidden="true"' in row.group(0)
