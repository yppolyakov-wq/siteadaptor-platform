"""Stripe Connect: оплата конечного клиента бизнесу напрямую (P2.5).

Деньги идут «клиент → бизнес» через connected account бизнеса (в отличие от
подписки «бизнес → платформа», см. services.py). Платформа может удержать
application fee — процент задаётся ПО ТИПУ БИЗНЕСА (решение владельца 2026-06-12:
по умолчанию 0 для всех, но настройка существует и включается позже).

Этот модуль — конфиг комиссии (без внешних вызовов Stripe). Онбординг
connected-аккаунтов и сами платежи — следующие подзадачи P2.5a/b/c. Вариант
«платформа собирает + payout» (option 3) — резерв под маркетплейс, здесь не
реализуется.
"""

from decimal import ROUND_DOWN, Decimal

from django.conf import settings

# Дефолтная комиссия по типу бизнеса — пусто = 0 % для всех. Оверрайд через
# settings.BILLING_APPLICATION_FEE_PERCENT (env), ключ "" — дефолт для всех типов.
_DEFAULT_FEE_PERCENT: dict[str, str] = {}


def _fee_table() -> dict[str, str]:
    return {**_DEFAULT_FEE_PERCENT, **getattr(settings, "BILLING_APPLICATION_FEE_PERCENT", {})}


def application_fee_percent(business_type: str) -> Decimal:
    """Процент application fee для типа бизнеса (Decimal ≥ 0, по умолчанию 0).

    Приоритет: точный тип → ключ "" (общий дефолт) → 0.
    """
    table = _fee_table()
    raw = table.get(business_type)
    if raw is None:
        raw = table.get("", 0)
    pct = Decimal(str(raw or 0))
    return pct if pct > 0 else Decimal(0)


def application_fee_cents(amount_cents: int, business_type: str) -> int:
    """application fee в центах от суммы платежа (округление вниз).

    0 при нулевом проценте — тогда Checkout создаётся вообще без application_fee
    (платформа ничего не удерживает, бизнес получает всё).
    """
    pct = application_fee_percent(business_type)
    if pct <= 0 or amount_cents <= 0:
        return 0
    fee = (Decimal(amount_cents) * pct / Decimal(100)).to_integral_value(rounding=ROUND_DOWN)
    return int(fee)
