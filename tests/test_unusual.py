"""M11: anomaly flags applied per category, in the expense list and on the dashboard."""

import re
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

import pytest
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy

from app.models import Expense, User
from app.repositories import expenses as expenses_repo
from app.services import insights
from tests.conftest import login

TODAY = date(2026, 11, 21)
USUAL = ("20.00", "22.00", "18.00", "21.00", "19.00")  # typical dining: about $20


@pytest.fixture
def today(fake_today: Callable[[date], None]) -> date:
    fake_today(TODAY)
    return TODAY


def _add(user: User, amount: str, spent_on: date, category: str = "dining", note: str = "") -> Expense:
    expense = expenses_repo.add(user.id, Decimal(amount), category, spent_on, note)
    expenses_repo.db.session.commit()
    return expense


def _usual_dining(user: User, spent_on: date = date(2026, 6, 1)) -> None:
    for amount in USUAL:
        _add(user, amount, spent_on)


# --- Queries ---------------------------------------------------------------------------------------


def test_amounts_for_user(db: SQLAlchemy, user_a: User, user_b: User) -> None:
    first = _add(user_a, "1.50", date(2026, 1, 1), "travel")
    second = _add(user_a, "2.00", date(2026, 1, 2))
    _add(user_b, "3.00", date(2026, 1, 3))
    assert sorted(expenses_repo.amounts_for_user(user_a.id)) == [
        (first.id, "travel", Decimal("1.50")),
        (second.id, "dining", Decimal("2.00")),
    ]


def test_list_since_is_inclusive_and_newest_first(db: SQLAlchemy, user_a: User, user_b: User) -> None:
    _add(user_a, "1.00", date(2026, 8, 23))
    on_the_day = _add(user_a, "1.00", date(2026, 8, 24))
    later = _add(user_a, "1.00", date(2026, 9, 1))
    _add(user_b, "1.00", date(2026, 9, 2))
    assert [e.id for e in expenses_repo.list_since(user_a.id, date(2026, 8, 24))] == [later.id, on_the_day.id]


# --- Service ---------------------------------------------------------------------------------------


def test_outlier_is_flagged_with_the_typical_amount(db: SQLAlchemy, user_a: User) -> None:
    _usual_dining(user_a)
    outlier = _add(user_a, "240.00", date(2026, 6, 20), note="Birthday dinner")
    flags = insights.unusual_expenses(user_a.id)
    assert set(flags) == {outlier.id}
    assert flags[outlier.id].typical == Decimal("20.00")


def test_other_users_expenses_are_not_the_yardstick(db: SQLAlchemy, user_a: User, user_b: User) -> None:
    # User B's cheap dining would make A's 240 look unusual if the users were mixed; A has too few expenses.
    _usual_dining(user_b)
    _add(user_a, "240.00", date(2026, 6, 20))
    assert insights.unusual_expenses(user_a.id) == {}
    assert insights.unusual_expenses(user_b.id) == {}


def test_other_categories_are_not_the_yardstick(db: SQLAlchemy, user_a: User) -> None:
    _usual_dining(user_a)
    _add(user_a, "1450.00", date(2026, 6, 1), "housing")  # far above dining, but it's the only housing expense
    assert insights.unusual_expenses(user_a.id) == {}


def test_recent_unusual_covers_the_last_90_days(db: SQLAlchemy, user_a: User, today: date) -> None:
    # Enough usual expenses that three outliers don't widen each other's yardstick too much to be flagged.
    for _ in range(6):
        _usual_dining(user_a)
    too_old = _add(user_a, "240.00", TODAY - timedelta(days=90))
    first_day = _add(user_a, "250.00", TODAY - timedelta(days=89))
    newest = _add(user_a, "260.00", TODAY)
    assert set(insights.unusual_expenses(user_a.id)) == {too_old.id, first_day.id, newest.id}
    assert [item.expense.id for item in insights.recent_unusual(user_a.id)] == [newest.id, first_day.id]


def test_nothing_recent_when_nothing_is_unusual(db: SQLAlchemy, user_a: User, today: date) -> None:
    _usual_dining(user_a, TODAY)
    assert insights.recent_unusual(user_a.id) == []


# --- Expense list ----------------------------------------------------------------------------------


def test_list_flags_unusual_expenses(client: FlaskClient, user_a: User, today: date) -> None:
    _usual_dining(user_a)
    outlier = _add(user_a, "240.00", date(2026, 6, 20), note="Birthday dinner")
    login(client, "a@example.com")
    page = client.get("/expenses/").get_data(as_text=True)

    flagged = re.findall(r'<li class="expense-item expense-item-unusual"[^>]*data-unusual', page)
    assert len(flagged) == 1
    assert page.count('<span class="badge">Unusual</span>') == 1
    assert "Much higher than your usual Dining out expense (about $20.00)." in page
    item = re.search(r'<li class="expense-item expense-item-unusual".*?</li>', page, re.DOTALL)
    assert item and f"/expenses/{outlier.id}/edit" in item.group(0)


def test_list_without_unusual_expenses_has_no_badges(client: FlaskClient, user_a: User, today: date) -> None:
    _usual_dining(user_a)
    login(client, "a@example.com")
    page = client.get("/expenses/").get_data(as_text=True)
    assert "Unusual" not in page
    assert "expense-item-unusual" not in page


# --- Dashboard -------------------------------------------------------------------------------------


def test_dashboard_lists_recent_unusual_expenses(client: FlaskClient, user_a: User, today: date) -> None:
    _usual_dining(user_a, date(2026, 10, 1))
    outlier = _add(user_a, "240.00", date(2026, 11, 2), note="<b>Birthday</b> dinner")
    login(client, "a@example.com")
    page = client.get("/dashboard/").get_data(as_text=True)

    panel = page[page.index('id="unusual-title"') : page.index('id="months-title"')]
    assert "From the last 90 days" in panel
    assert "Dining out" in panel and "$240.00" in panel
    assert "Nov 2, 2026" in panel
    assert "usually about $20.00" in panel
    assert "&lt;b&gt;Birthday&lt;/b&gt; dinner" in panel and "<b>" not in panel
    assert f'href="/expenses/{outlier.id}/edit"' in panel


def test_dashboard_says_when_nothing_is_unusual(client: FlaskClient, user_a: User, today: date) -> None:
    _add(user_a, "12.00", date(2026, 11, 2))
    login(client, "a@example.com")
    page = client.get("/dashboard/").get_data(as_text=True)
    assert "Nothing unusual. Flags appear once a category has at least 6 expenses." in page
    assert "unusual-item" not in page
