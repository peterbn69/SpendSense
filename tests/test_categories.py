import re

import pytest

from app import categories

SPEC_KEYS = [
    "housing", "groceries", "dining", "transport", "health", "shopping",
    "entertainment", "subscriptions", "education", "travel", "other",
]


def test_keys_match_the_spec_in_order() -> None:
    assert list(categories.KEYS) == SPEC_KEYS


def test_keys_fit_the_column_and_are_safe_in_sql() -> None:
    # The CHECK constraint quotes the keys directly, so they must be plain lowercase words.
    for key in categories.KEYS:
        assert re.fullmatch(r"[a-z_]{1,32}", key)


def test_labels() -> None:
    assert categories.label("housing") == "Housing & utilities"
    assert categories.label("health") == "Health & personal care"
    assert all(categories.label(key) for key in categories.KEYS)


def test_unknown_label_raises() -> None:
    with pytest.raises(KeyError):
        categories.label("rent")


def test_choices_are_key_label_pairs_in_order() -> None:
    assert categories.CHOICES[0] == ("housing", "Housing & utilities")
    assert [key for key, _ in categories.CHOICES] == SPEC_KEYS


@pytest.mark.parametrize(("key", "valid"), [("dining", True), ("Dining", False), ("", False), ("rent", False)])
def test_is_valid(key: str, valid: bool) -> None:
    assert categories.is_valid(key) is valid
