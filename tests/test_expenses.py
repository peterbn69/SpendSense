from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from werkzeug.test import TestResponse

from app import clock
from app.models import Expense, User
from app.repositories import expenses as expenses_repo
from app.services import expenses
from app.services.expenses import ExpenseRuleError
from tests.conftest import csrf_token, login

TODAY = date(2026, 11, 20)
LIST = "/expenses/"
NEW = "/expenses/new"
VALID = {"amount": "12.50", "category": "dining", "spent_on": "2026-11-19", "note": "Lunch"}


@pytest.fixture
def today(fake_today: Callable[[date], None]) -> date:
    fake_today(TODAY)
    return TODAY


@pytest.fixture
def client_a(client: FlaskClient, user_a: User, today: date) -> FlaskClient:
    login(client, "a@example.com")
    return client


def _post(client: FlaskClient, path: str, data: dict[str, str] | None = None, token_from: str = NEW) -> TestResponse:
    return client.post(path, data={**(data or {}), "csrf_token": csrf_token(client, token_from)})


def _add(
    user: User, amount: str = "10.00", spent_on: date = date(2026, 11, 1), note: str = "", category: str = "groceries"
) -> Expense:
    expense = expenses_repo.add(user.id, Decimal(amount), category, spent_on, note)
    expenses_repo.db.session.commit()
    return expense


def _html(response: TestResponse) -> str:
    return response.get_data(as_text=True)


# --- Login is required -----------------------------------------------------------------------------


@pytest.mark.parametrize("path", [LIST, NEW, "/expenses/1/edit", "/expenses/1/delete"])
def test_pages_require_login(client: FlaskClient, db: SQLAlchemy, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/auth/login")


def test_nav_links_to_expenses(client_a: FlaskClient) -> None:
    assert 'href="/expenses/"' in _html(client_a.get("/dashboard/"))


# --- Create --------------------------------------------------------------------------------------


def test_new_form_defaults_to_today(client_a: FlaskClient) -> None:
    html = _html(client_a.get(NEW))
    assert 'value="2026-11-20"' in html
    assert 'max="2026-11-20"' in html
    assert 'min="2000-01-01"' in html
    assert "Choose a category" in html


def test_create_saves_and_redirects(client_a: FlaskClient, user_a: User) -> None:
    response = _post(client_a, NEW, {**VALID, "note": "  Lunch with Sam  "})
    assert response.status_code == 302
    assert response.headers["Location"] == LIST

    (expense,) = expenses_repo.list_for_user(user_a.id)
    assert (expense.amount, expense.category, expense.spent_on, expense.note) == (
        Decimal("12.50"),
        "dining",
        date(2026, 11, 19),
        "Lunch with Sam",
    )
    assert "Expense added." in _html(client_a.get(LIST))


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("12", "12.00"),
        ("12.5", "12.50"),
        (".5", "0.50"),
        ("0.01", "0.01"),
        ("999999.99", "999999.99"),
        (" 7.25 ", "7.25"),
    ],
)
def test_amount_accepted(client_a: FlaskClient, user_a: User, typed: str, stored: str) -> None:
    assert _post(client_a, NEW, {**VALID, "amount": typed}).status_code == 302
    (expense,) = expenses_repo.list_for_user(user_a.id)
    assert expense.amount == Decimal(stored)


@pytest.mark.parametrize(
    ("typed", "message"),
    [
        ("", expenses.AMOUNT_REQUIRED_MESSAGE),
        ("   ", expenses.AMOUNT_REQUIRED_MESSAGE),
        ("0", expenses.AMOUNT_POSITIVE_MESSAGE),
        ("0.00", expenses.AMOUNT_POSITIVE_MESSAGE),
        ("-5", expenses.AMOUNT_POSITIVE_MESSAGE),
        ("-0.01", expenses.AMOUNT_POSITIVE_MESSAGE),
        ("1000000", expenses.AMOUNT_LIMIT_MESSAGE),
        ("1000000.00", expenses.AMOUNT_LIMIT_MESSAGE),
        ("9" * 5000, expenses.AMOUNT_LIMIT_MESSAGE),
        ("12.345", expenses.AMOUNT_PLACES_MESSAGE),
        ("1.500", expenses.AMOUNT_PLACES_MESSAGE),
        ("abc", expenses.AMOUNT_FORMAT_MESSAGE),
        ("12,50", expenses.AMOUNT_FORMAT_MESSAGE),
        ("$12", expenses.AMOUNT_FORMAT_MESSAGE),
        ("NaN", expenses.AMOUNT_FORMAT_MESSAGE),
        ("Infinity", expenses.AMOUNT_FORMAT_MESSAGE),
        ("1e5", expenses.AMOUNT_FORMAT_MESSAGE),
        ("+5", expenses.AMOUNT_FORMAT_MESSAGE),
        ("1.2.3", expenses.AMOUNT_FORMAT_MESSAGE),
    ],
)
def test_bad_amount_rejected(client_a: FlaskClient, user_a: User, typed: str, message: str) -> None:
    response = _post(client_a, NEW, {**VALID, "amount": typed})
    assert response.status_code == 200
    assert message.replace("'", "&#39;") in _html(response)
    assert expenses_repo.count_for_user(user_a.id) == 0


def test_typed_amount_is_kept_after_an_error(client_a: FlaskClient) -> None:
    html = _html(_post(client_a, NEW, {**VALID, "amount": "12.345"}))
    assert 'value="12.345"' in html


@pytest.mark.parametrize("category", ["", "rent", "Dining", "x" * 500])
def test_bad_category_rejected(client_a: FlaskClient, user_a: User, category: str) -> None:
    response = _post(client_a, NEW, {**VALID, "category": category})
    assert response.status_code == 200
    assert expenses.CATEGORY_MESSAGE in _html(response)
    assert expenses_repo.count_for_user(user_a.id) == 0


@pytest.mark.parametrize("spent_on", ["2026-11-20", "2000-01-01", "2024-02-29"])
def test_date_accepted(client_a: FlaskClient, user_a: User, spent_on: str) -> None:
    assert _post(client_a, NEW, {**VALID, "spent_on": spent_on}).status_code == 302
    assert expenses_repo.count_for_user(user_a.id) == 1


@pytest.mark.parametrize(
    ("spent_on", "message"),
    [
        ("2026-11-21", expenses.DATE_FUTURE_MESSAGE),
        ("9999-12-31", expenses.DATE_FUTURE_MESSAGE),
        ("1999-12-31", expenses.DATE_TOO_EARLY_MESSAGE),
        ("1926-11-19", expenses.DATE_TOO_EARLY_MESSAGE),
        ("", expenses.DATE_REQUIRED_MESSAGE),
        ("2026-02-30", "Enter a real date"),
        ("not a date", "Enter a real date"),
        ("20261-01-01", "Enter a real date"),
        ("11/19/2026", "Enter a real date"),
    ],
)
def test_bad_date_rejected(client_a: FlaskClient, user_a: User, spent_on: str, message: str) -> None:
    response = _post(client_a, NEW, {**VALID, "spent_on": spent_on})
    assert response.status_code == 200
    assert message.replace("'", "&#39;") in _html(response)
    assert expenses_repo.count_for_user(user_a.id) == 0


def test_missing_date_is_required_not_today(client_a: FlaskClient, user_a: User) -> None:
    data = {key: value for key, value in VALID.items() if key != "spent_on"}
    response = _post(client_a, NEW, data)
    assert response.status_code == 200
    assert expenses.DATE_REQUIRED_MESSAGE in _html(response)
    assert expenses_repo.count_for_user(user_a.id) == 0


def test_future_is_judged_in_app_timezone(client: FlaskClient, user_a: User, monkeypatch: pytest.MonkeyPatch) -> None:
    # 03:00 UTC on 1 November is still 31 October in Toronto, so 1 November is tomorrow there.
    monkeypatch.setattr(clock, "_utc_now", lambda: datetime(2026, 11, 1, 3, 0, tzinfo=UTC))
    login(client, "a@example.com")
    assert _post(client, NEW, {**VALID, "spent_on": "2026-11-01"}).status_code == 200
    assert _post(client, NEW, {**VALID, "spent_on": "2026-10-31"}).status_code == 302
    assert expenses_repo.count_for_user(user_a.id) == 1


def test_note_is_optional(client_a: FlaskClient, user_a: User) -> None:
    data = {key: value for key, value in VALID.items() if key != "note"}
    assert _post(client_a, NEW, data).status_code == 302
    (expense,) = expenses_repo.list_for_user(user_a.id)
    assert expense.note == ""


def test_note_of_200_accepted_and_201_rejected(client_a: FlaskClient, user_a: User) -> None:
    assert _post(client_a, NEW, {**VALID, "note": "x" * 200}).status_code == 302
    response = _post(client_a, NEW, {**VALID, "note": "x" * 201})
    assert response.status_code == 200
    assert expenses.NOTE_LENGTH_MESSAGE in _html(response)
    assert expenses_repo.count_for_user(user_a.id) == 1


def test_blank_form_shows_every_error(client_a: FlaskClient, user_a: User) -> None:
    html = _html(_post(client_a, NEW, {}))
    for message in (expenses.AMOUNT_REQUIRED_MESSAGE, expenses.CATEGORY_MESSAGE, expenses.DATE_REQUIRED_MESSAGE):
        assert message in html
    assert expenses_repo.count_for_user(user_a.id) == 0


def test_create_without_csrf_token_rejected(client_a: FlaskClient, user_a: User) -> None:
    assert client_a.post(NEW, data=VALID).status_code == 400
    assert expenses_repo.count_for_user(user_a.id) == 0


# --- Read ----------------------------------------------------------------------------------------


def test_empty_list_shows_empty_state(client_a: FlaskClient) -> None:
    html = _html(client_a.get(LIST))
    assert "No expenses yet" in html
    assert 'href="/expenses/new"' in html


def test_list_shows_own_expenses_newest_first(client_a: FlaskClient, user_a: User, user_b: User) -> None:
    _add(user_a, "1234.50", date(2026, 10, 3), "Older", "housing")
    _add(user_a, "8.00", date(2026, 11, 18), "Newer", "dining")
    _add(user_b, "99.00", date(2026, 11, 19), "Someone else's")

    html = _html(client_a.get(LIST))
    assert html.index("Newer") < html.index("Older")
    assert "Someone else" not in html
    assert "$1,234.50" in html and "$8.00" in html
    assert "Housing &amp; utilities" in html and "Dining out" in html
    assert "Oct 3, 2026" in html
    assert "No expenses yet" not in html


def test_note_is_escaped(client_a: FlaskClient, user_a: User) -> None:
    _add(user_a, note="<script>alert(1)</script>")
    html = _html(client_a.get(LIST))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# --- Update --------------------------------------------------------------------------------------


def test_edit_form_is_prefilled(client_a: FlaskClient, user_a: User) -> None:
    expense = _add(user_a, "42.10", date(2026, 11, 2), "Market")
    html = _html(client_a.get(f"/expenses/{expense.id}/edit"))
    assert 'value="42.10"' in html
    assert 'value="2026-11-02"' in html
    assert 'value="Market"' in html
    assert '<option selected value="groceries">' in html


def test_edit_saves_changes(client_a: FlaskClient, user_a: User) -> None:
    expense = _add(user_a)
    path = f"/expenses/{expense.id}/edit"
    response = _post(
        client_a, path, {"amount": "15.75", "category": "transport", "spent_on": "2026-11-03", "note": "Taxi"}, path
    )
    assert response.status_code == 302
    assert response.headers["Location"] == LIST

    expenses_repo.db.session.expire_all()
    changed = expenses_repo.get(user_a.id, expense.id)
    assert changed is not None
    assert (changed.amount, changed.category, changed.spent_on, changed.note) == (
        Decimal("15.75"),
        "transport",
        date(2026, 11, 3),
        "Taxi",
    )


def test_bad_edit_changes_nothing(client_a: FlaskClient, user_a: User) -> None:
    expense = _add(user_a, "10.00")
    path = f"/expenses/{expense.id}/edit"
    response = _post(client_a, path, {**VALID, "amount": "-3", "spent_on": "2026-12-01"}, path)
    assert response.status_code == 200
    html = _html(response)
    assert expenses.AMOUNT_POSITIVE_MESSAGE in html
    assert expenses.DATE_FUTURE_MESSAGE.replace("'", "&#39;") in html

    expenses_repo.db.session.expire_all()
    unchanged = expenses_repo.get(user_a.id, expense.id)
    assert unchanged is not None and unchanged.amount == Decimal("10.00")


# --- Delete --------------------------------------------------------------------------------------


def test_delete_asks_first_and_get_deletes_nothing(client_a: FlaskClient, user_a: User) -> None:
    expense = _add(user_a, "10.00", note="Market")
    response = client_a.get(f"/expenses/{expense.id}/delete")
    assert response.status_code == 200
    html = _html(response)
    assert "Delete this expense?" in html
    assert "$10.00" in html and "Market" in html
    assert 'name="csrf_token"' in html
    assert expenses_repo.count_for_user(user_a.id) == 1


def test_delete_removes_the_expense(client_a: FlaskClient, user_a: User) -> None:
    expense = _add(user_a)
    kept = _add(user_a)
    path = f"/expenses/{expense.id}/delete"
    response = _post(client_a, path, token_from=path)
    assert response.status_code == 302
    assert response.headers["Location"] == LIST
    assert [e.id for e in expenses_repo.list_for_user(user_a.id)] == [kept.id]
    assert "Expense deleted." in _html(client_a.get(LIST))

    # Deleting it again finds nothing.
    assert _post(client_a, path, token_from=NEW).status_code == 404


def test_delete_without_csrf_token_rejected(client_a: FlaskClient, user_a: User) -> None:
    expense = _add(user_a)
    assert client_a.post(f"/expenses/{expense.id}/delete").status_code == 400
    assert expenses_repo.count_for_user(user_a.id) == 1


# --- Done when: user B gets a 404 for every one of user A's expense IDs -----------------------------


def test_user_b_gets_404_for_every_one_of_user_as_expenses(
    client: FlaskClient, user_a: User, user_b: User, today: date
) -> None:
    a_expenses = [_add(user_a, f"{n}.00", date(2026, 11, n), f"A's expense {n}") for n in range(1, 6)]
    login(client, "b@example.com")

    for expense in a_expenses:
        edit, delete = f"/expenses/{expense.id}/edit", f"/expenses/{expense.id}/delete"
        assert client.get(edit).status_code == 404
        assert _post(client, edit, {**VALID, "amount": "1.00", "note": "hijacked"}).status_code == 404
        assert client.get(delete).status_code == 404
        assert _post(client, delete).status_code == 404

    expenses_repo.db.session.expire_all()
    assert [(e.amount, e.note) for e in expenses_repo.list_for_user(user_a.id)] == [
        (e.amount, e.note) for e in reversed(a_expenses)
    ]
    assert "A&#39;s expense" not in _html(client.get(LIST))


@pytest.mark.parametrize("expense_id", ["999999", "0", "-1", "abc", str(2**63), "9" * 40])
def test_missing_or_impossible_id_is_404(client_a: FlaskClient, expense_id: str) -> None:
    for path in (f"/expenses/{expense_id}/edit", f"/expenses/{expense_id}/delete"):
        assert client_a.get(path).status_code == 404
        assert _post(client_a, path).status_code == 404


# --- Service rules hold even if a form has a bug --------------------------------------------------


@pytest.mark.parametrize(
    ("fields", "field"),
    [
        ({"amount": Decimal(0)}, "amount"),
        ({"amount": Decimal(1000000)}, "amount"),
        ({"amount": Decimal("1.005")}, "amount"),
        ({"amount": Decimal("NaN")}, "amount"),
        ({"category": "rent"}, "category"),
        ({"spent_on": date(2026, 11, 21)}, "spent_on"),
        ({"spent_on": date(1999, 12, 31)}, "spent_on"),
        ({"note": "x" * 201}, "note"),
    ],
)
def test_service_enforces_rules(user_a: User, today: date, fields: dict[str, object], field: str) -> None:
    values: dict[str, object] = {"amount": Decimal("5.00"), "category": "other", "spent_on": TODAY, "note": ""}
    values.update(fields)
    with pytest.raises(ExpenseRuleError) as error:
        expenses.create(user_a.id, **values)  # type: ignore[arg-type]
    assert error.value.field == field
    assert expenses_repo.count_for_user(user_a.id) == 0


def test_service_update_and_delete_ignore_other_users(user_a: User, user_b: User, today: date) -> None:
    expense = _add(user_a)
    assert expenses.update(user_b.id, expense.id, Decimal("1.00"), "other", TODAY, "") is None
    assert expenses.delete(user_b.id, expense.id) is False
    assert expenses.get_expense(user_b.id, expense.id) is None
    assert expenses.get_expense(user_a.id, 2**63) is None
    assert expenses_repo.count_for_user(user_a.id) == 1
