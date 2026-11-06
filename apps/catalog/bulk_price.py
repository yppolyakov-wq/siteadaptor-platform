"""KA-12 WR-6 + AIS A-4d: одна формула массовой правки цены.

«= X €» (set), «± X %» (pct), «± X €» (eur) — с теми же пределами и округлением на экране
«Sortiment» (мультивыбор) и в помощнике («alle Kuchen 10 % teurer»): два места с разной
математикой дали бы разную цену за одно и то же действие.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

MODES = ("set", "pct", "eur")
PCT_MIN, PCT_MAX = Decimal("-90"), Decimal("500")
AMOUNT_MAX = Decimal("100000")
CENT = Decimal("0.01")


def valid(mode: str, amount: Decimal | None) -> bool:
    """Режим известен, сумма конечна и в пределах (процент −90…500, сумма ≤ 100 000)."""
    if mode not in MODES or amount is None or not amount.is_finite():
        return False
    if abs(amount) > AMOUNT_MAX:
        return False
    if mode == "set" and amount < 0:
        return False
    return not (mode == "pct" and not PCT_MIN <= amount <= PCT_MAX)


def new_price(base, mode: str, amount: Decimal) -> Decimal:
    """Новая цена: не ниже нуля, до цента (половина — вверх)."""
    base = Decimal(str(base))
    if mode == "set":
        new = amount
    elif mode == "pct":
        new = base * (Decimal(100) + amount) / Decimal(100)
    else:
        new = base + amount
    return max(new, Decimal("0")).quantize(CENT, rounding=ROUND_HALF_UP)
