from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import TypeVar

MIN_POINTS = 5  # minimum number of existing expenses for a z-score
THRESHOLD = Decimal(3)  # minimum number of (sample) standard deviations above the others' mean
CENT = Decimal("0.01")
_PRECISION = 50  # room for sums of squares of large amounts without rounding

K = TypeVar("K", bound=Hashable)


@dataclass(frozen=True)
class Anomaly:
    z: Decimal  # standard deviation
    typical: Decimal  # mean (rounded to the cent)


def z_score(value: Decimal, others: Sequence[Decimal]) -> Decimal | None:
    with localcontext() as context:
        context.prec = _PRECISION
        total = sum(others, Decimal(0))
        squares = sum((amount * amount for amount in others), Decimal(0))
        return _z(value, len(others), total, squares)


def flag_unusual(expenses: Iterable[tuple[K, str, Decimal]], threshold: Decimal = THRESHOLD) -> dict[K, Anomaly]:
    by_category: dict[str, list[tuple[K, Decimal]]] = {}
    for key, category, amount in expenses:
        by_category.setdefault(category, []).append((key, amount))

    flagged: dict[K, Anomaly] = {}
    with localcontext() as context:
        context.prec = _PRECISION
        for items in by_category.values():
            count = len(items)
            total = sum((amount for _, amount in items), Decimal(0))
            squares = sum((amount * amount for _, amount in items), Decimal(0))
            for key, amount in items:
                others_total = total - amount
                z = _z(amount, count - 1, others_total, squares - amount * amount)
                if z is not None and z >= threshold:
                    typical = (others_total / (count - 1)).quantize(CENT, rounding=ROUND_HALF_UP)
                    flagged[key] = Anomaly(z=z.quantize(CENT, rounding=ROUND_HALF_UP), typical=typical)
    return flagged


def _z(value: Decimal, count: int, total: Decimal, squares: Decimal) -> Decimal | None:
    if count < MIN_POINTS:
        return None
    spread = count * squares - total * total
    if spread <= 0:
        return None
    variance = spread / (count * (count - 1))
    mean = total / count
    return (value - mean) / variance.sqrt()
