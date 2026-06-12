"""Платное продвижение листинга в агрегаторе (P2.4b): разовый Stripe-платёж.

Featured-листинг (P2.4a) поднимается наверх выдачи порталов/агрегатора с бейджем
«★ Empfohlen». Здесь — самообслуживание: владелец акции из кабинета покупает
продвижение на N дней разовым Checkout-платежом (mode="payment"). Срок ставит
вебхук на public-схеме (apps.billing.webhooks → services.apply_featured_purchase),
поле то же — AggregatorListing.featured_until (миграций не нужно).

Без заведения Price в Stripe-дашборде: суммы передаём inline price_data
(минимум настройки). Цены — в коде с дефолтами; оверрайд через .env
(BILLING_FEATURED_PRICES="7=900,14=1500,30=2500").
"""

from dataclasses import dataclass

from django.conf import settings

# Дефолтные планы (дни → центы), решение владельца 2026-06-12: 9 / 15 / 25 €.
_DEFAULT_PRICES: dict[int, int] = {7: 900, 14: 1500, 30: 2500}


@dataclass(frozen=True)
class FeaturedPlan:
    days: int
    amount_cents: int

    @property
    def amount_eur(self) -> str:
        """Сумма для UI: «9 €» / «9,50 €» (немецкая запятая, без лишних нулей)."""
        if self.amount_cents % 100 == 0:
            return f"{self.amount_cents // 100} €"
        return f"{self.amount_cents / 100:.2f}".replace(".", ",") + " €"

    @property
    def label(self) -> str:
        return f"{self.days} Tage"


def _prices() -> dict[int, int]:
    """Активная таблица цен: env-оверрайд (строки) либо дефолты."""
    raw = getattr(settings, "BILLING_FEATURED_PRICES", None) or {}
    if raw:
        return {int(days): int(cents) for days, cents in raw.items()}
    return dict(_DEFAULT_PRICES)


def get_plans() -> list[FeaturedPlan]:
    """Планы по возрастанию длительности (для страницы покупки)."""
    return [FeaturedPlan(days=d, amount_cents=c) for d, c in sorted(_prices().items())]


def get_plan(days: int) -> FeaturedPlan | None:
    """План по числу дней или None (защита от поддельного ?days=)."""
    cents = _prices().get(int(days))
    return FeaturedPlan(days=int(days), amount_cents=cents) if cents is not None else None


def _stripe_secret() -> str:
    return (
        settings.STRIPE_LIVE_SECRET_KEY
        if settings.STRIPE_LIVE_MODE
        else settings.STRIPE_TEST_SECRET_KEY
    )


def is_enabled() -> bool:
    """Готово ли к продаже: есть Stripe-ключ активного режима и хотя бы один план.

    Зеркало billing.views.price_configured для подписки — пока Stripe не настроен
    (нет ключа в .env), кнопку покупки в кабинете скрываем.
    """
    return bool(_stripe_secret()) and bool(get_plans())
