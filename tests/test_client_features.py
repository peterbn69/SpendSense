"""M8: what the server hands to the scripts, and that every page still works without them."""

import html
import json
import re
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy

from app.models import Expense, User
from app.repositories import expenses as expenses_repo
from app.services import expenses
from tests.conftest import csrf_token, login

TODAY = date(2026, 11, 21)


@pytest.fixture
def today(fake_today: Callable[[date], None]) -> date:
    fake_today(TODAY)
    return TODAY


@pytest.fixture
def client_a(client: FlaskClient, user_a: User, today: date) -> FlaskClient:
    login(client, "a@example.com")
    return client


def _add(user: User, amount: str, spent_on: date, category: str = "groceries") -> Expense:
    expense = expenses_repo.add(user.id, Decimal(amount), category, spent_on, "")
    expenses_repo.db.session.commit()
    return expense


def _data(page: str, name: str) -> object:
    """The JSON in a single-quoted data- attribute, as the browser would read it."""
    match = re.search(rf"{name}='([^']*)'", page)
    assert match, f"no {name} attribute"
    return json.loads(html.unescape(match.group(1)))


def _attr(page: str, name: str) -> str:
    match = re.search(rf'{name}="([^"]*)"', page)
    assert match, f"no {name} attribute"
    return match.group(1)


def _running_total_text(page: str) -> str:
    match = re.search(r"<p class=\"running-total\".*?</p>", page, re.DOTALL)
    assert match
    return " ".join(re.sub(r"<[^>]+>", " ", match.group(0)).split())


# --- Monthly totals behind the running total ---------------------------------------------------------


def test_monthly_totals_group_by_month_and_user(db: SQLAlchemy, user_a: User, user_b: User) -> None:
    _add(user_a, "10.00", date(2026, 10, 1))
    _add(user_a, "5.25", date(2026, 10, 31))
    _add(user_a, "1.00", date(2026, 11, 2))
    _add(user_b, "99.00", date(2026, 10, 15))
    assert expenses_repo.monthly_totals(user_a.id) == {
        date(2026, 10, 1): Decimal("15.25"),
        date(2026, 11, 1): Decimal("1.00"),
    }


def test_monthly_totals_can_leave_one_expense_out(db: SQLAlchemy, user_a: User) -> None:
    kept = _add(user_a, "10.00", date(2026, 10, 1))
    left_out = _add(user_a, "5.00", date(2026, 10, 2))
    only = _add(user_a, "7.00", date(2026, 9, 2))
    totals = expenses_repo.monthly_totals(user_a.id, exclude_expense_id=left_out.id)
    assert totals == {date(2026, 10, 1): Decimal("10.00"), date(2026, 9, 1): Decimal("7.00")}
    assert expenses.month_totals(user_a.id, exclude_expense_id=only.id) == {date(2026, 10, 1): Decimal("15.00")}
    assert kept.id


# --- Expense form --------------------------------------------------------------------------------


def test_new_form_embeds_every_month_and_starts_at_this_month(
    client_a: FlaskClient, user_a: User, user_b: User
) -> None:
    _add(user_a, "1234.50", date(2026, 11, 3))
    _add(user_a, "0.75", date(2026, 11, 20))
    _add(user_a, "40.00", date(2026, 9, 9))
    _add(user_b, "500.00", date(2026, 11, 1))

    page = client_a.get("/expenses/new").get_data(as_text=True)
    assert _data(page, "data-month-totals") == {"2026-09": "40.00", "2026-11": "1235.25"}
    assert _attr(page, "data-month") == "2026-11"
    assert _attr(page, "data-amount-input") == "amount"
    assert _attr(page, "data-date-input") == "spent_on"
    # The no-JS text: this month's spending so far.
    assert _running_total_text(page) == "Spent in November 2026 : $1,235.25"
    assert "js/running-total.js" in page and "js/live-validation.js" in page


def test_new_form_for_a_new_user_starts_at_zero(client_a: FlaskClient) -> None:
    page = client_a.get("/expenses/new").get_data(as_text=True)
    assert _data(page, "data-month-totals") == {}
    assert _running_total_text(page) == "Spent in November 2026 : $0.00"


def test_edit_form_leaves_out_the_expense_being_edited(client_a: FlaskClient, user_a: User) -> None:
    _add(user_a, "100.00", date(2026, 10, 1))
    edited = _add(user_a, "25.50", date(2026, 10, 15))
    _add(user_a, "3.00", date(2026, 11, 1))

    page = client_a.get(f"/expenses/{edited.id}/edit").get_data(as_text=True)
    assert _data(page, "data-month-totals") == {"2026-10": "100.00", "2026-11": "3.00"}
    assert _attr(page, "data-month") == "2026-10"
    # Without JS the line shows the real month total: the others plus this expense's amount, counted once.
    assert _running_total_text(page) == "Spent in October 2026 : $125.50"


def test_edit_form_for_the_only_expense_in_a_month(client_a: FlaskClient, user_a: User) -> None:
    edited = _add(user_a, "8.00", date(2026, 8, 4))
    page = client_a.get(f"/expenses/{edited.id}/edit").get_data(as_text=True)
    assert _data(page, "data-month-totals") == {}
    assert _running_total_text(page) == "Spent in August 2026 : $8.00"


@pytest.mark.parametrize(
    ("typed", "expected"), [("12.50", "$22.50"), ("abc", "$10.00"), ("-5", "$10.00"), ("1000000", "$10.00")]
)
def test_rerendered_form_counts_only_a_valid_typed_amount(
    client_a: FlaskClient, user_a: User, typed: str, expected: str
) -> None:
    _add(user_a, "10.00", date(2026, 10, 1))
    data = {
        "amount": typed,
        "category": "",
        "spent_on": "2026-10-05",
        "note": "",
        "csrf_token": csrf_token(client_a, "/expenses/new"),
    }
    page = client_a.post("/expenses/new", data=data).get_data(as_text=True)
    assert _running_total_text(page) == f"Spent in October 2026 : {expected}"


def test_form_hands_the_server_rules_to_live_validation(client_a: FlaskClient) -> None:
    page = client_a.get("/expenses/new").get_data(as_text=True)
    rules = _data(page, "data-live-validation")
    assert isinstance(rules, dict)
    assert rules["amount"]["places"] == expenses.AMOUNT_PLACES_MESSAGE
    assert rules["amount"]["limit"] == expenses.AMOUNT_LIMIT_MESSAGE
    assert rules["spent_on"]["future"] == expenses.DATE_FUTURE_MESSAGE
    assert rules["spent_on"]["min"] == "2000-01-01"
    assert rules["spent_on"]["max"] == "2026-11-21"
    assert rules["note"]["max_length"] == 200


def test_amount_is_a_text_box_with_a_decimal_keypad(client_a: FlaskClient) -> None:
    page = client_a.get("/expenses/new").get_data(as_text=True)
    amount = re.search(r"<input[^>]*name=\"amount\"[^>]*>", page)
    assert amount
    tag = amount.group(0)
    assert 'type="text"' in tag
    assert 'inputmode="decimal"' in tag
    assert "required" in tag
    assert 'pattern="' in tag
    assert 'type="number"' not in tag


# --- Landing-page demo -----------------------------------------------------------------------------


def test_landing_demo_starts_from_the_sample_total(client: FlaskClient, db: SQLAlchemy, today: date) -> None:
    page = client.get("/").get_data(as_text=True)
    assert _data(page, "data-month-totals") == {"2026-11": "412.50"}
    assert _attr(page, "data-month") == "2026-11"
    assert _attr(page, "data-amount-input") == "demo-amount"
    assert "data-date-input" not in page
    assert _running_total_text(page) == "Spent in November 2026 : $412.50"
    assert "js/running-total.js" in page


def test_landing_demo_saves_nothing_and_hides_its_input_without_js(
    client: FlaskClient, db: SQLAlchemy, today: date
) -> None:
    page = client.get("/").get_data(as_text=True)
    assert "<form" not in page  # logged out: no form at all, so the demo can't submit anything
    assert re.search(r"<div class=\"field\" data-running-total-reveal hidden>", page)
    assert 'id="demo-amount"' in page


# --- Category filter -------------------------------------------------------------------------------


@pytest.fixture
def three_expenses(user_a: User) -> None:
    _add(user_a, "10.00", date(2026, 11, 1), "dining")
    _add(user_a, "20.00", date(2026, 11, 2), "groceries")
    _add(user_a, "30.00", date(2026, 11, 3), "groceries")


def _hidden_categories(page: str) -> list[tuple[str, bool]]:
    return [
        (category, hidden == " hidden") for category, hidden in re.findall(r'data-category="(\w+)"( hidden)?>', page)
    ]


def test_list_without_filter_shows_everything(client_a: FlaskClient, three_expenses: None) -> None:
    page = client_a.get("/expenses/").get_data(as_text=True)
    assert _hidden_categories(page) == [("groceries", False), ("groceries", False), ("dining", False)]
    assert "3 expenses, newest first." in page
    assert '<option selected value="">All categories</option>' in page
    assert re.search(r"<p class=\"notice\" data-filter-empty hidden>", page)
    assert "js/category-filter.js" in page


def test_filter_form_is_a_get_form_without_csrf(client_a: FlaskClient, three_expenses: None) -> None:
    page = client_a.get("/expenses/").get_data(as_text=True)
    form = re.search(r"<form class=\"filter-form\".*?</form>", page, re.DOTALL)
    assert form
    assert 'method="get"' in form.group(0)
    assert "csrf_token" not in form.group(0)
    assert 'name="category"' in form.group(0)


def test_filter_works_without_js(client_a: FlaskClient, three_expenses: None) -> None:
    page = client_a.get("/expenses/?category=groceries").get_data(as_text=True)
    assert _hidden_categories(page) == [("groceries", False), ("groceries", False), ("dining", True)]
    assert "2 of 3 expenses, newest first." in page
    assert '<option selected value="groceries">Groceries</option>' in page


def test_filter_with_no_matches_says_so(client_a: FlaskClient, three_expenses: None) -> None:
    page = client_a.get("/expenses/?category=travel").get_data(as_text=True)
    assert all(hidden for _, hidden in _hidden_categories(page))
    assert "0 of 3 expenses" in page
    assert re.search(r"<p class=\"notice\" data-filter-empty>", page)


@pytest.mark.parametrize("category", ["rent", "Dining", "<script>", "", "x" * 5000])
def test_unknown_filter_is_ignored(client_a: FlaskClient, three_expenses: None, category: str) -> None:
    response = client_a.get("/expenses/", query_string={"category": category})
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert not any(hidden for _, hidden in _hidden_categories(page))
    assert "3 expenses, newest first." in page
    assert "<script>" not in page.replace('<script src="', "")


def test_no_filter_on_an_empty_list(client_a: FlaskClient) -> None:
    page = client_a.get("/expenses/").get_data(as_text=True)
    assert "filter-form" not in page
    assert "No expenses yet" in page


# --- The scripts are served ------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["running-total.js", "live-validation.js", "category-filter.js"])
def test_scripts_are_served(client: FlaskClient, name: str) -> None:
    response = client.get(f"/static/js/{name}")
    assert response.status_code == 200
    assert "javascript" in response.content_type
    response.close()


def test_hidden_attribute_beats_display_rules(client: FlaskClient) -> None:
    # The filter and the demo rely on the hidden attribute; a rule like .expense-item { display: grid } would
    # otherwise keep "hidden" items on screen, with or without JS.
    response = client.get("/static/css/style.css")
    css = response.get_data(as_text=True)
    response.close()
    assert re.search(r"\[hidden\]\s*\{\s*display:\s*none\s*!important;\s*\}", css)
