"""Jinja filters for showing values. Money stays a Decimal; nothing here converts to float."""

from datetime import date
from decimal import Decimal

from flask import Flask

from app import categories


def money(value: Decimal) -> str:
    # e.g., $1,234.50
    return f"${value:,.2f}"


def long_date(value: date) -> str:
    # e.g., Oct 5, 2026
    return f"{value:%b} {value.day}, {value.year}"


def register_filters(app: Flask) -> None:
    app.add_template_filter(money, "money")
    app.add_template_filter(long_date, "long_date")
    app.add_template_filter(categories.label, "category_label")
