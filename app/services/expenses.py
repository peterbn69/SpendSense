"""Expense rules and changes. The form checks these rules first; this layer checks them again and owns commits."""

import re
from datetime import date
from decimal import Decimal

from app import categories, clock
from app.extensions import db
from app.models import Expense
from app.repositories import expenses

AMOUNT_LIMIT = Decimal("1000000")
MIN_DATE = date(2000, 1, 1)
NOTE_MAX_LENGTH = 200
MAX_EXPENSE_ID = 2**63 - 1

AMOUNT_REQUIRED_MESSAGE = "Enter an amount."
AMOUNT_FORMAT_MESSAGE = "Enter a number, like 12.50."
AMOUNT_POSITIVE_MESSAGE = "Enter an amount above 0."
AMOUNT_PLACES_MESSAGE = "Use at most 2 decimal places."
AMOUNT_LIMIT_MESSAGE = "Enter an amount under 1,000,000."
CATEGORY_MESSAGE = "Choose a category."
DATE_REQUIRED_MESSAGE = "Enter the date of the expense."
DATE_FUTURE_MESSAGE = "The date can't be in the future."
DATE_TOO_EARLY_MESSAGE = f"Use a date on or after {MIN_DATE:%B} {MIN_DATE.day}, {MIN_DATE.year}."
NOTE_LENGTH_MESSAGE = f"Use at most {NOTE_MAX_LENGTH} characters."

# Plain digits with an optional decimal part: no signs, exponents, NaN or Infinity.
_AMOUNT_PATTERN = re.compile(r"\d+(?:\.\d+)?|\.\d+")


class ExpenseRuleError(ValueError):
    # A value breaks an expense rule; `field` names the form field it belongs to.

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


def parse_amount(text: str | None) -> Decimal:
    # Turn typed text into a two-place Decimal, or raise ExpenseRuleError with a message for the user.
    text = (text or "").strip()
    if not text:
        raise ExpenseRuleError("amount", AMOUNT_REQUIRED_MESSAGE)
    if text.startswith("-"):
        raise ExpenseRuleError("amount", AMOUNT_POSITIVE_MESSAGE)
    if not _AMOUNT_PATTERN.fullmatch(text):
        raise ExpenseRuleError("amount", AMOUNT_FORMAT_MESSAGE)
    amount = Decimal(text)
    check_amount(amount)
    # Judge the typed text, so "1.500" is rejected too even though it equals 1.50.
    if len(text.partition(".")[2]) > 2:
        raise ExpenseRuleError("amount", AMOUNT_PLACES_MESSAGE)
    return amount.quantize(Decimal("0.01"))


def check_amount(amount: Decimal) -> None:
    if not amount.is_finite():
        raise ExpenseRuleError("amount", AMOUNT_FORMAT_MESSAGE)
    if amount <= 0:
        raise ExpenseRuleError("amount", AMOUNT_POSITIVE_MESSAGE)
    if amount >= AMOUNT_LIMIT:
        raise ExpenseRuleError("amount", AMOUNT_LIMIT_MESSAGE)
    if amount != amount.quantize(Decimal("0.01")):
        raise ExpenseRuleError("amount", AMOUNT_PLACES_MESSAGE)


def check_spent_on(spent_on: date) -> None:
    # No date before MIN_DATE, and none after today in APP_TIMEZONE.
    if spent_on < MIN_DATE:
        raise ExpenseRuleError("spent_on", DATE_TOO_EARLY_MESSAGE)
    if spent_on > clock.today():
        raise ExpenseRuleError("spent_on", DATE_FUTURE_MESSAGE)


def _check(amount: Decimal, category: str, spent_on: date, note: str) -> None:
    check_amount(amount)
    if not categories.is_valid(category):
        raise ExpenseRuleError("category", CATEGORY_MESSAGE)
    check_spent_on(spent_on)
    if len(note) > NOTE_MAX_LENGTH:
        raise ExpenseRuleError("note", NOTE_LENGTH_MESSAGE)


def list_expenses(user_id: int) -> list[Expense]:
    return expenses.list_for_user(user_id)


def month_totals(user_id: int, exclude_expense_id: int | None = None) -> dict[date, Decimal]:
    return expenses.monthly_totals(user_id, exclude_expense_id)


def get_expense(user_id: int, expense_id: int) -> Expense | None:
    # The user's expense, or None if it is missing, someone else's, or the id is out of range.
    if not 1 <= expense_id <= MAX_EXPENSE_ID:
        return None
    return expenses.get(user_id, expense_id)


def create(user_id: int, amount: Decimal, category: str, spent_on: date, note: str = "") -> Expense:
    note = note.strip()
    _check(amount, category, spent_on, note)
    expense = expenses.add(user_id, amount, category, spent_on, note)
    db.session.commit()
    return expense


def update(user_id: int, expense_id: int, amount: Decimal, category: str, spent_on: date, note: str = "") -> Expense | None:
    # The changed expense, or None if it isn't the user's (the caller answers 404).
    if get_expense(user_id, expense_id) is None:
        return None
    note = note.strip()
    _check(amount, category, spent_on, note)
    expense = expenses.update(user_id, expense_id, amount, category, spent_on, note)
    db.session.commit()
    return expense


def delete(user_id: int, expense_id: int) -> bool:
    # True if the user's expense was deleted; False if it isn't theirs (the caller answers 404).
    if not 1 <= expense_id <= MAX_EXPENSE_ID:
        return False
    deleted = expenses.delete_one(user_id, expense_id)
    db.session.commit()
    return deleted
