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
    assert board.month_total == Decimal(0)
    assert board.categories == []
    assert [bar.amount for bar in board.months] == [Decimal(0)] * 6
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
        ("Oct 2025", Decimal(0), 0, False),
        ("Nov 2025", Decimal(0), 0, False),
        ("Dec 2025", Decimal("50.00"), 50, False),
        ("Jan 2026", Decimal(0), 0, False),
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
    assert '<p class="stat-hero-amount">$1,299.75</p>' in page
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
    assert '<p class="stat-hero-amount">$0.00</p>' in page
    assert "Last 6 months" in page


def test_bars_are_readable_without_css(client: FlaskClient, user_a: User, today: date) -> None:
    _add(user_a, "12.00", date(2026, 2, 1), "health")
    login(client, "a@example.com")
    page = _page(client)
    row = re.search(r'<li class="bar-row">.*?</li>', page, re.DOTALL)
    assert row
    text = " ".join(re.sub(r"<[^>]+>", " ", row.group(0)).split())
    assert text == "Health & personal care $12.00".replace("&", "&amp;")
    assert 'class="bar-track" aria-hidden="true"' in row.group(0)


# --- Forecast (M10) --------------------------------------------------------------------------------
# TODAY is 2026-02-14: the completed months are ..., Nov 2025, Dec 2025, Jan 2026; the forecast is for March 2026.


def test_first_spent_on(db: SQLAlchemy, user_a: User, user_b: User) -> None:
    assert expenses_repo.first_spent_on(user_a.id) is None
    _add(user_b, "1.00", date(2020, 1, 1))
    _add(user_a, "1.00", date(2025, 6, 9))
    _add(user_a, "1.00", date(2025, 3, 2))
    assert expenses_repo.first_spent_on(user_a.id) == date(2025, 3, 2)


def test_monthly_category_totals_before_a_day(db: SQLAlchemy, user_a: User, user_b: User) -> None:
    _add(user_a, "1.00", date(2026, 1, 5), "dining")
    _add(user_a, "2.00", date(2026, 1, 31), "dining")
    _add(user_a, "4.00", date(2026, 1, 9), "travel")
    _add(user_a, "8.00", date(2026, 2, 1), "dining")  # on the cut-off day: left out
    _add(user_b, "16.00", date(2026, 1, 5), "dining")
    assert expenses_repo.monthly_category_totals(user_a.id, before=date(2026, 2, 1)) == {
        ("dining", date(2026, 1, 1)): Decimal("3.00"),
        ("travel", date(2026, 1, 1)): Decimal("4.00"),
    }


@pytest.mark.parametrize(
    ("first_expense", "months_of_history"),
    [(None, 0), (date(2026, 2, 1), 0), (date(2026, 1, 31), 1), (date(2025, 12, 1), 2)],
)
def test_not_enough_history(
    db: SQLAlchemy, user_a: User, today: date, first_expense: date | None, months_of_history: int
) -> None:
    if first_expense:
        _add(user_a, "500.00", first_expense)
    result = insights.next_month_forecast(user_a.id)
    assert result.ready is False
    assert result.total is None
    assert result.categories == []
    assert result.months_of_history == months_of_history
    assert result.months_needed == 3
    assert result.month == date(2026, 3, 1)


def test_three_full_months_give_a_forecast(db: SQLAlchemy, user_a: User, today: date) -> None:
    _add(user_a, "30.00", date(2025, 11, 1), "dining")
    _add(user_a, "60.00", date(2025, 12, 15), "dining")
    _add(user_a, "90.00", date(2026, 1, 31), "dining")
    result = insights.next_month_forecast(user_a.id)
    assert result.ready is True
    assert result.months_of_history == 3
    assert [(bar.label, bar.amount) for bar in result.categories] == [("Dining out", Decimal("60.00"))]
    assert result.total == Decimal("60.00")


def test_this_month_is_left_out(db: SQLAlchemy, user_a: User, today: date) -> None:
    for month in (11, 12):
        _add(user_a, "30.00", date(2025, month, 1))
    _add(user_a, "30.00", date(2026, 1, 1))
    _add(user_a, "9000.00", date(2026, 2, 14))  # this month, partial: not part of the history
    assert insights.next_month_forecast(user_a.id).total == Decimal("30.00")


def test_only_the_last_three_months_count(db: SQLAlchemy, user_a: User, today: date) -> None:
    _add(user_a, "5000.00", date(2025, 6, 1), "travel")  # months ago
    for month, amount in ((11, "10.00"), (12, "20.00")):
        _add(user_a, amount, date(2025, month, 3), "groceries")
    _add(user_a, "30.00", date(2026, 1, 3), "groceries")
    result = insights.next_month_forecast(user_a.id)
    assert result.months_of_history == 8  # Jun 2025 through Jan 2026
    assert [(bar.label, bar.amount) for bar in result.categories] == [("Groceries", Decimal("20.00"))]


def test_history_is_zero_filled_from_the_first_expense_in_any_category(
    db: SQLAlchemy, user_a: User, today: date
) -> None:
    _add(user_a, "300.00", date(2025, 11, 2), "housing")
    _add(user_a, "90.00", date(2026, 1, 20), "health")  # one month of health spending: averaged with two zeros
    result = insights.next_month_forecast(user_a.id)
    assert [(bar.label, bar.amount) for bar in result.categories] == [
        ("Housing & utilities", Decimal("100.00")),
        ("Health & personal care", Decimal("30.00")),
    ]
    assert result.total == Decimal("130.00")


def test_total_is_the_sum_of_rounded_category_forecasts(db: SQLAlchemy, user_a: User, today: date) -> None:
    # Each category averages to 0.0033..., rounded to 0.00 and left out; dining averages to 3.3333... -> 3.33.
    for key in ("groceries", "transport"):
        _add(user_a, "0.01", date(2026, 1, 2), key)
    _add(user_a, "10.00", date(2025, 11, 2), "dining")
    result = insights.next_month_forecast(user_a.id)
    assert [(bar.label, bar.amount) for bar in result.categories] == [("Dining out", Decimal("3.33"))]
    assert result.total == Decimal("3.33")


def test_forecast_ignores_other_users(db: SQLAlchemy, user_a: User, user_b: User, today: date) -> None:
    _add(user_a, "30.00", date(2025, 11, 1))
    _add(user_b, "999.00", date(2025, 12, 1))
    _add(user_b, "999.00", date(2026, 1, 1))
    result = insights.next_month_forecast(user_a.id)
    assert result.total == Decimal("10.00")


def test_forecast_for_next_month_crosses_a_year(
    db: SQLAlchemy, user_a: User, fake_today: Callable[[date], None]
) -> None:
    fake_today(date(2026, 12, 5))
    _add(user_a, "12.00", date(2026, 9, 1))
    result = insights.next_month_forecast(user_a.id)
    assert result.month == date(2027, 1, 1)
    assert result.months_of_history == 3  # Sep, Oct, Nov
    assert result.total == Decimal("4.00")


def test_page_says_not_enough_data_yet(client: FlaskClient, user_a: User, today: date) -> None:
    _add(user_a, "40.00", date(2026, 1, 5))
    login(client, "a@example.com")
    page = _page(client)
    assert "Forecast for March 2026" in page
    assert "Not enough data yet." in page
    assert "You have 1 so far." in page
    assert "Expected spending" not in page


def test_page_shows_the_forecast(client: FlaskClient, user_a: User, today: date) -> None:
    for month in (11, 12):
        _add(user_a, "1500.00", date(2025, month, 1), "housing")
        _add(user_a, "75.00", date(2025, month, 9), "dining")
    _add(user_a, "1500.00", date(2026, 1, 1), "housing")
    login(client, "a@example.com")
    page = _page(client)
    assert "Forecast for March 2026" in page
    assert "Expected spending: <strong>$1,550.00</strong>" in page
    assert "Not enough data yet" not in page
    forecast_panel = page[page.index('id="forecast-title"') : page.index('id="months-title"')]
    assert "Housing &amp; utilities" in forecast_panel and "$1,500.00" in forecast_panel
    assert "Dining out" in forecast_panel and "$50.00" in forecast_panel
    assert forecast_panel.index("Housing") < forecast_panel.index("Dining")


def test_page_when_the_last_three_months_were_empty(client: FlaskClient, user_a: User, today: date) -> None:
    _add(user_a, "40.00", date(2025, 6, 5))
    login(client, "a@example.com")
    page = _page(client)
    assert "Expected spending: <strong>$0.00</strong>" in page
    assert "No spending in the last 3 full months." in page


def test_headline_card_leads_with_this_month(client: FlaskClient, user_a: User, today: date) -> None:
    for month in (11, 12):
        _add(user_a, "100.00", date(2025, month, 1))
    _add(user_a, "250.00", date(2026, 1, 15))  # last month
    _add(user_a, "42.10", date(2026, 2, 2))  # this month
    login(client, "a@example.com")
    page = _page(client)

    hero = page[page.index('class="stat-hero"') : page.index('class="dashboard-grid"')]
    assert "Spent in February 2026" in hero
    assert '<p class="stat-hero-amount">$42.10</p>' in hero
    assert "Last month" in hero and "$250.00" in hero
    assert "Forecast for March 2026" in hero and "$150.00" in hero
    assert 'href="#unusual-title">0</a>' in hero
    # It comes before every panel.
    assert page.index('class="stat-hero"') < page.index('id="this-month-title"')


def test_headline_card_before_enough_history(client: FlaskClient, user_a: User, today: date) -> None:
    _add(user_a, "10.00", date(2026, 2, 2))
    login(client, "a@example.com")
    hero = _page(client).split('class="stat-hero"')[1].split('class="dashboard-grid"')[0]
    assert "Not enough data yet" in hero
