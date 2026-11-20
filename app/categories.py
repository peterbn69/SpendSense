"""
The database stores the key
Templates show the label.

Changing this list also needs a migration that replaces the ck_expenses_category_known CHECK constraint.
"""

CATEGORIES: dict[str, str] = {
    "housing": "Housing & utilities",
    "groceries": "Groceries",
    "dining": "Dining out",
    "transport": "Transportation",
    "health": "Health & personal care",
    "shopping": "Shopping",
    "entertainment": "Entertainment",
    "subscriptions": "Subscriptions",
    "education": "Education",
    "travel": "Travel",
    "other": "Other",
}

KEYS: tuple[str, ...] = tuple(CATEGORIES)

# The shape WTForms' SelectField expects.
CHOICES: list[tuple[str, str]] = list(CATEGORIES.items())


def label(key: str) -> str:
    return CATEGORIES[key]


def is_valid(key: str) -> bool:
    return key in CATEGORIES
