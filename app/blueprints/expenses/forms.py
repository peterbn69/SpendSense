from datetime import date
from decimal import Decimal
from typing import Any

from flask_wtf import FlaskForm
from wtforms import DateField, Field, SelectChoice, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, InputRequired, Length, StopValidation, ValidationError

from app import categories, clock
from app.services import expenses
from app.services.expenses import (
    AMOUNT_LIMIT,
    CATEGORY_MESSAGE,
    DATE_REQUIRED_MESSAGE,
    MIN_DATE,
    NOTE_LENGTH_MESSAGE,
    NOTE_MAX_LENGTH,
)

DATE_INVALID_MESSAGE = "Enter a real date, like 2026-10-05."


def _strip(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


class AmountField(StringField):
    # A text box for money. The service's parse_amount decides what counts as a valid amount.

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.amount: Decimal | None = None

    def _value(self) -> str:
        if self.raw_data:
            return self.raw_data[0]
        return "" if self.data is None else str(self.data)

    def pre_validate(self, form: FlaskForm) -> None:
        try:
            self.amount = expenses.parse_amount(self.data if isinstance(self.data, str) else None)
        except expenses.ExpenseRuleError as error:
            raise StopValidation(error.message) from None


class ExpenseForm(FlaskForm):
    amount = AmountField(
        "Amount",
        render_kw={
            "inputmode": "decimal",
            "autocomplete": "off",
            "type": "number",
            "step": "0.01",
            "min": "0.01",
            "max": str(AMOUNT_LIMIT - Decimal("0.01")),
        },
    )
    category = SelectField(
        "Category",
        choices=[SelectChoice("", "Choose a category")] + [SelectChoice(key, label) for key, label in categories.CHOICES],
        validators=[DataRequired(message=CATEGORY_MESSAGE)],
        invalid_choice_message=CATEGORY_MESSAGE,
    )
    spent_on = DateField(
        "Date",
        # InputRequired (not DataRequired), so text that isn't a date gets the "real date" message.
        validators=[InputRequired(message=DATE_REQUIRED_MESSAGE)],
        invalid_value_message=DATE_INVALID_MESSAGE,
    )
    note = StringField(
        "Note (optional)",
        filters=[_strip],
        validators=[Length(max=NOTE_MAX_LENGTH, message=NOTE_LENGTH_MESSAGE)],
        render_kw={"maxlength": NOTE_MAX_LENGTH, "autocomplete": "off"},
    )
    submit = SubmitField("Save expense")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # A new form starts at today. Not a field default: WTForms would also use it for a submission without a date.
        if not self.is_submitted() and self.spent_on.data is None:
            self.spent_on.data = clock.today()
        # Browser hints only; the server checks the same range below.
        self.spent_on.render_kw = {"min": MIN_DATE.isoformat(), "max": clock.today().isoformat()}

    def validate_spent_on(self, field: Field) -> None:
        if isinstance(field.data, date):
            try:
                expenses.check_spent_on(field.data)
            except expenses.ExpenseRuleError as error:
                raise ValidationError(error.message) from None


class DeleteForm(FlaskForm):
    # CSRF token only
    submit = SubmitField("Delete expense")
