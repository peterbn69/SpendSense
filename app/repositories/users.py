from sqlalchemy import select

from app.extensions import db
from app.models import User


def get_by_id(user_id: int) -> User | None:
    return db.session.get(User, user_id)


def get_by_email(email: str) -> User | None:
    # Exact match, since the service already lowercased the email.
    return db.session.scalar(select(User).where(User.email == email))


def set_password_hash(user: User, password_hash: str) -> None:
    user.password_hash = password_hash
    db.session.flush()


def add(email: str, password_hash: str) -> User:
    # Stage a new user and flush, so it gets an id and a duplicate email fails here.
    user = User(email=email, password_hash=password_hash)  # pyrefly: ignore[unexpected-keyword]
    db.session.add(user)
    db.session.flush()
    return user
