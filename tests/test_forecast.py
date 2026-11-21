from decimal import Decimal

import pytest

from app.analytics.forecast import forecast


def d(*values: str) -> list[Decimal]:
    return [Decimal(value) for value in values]


@pytest.mark.parametrize("history", [d(), d("10.00"), d("10.00", "20.00")])
def test_fewer_than_three_months_is_none(history: list[Decimal]) -> None:
    assert forecast(history) is None


def test_three_months_are_averaged() -> None:
    assert forecast(d("10.00", "20.00", "30.00")) == Decimal("20.00")


def test_six_months_average_the_last_three() -> None:
    assert forecast(d("1000.00", "1000.00", "1000.00", "30.00", "60.00", "90.00")) == Decimal("60.00")


def test_rounds_half_up_to_the_cent() -> None:
    assert forecast(d("10.00", "10.00", "10.01")) == Decimal("10.00")  # 10.0033...
    assert forecast(d("10.00", "10.01", "10.01")) == Decimal("10.01")  # 10.0066...
    assert forecast(d("0.00", "0.00", "0.03")) == Decimal("0.01")
    assert forecast(d("0.00", "0.01", "0.02")) == Decimal("0.01")
    assert forecast(d("0.00", "0.00", "0.015")) == Decimal("0.01")  # 0.005 rounds up, not to even


def test_zero_months_count_as_history() -> None:
    assert forecast(d("0", "0", "0")) == Decimal("0.00")
    assert forecast(d("90.00", "0", "0")) == Decimal("30.00")


def test_result_is_a_two_place_decimal() -> None:
    result = forecast(d("1", "2", "4"))
    assert isinstance(result, Decimal)
    assert result == Decimal("2.33")
    assert result.as_tuple().exponent == -2


def test_large_amounts_stay_exact() -> None:
    assert forecast(d("9999999999.99", "9999999999.99", "9999999999.99")) == Decimal("9999999999.99")


def test_does_not_change_the_history() -> None:
    history = d("1", "2", "3", "4")
    forecast(history)
    assert history == d("1", "2", "3", "4")


def test_accepts_any_sequence() -> None:
    assert forecast(tuple(d("3", "3", "3"))) == Decimal("3.00")
