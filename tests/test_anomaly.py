import statistics
from decimal import Decimal

import pytest

from app.analytics.anomaly import MIN_POINTS, THRESHOLD, Anomaly, flag_unusual, z_score


def d(*values: str) -> list[Decimal]:
    return [Decimal(value) for value in values]


# --- z_score ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("count", range(MIN_POINTS))
def test_too_few_points_give_no_result(count: int) -> None:
    others = [Decimal(n + 1) for n in range(count)]
    assert z_score(Decimal(1000), others) is None


def test_five_points_are_enough() -> None:
    assert MIN_POINTS == 5
    assert z_score(Decimal(1000), d("1", "2", "3", "4", "5")) is not None


@pytest.mark.parametrize("value", ["12.00", "9999.99", "0.01"])
def test_standard_deviation_of_zero_gives_no_result(value: str) -> None:
    assert z_score(Decimal(value), d("12.00", "12.00", "12.00", "12.00", "12.00", "12.00")) is None


def test_matches_the_textbook_sample_z_score() -> None:
    others = d("10.00", "12.50", "9.75", "11.00", "13.25", "10.40")
    value = Decimal("30.00")
    floats = [float(x) for x in others]
    expected = (float(value) - statistics.mean(floats)) / statistics.stdev(floats)
    result = z_score(value, others)
    assert result is not None
    assert float(result) == pytest.approx(expected, rel=1e-12)


def test_sign_shows_direction() -> None:
    others = d("10", "11", "12", "13", "14")
    assert z_score(Decimal(12), others) == 0
    assert z_score(Decimal(20), others) > 0  # type: ignore[operator]
    assert z_score(Decimal(1), others) < 0  # type: ignore[operator]


def test_works_with_huge_amounts() -> None:
    others = d("9999999999.97", "9999999999.98", "9999999999.99", "9999999999.98", "9999999999.97")
    result = z_score(Decimal("9999999999.99"), others)
    assert result is not None and result > 0


def test_tiny_spread_is_not_mistaken_for_zero() -> None:
    others = d("1000000.00", "1000000.00", "1000000.00", "1000000.00", "1000000.01")
    assert z_score(Decimal("1000000.00"), others) is not None


# --- flag_unusual ----------------------------------------------------------------------------------


def _rows(category: str, *amounts: str, start: int = 1) -> list[tuple[int, str, Decimal]]:
    return [(start + index, category, Decimal(amount)) for index, amount in enumerate(amounts)]


def test_flags_a_clear_outlier_with_its_typical_amount() -> None:
    rows = _rows("dining", "20.00", "22.00", "18.00", "21.00", "19.00", "240.00")
    flags = flag_unusual(rows)
    assert set(flags) == {6}
    assert flags[6].typical == Decimal("20.00")
    assert flags[6].z >= THRESHOLD
    assert flags[6].z.as_tuple().exponent == -2


def test_outlier_is_left_out_of_its_own_yardstick() -> None:
    # With the 240 included in the mean and spread, its z-score would be about 2.0 and missed.
    rows = _rows("dining", "20.00", "22.00", "18.00", "21.00", "19.00", "240.00")
    amounts = [float(amount) for _, _, amount in rows]
    assert (240 - statistics.mean(amounts)) / statistics.stdev(amounts) < 3
    assert 6 in flag_unusual(rows)


def test_categories_are_compared_separately() -> None:
    rows = _rows("housing", "1450.00", "1450.00", "1450.00", "1450.00", "1450.00", "1450.00")
    rows += _rows("dining", "20.00", "22.00", "18.00", "21.00", "19.00", "23.00", start=10)
    # A 1450 rent is normal for housing and no dining expense is far off, so nothing is flagged.
    assert flag_unusual(rows) == {}


def test_needs_five_other_expenses_in_the_category() -> None:
    assert flag_unusual(_rows("dining", "20.00", "22.00", "18.00", "21.00", "240.00")) == {}  # 4 others
    assert set(flag_unusual(_rows("dining", "20.00", "22.00", "18.00", "21.00", "19.00", "240.00"))) == {6}


def test_identical_others_give_no_flag() -> None:
    # Rent was always 1450.00, then rose: the others' spread is 0, so there is no z-score and no flag.
    rows = _rows("housing", "1450.00", "1450.00", "1450.00", "1450.00", "1450.00", "1600.00")
    assert flag_unusual(rows) == {}


def test_unusually_low_is_not_flagged() -> None:
    rows = _rows("dining", "20.00", "22.00", "18.00", "21.00", "19.00", "0.50")
    assert flag_unusual(rows) == {}


def test_threshold_is_inclusive_and_adjustable() -> None:
    rows = _rows("dining", "10", "12", "14", "16", "18", "20.33")
    z = z_score(Decimal("20.33"), d("10", "12", "14", "16", "18"))
    assert z is not None and Decimal("1.5") < z < THRESHOLD
    assert flag_unusual(rows) == {}
    assert set(flag_unusual(rows, threshold=Decimal("1.5"))) == {6}
    assert set(flag_unusual(rows, threshold=z)) == {6}


def test_matches_z_score_for_every_expense() -> None:
    rows = _rows("groceries", "35.10", "88.00", "140.00", "52.25", "61.60", "385.40", "73.15", "99.99")
    flags = flag_unusual(rows, threshold=Decimal(-100))
    for key, _, amount in rows:
        others = [other for other_key, _, other in rows if other_key != key]
        expected = z_score(amount, others)
        assert expected is not None
        assert flags[key].z == expected.quantize(Decimal("0.01"))


def test_empty_input() -> None:
    assert flag_unusual([]) == {}


def test_returns_anomaly_records() -> None:
    flags = flag_unusual(_rows("x", "1", "1", "1", "1", "2", "50"))
    assert all(isinstance(flag, Anomaly) for flag in flags.values())
