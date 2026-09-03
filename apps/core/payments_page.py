"""R7-3: «Zahlungen» — отдельная поверхность оплат (фидбэк владельца 2026-08-24
«так же с оплатой, чтоб можно было посмотреть оплаты отдельно»).

Раньше состояние оплаты было СТОЛБЦОМ в списках сделок и «Offene Posten» в
Finanzen (модуль по умолчанию выключен) — отдельного взгляда «кто заплатил,
кто должен, чем платили» не было. Здесь — тонкий слой ЧТЕНИЯ поверх тех же
сделок: свои таблицы не заводим, статусы меняются штатным путём
(`transactions.apply_action` / `orders:order-action`), деньги считаются
контрактом Transaction (`amount_value`).
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core import payment_methods, status_registry, transactions

# Состояния оплаты per-kind: что считаем «оплачено» и «ждёт денег».
# Зеркалит finance.bank._OPEN_PAYMENT_STATES (ERP-2): у броней `none` — оплата
# на месте, это НЕ долг; у билета `deposit` — частичная предоплата.
PAID_STATES = {
    "order": ("paid",),
    "booking": ("paid",),
    "stay": ("paid",),
    "ticket": ("paid",),
}
OPEN_STATES = {
    "order": ("unpaid",),
    "booking": ("pending",),
    "stay": ("pending",),
    "ticket": ("pending", "deposit"),
}
REFUNDED_STATES = {k: ("refunded",) for k in PAID_STATES}

FILTERS = (
    ("open", _("Offen")),
    ("paid", _("Bezahlt")),
    ("refunded", _("Erstattet")),
    ("", _("Alle")),
)

_STATES_BY_FILTER = {"open": OPEN_STATES, "paid": PAID_STATES, "refunded": REFUNDED_STATES}


def _kinds(tenant) -> list[str]:
    """Направления с деньгами, доступные тенанту (по активным модулям)."""
    return [k for k in PAID_STATES if tenant.is_module_active(transactions.KIND_MODULE[k])]


def payment_rows(tenant, state: str = "open", method: str = "", limit: int = 200) -> list[dict]:
    """Строки оплат: сделка + состояние + способ + сумма.

    `state` — ключ FILTERS ("" = все); `method` — код способа оплаты
    (`Order.payment_method`), пусто = любой. Отменённые сделки не показываем:
    их деньги закрыты FSM (тот же приём, что в finance.bank.open_items).
    """
    rows: list[dict] = []
    states_map = _STATES_BY_FILTER.get(state)
    for kind in _kinds(tenant):
        model = transactions.model_for(kind)
        qs = model.objects.exclude(status__in=status_registry.cancelled_statuses_for(kind, tenant))
        if states_map is not None:
            qs = qs.filter(payment_state__in=states_map[kind])
        # SH-23d: способ оплаты теперь есть у ВСЕХ видов сделок (SH-23c), поэтому
        # фильтр больше не отбрасывает бронь/номер/билет/заявку молча.
        if method:
            qs = qs.filter(payment_method=method)
        for obj in qs.order_by("-created_at")[:limit]:
            tx = transactions.transaction_for(kind, obj)
            rows.append(
                {
                    "kind": kind,
                    "kind_label": transactions.KIND_LABEL.get(kind, kind),
                    "pk": obj.pk,
                    "code": tx.reference_code,
                    "title": tx.title,
                    "customer": tx.customer,
                    "amount_display": tx.subtotal_display,
                    "amount_value": tx.amount_value,
                    "payment_state": getattr(obj, "payment_state", ""),
                    "payment_method": getattr(obj, "payment_method", ""),
                    "payment_method_label": (
                        payment_methods.label(obj.payment_method)
                        if getattr(obj, "payment_method", "")
                        else ""
                    ),
                    # SH-23d: срок оплаты (Р-2/Р-4) — просроченное видно на месте.
                    "payment_due_at": getattr(obj, "payment_due_at", None),
                    "created_at": obj.created_at,
                    "manage_url": tx.manage_url,
                }
            )
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows[:limit]


def payment_summary(tenant) -> dict:
    """Плашка сверху: сколько ждёт денег и сколько получено за 30 дней.

    Считаем по тем же строкам (без отдельных агрегатов): у booking/ticket итог
    вычисляется в Python (снимки допов), поэтому SQL-Sum врал бы — урок VS-2c.
    """
    open_rows = payment_rows(tenant, "open", limit=500)
    paid_rows = payment_rows(tenant, "paid", limit=500)
    since = timezone.now() - timedelta(days=30)
    paid_recent = [r for r in paid_rows if r["created_at"] >= since]
    return {
        "open_count": len(open_rows),
        "open_total": sum((r["amount_value"] or 0) for r in open_rows),
        "paid_count": len(paid_recent),
        "paid_total": sum((r["amount_value"] or 0) for r in paid_recent),
        "currency": "EUR",
    }
