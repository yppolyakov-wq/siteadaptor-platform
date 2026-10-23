"""KA-H7: сумма и ставка выручки записи для журнала (`finance.RevenueEntry`).

Две ошибки прежних хуков, найденные аудитом KA-5c:

- визит по карте (Mehrfachkarte) писал в журнал полную цену услуги, хотя деньги
  за неё уже проведены при продаже карты (`source="pass"`) — выручка удваивалась;
- ставка была жёстко 19 %: снимок `Booking.vat_rate` (DC-8) и Kleinunternehmer
  (§ 19 UStG) игнорировались.

Один помощник для встроенного хука FSM и для своих статусов (status_effects),
чтобы оба пути писали одно и то же. Смешанные ставки (услуга 7 %, Extras 19 %)
v1 пишут одной записью по ставке базовой позиции: разбивка `RevenueEntry` по
ставкам отложена с волны VAT (нужна защита от двойного учёта).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import connection

ZERO = Decimal("0")


def _tenant(tenant):
    """Настоящий тенант: в фоновых задачах (`schema_context`) у соединения FakeTenant
    без полей — § 19 потерялся бы, поэтому дочитываем запись по схеме."""
    if tenant is not None:
        return tenant
    current = getattr(connection, "tenant", None)
    if current is None or hasattr(current, "small_business"):
        return current
    from django_tenants.utils import get_tenant_model

    schema = getattr(current, "schema_name", "")
    return get_tenant_model().objects.filter(schema_name=schema).first() if schema else None


def revenue_for(booking, tenant=None) -> tuple[Decimal, Decimal]:
    """(сумма €, ставка %) выручки записи. Сумма 0 — писать нечего."""
    from apps.core.vat import _extras_components

    snapshot = getattr(booking, "vat_rate", None)
    rate = Decimal("19.00") if snapshot is None else Decimal(str(snapshot))
    if getattr(booking, "card_id", None):
        # Услуга оплачена картой: в журнал идут только Extras (скидка — из них;
        # Gutschein на визит по карте — редкость, v1 не делит его на услугу/Extras).
        # Ставка смешанных Extras — ставка большей позиции (одна запись журнала).
        extras = _extras_components(booking, rate)
        cents = max(0, booking.extras_cents - int(booking.discount_cents or 0))
        amount = Decimal(cents) / 100
        if extras:
            rate = max(extras, key=lambda c: c[1])[2]
    else:
        amount = Decimal(booking.total_cents) / 100
    if getattr(_tenant(tenant), "small_business", False):
        rate = ZERO
    return amount, rate


def recorded_amount(booking) -> Decimal | None:
    """Сумма, уже проведённая по записи (для сторно), или None."""
    from apps.finance.models import RevenueEntry

    entry = RevenueEntry.objects.filter(source="booking", source_ref=str(booking.id)).first()
    return entry.amount if entry is not None else None
