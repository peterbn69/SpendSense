from functools import cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User
from app.repositories import users

EMAIL_UNIQUE_CONSTRAINT = "uq_users_email"
PASSWORD_MAX_LENGTH = 128
_MAX_USER_ID = 2**63 - 1

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


def authenticate(email: str, password: str) -> User | None:
    if len(password) > PASSWORD_MAX_LENGTH:
        return None

    user = users.get_by_email(normalize_email(email))
    if user is None:
        # Spend the same Argon2 time as a real check, so response time doesn't reveal which emails exist.
        _verify(_dummy_hash(), password)
        return None
    if not _verify(user.password_hash, password):
        return None

    if _hasher.check_needs_rehash(user.password_hash):
        users.set_password_hash(user, _hasher.hash(password))
        db.session.commit()
    return user


def load_user(user_id: str) -> User | None:
    # Flask-Login's user_loader: the id stored in the session, or None if it is unusable.
    try:
        id_ = int(user_id)
    except (TypeError, ValueError):
        return None
    if not 1 <= id_ <= _MAX_USER_ID:
        return None
    return users.get_by_id(id_)


def _verify(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@cache
def _dummy_hash() -> str:
    return _hasher.hash("not a real password")


def _violated_constraint(error: IntegrityError) -> str | None:
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None)
