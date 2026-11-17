from argon2 import PasswordHasher
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User
from app.repositories import users

EMAIL_UNIQUE_CONSTRAINT = "uq_users_email"

_hasher = PasswordHasher()


class EmailTakenError(Exception):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_email_registered(email: str) -> bool:
    return users.get_by_email(normalize_email(email)) is not None


def register(email: str, password: str) -> User:
    email = normalize_email(email)
    if users.get_by_email(email) is not None:
        raise EmailTakenError(email)

    try:
        user = users.add(email, _hasher.hash(password))
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        if _violated_constraint(error) == EMAIL_UNIQUE_CONSTRAINT:
            raise EmailTakenError(email) from error
        raise
    return user


def _violated_constraint(error: IntegrityError) -> str | None:
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None)
