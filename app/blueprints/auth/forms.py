from flask_wtf import FlaskForm
from wtforms import EmailField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from app.services import auth

EMAIL_MAX_LENGTH = 254
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

EMAIL_TAKEN_MESSAGE = "An account with this email already exists. Please log in instead."


def _strip(value: str | None) -> str | None:
    return value.strip() if isinstance(value, str) else value


class RegisterForm(FlaskForm):
    email = EmailField(
        "Email",
        filters=[_strip],
        validators=[
            DataRequired(message="Enter your email address."),
            Length(max=EMAIL_MAX_LENGTH, message=f"Use at most {EMAIL_MAX_LENGTH} characters."),
            Email(message="Enter a valid email address, like name@example.com."),
        ],
        render_kw={"autocomplete": "email"},
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Choose a password."),
            Length(
                min=PASSWORD_MIN_LENGTH,
                max=PASSWORD_MAX_LENGTH,
                message=f"Use {PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters.",
            ),
        ],
        render_kw={"autocomplete": "new-password"},
    )
    confirm = PasswordField(
        "Confirm password",
        validators=[
            DataRequired(message="Type your password again."),
            EqualTo("password", message="The passwords don't match."),
        ],
        render_kw={"autocomplete": "new-password"},
    )
    submit = SubmitField("Create account")

    def validate_email(self, field: EmailField) -> None:
        # Friendly early check; auth.register() still catches the race at the database.
        if auth.is_email_registered(field.data):
            raise ValidationError(EMAIL_TAKEN_MESSAGE)
