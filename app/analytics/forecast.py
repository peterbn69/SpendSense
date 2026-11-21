from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

WINDOW = 3
CENT = Decimal("0.01")


def forecast(history: Sequence[Decimal]) -> Decimal | None:
    if len(history) < WINDOW:
        return None
    recent = history[-WINDOW:]
    return (sum(recent, Decimal("0")) / WINDOW).quantize(CENT, rounding=ROUND_HALF_UP)
