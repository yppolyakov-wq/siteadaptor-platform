"""SH-23 (фидбэк владельца 2026-09-03): «для каждого типа заказа всех архетипов
по желанию нужна оплата онлайн, при получении или на месте или выставить счёт
как юрлицо; видимо нужен выбор — юрлицо покупает или физлицо».

Реестр способов оплаты — ОДИН на все виды сделок. До этой волны способ знал
только заказ (`Order.payment_method`), а бронь/номер/билет/заявка имели лишь
«сколько списать Stripe». Здесь: коды способов, тип покупателя и правила
доступности (`available`), которые уважают и настройки бизнеса, и решения
владельца §9 плана `docs/order-feedback-plan-2026-09-03.md`.

Решения владельца, зашитые в правила:
* Р-3 «Rechnung» (Kauf auf Rechnung) — ТОЛЬКО фирмам; частному лицу остаются
  Vorkasse, оплата на месте и онлайн.
* Р-2 срок оплаты счёта по умолчанию 14 дней (`Tenant.invoice_terms_days`).
* Р-4 удержание места без оплаты: до срока счёта, 3 дня для Vorkasse
  (`Tenant.vorkasse_hold_days`), «на месте» — без удержания.
* Р-5 отель со 100 % предоплатой принимает и банковский перевод, не только карту.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

# Коды способов. Совпадают с `Order.PAYMENT_METHODS` (легаси-значения целы) плюс
# «invoice» — счёт юрлицу.
ON_SITE = "on_site"
STRIPE = "stripe"
VORKASSE = "vorkasse"
INVOICE = "invoice"

METHOD_LABELS = {
    ON_SITE: _("Barzahlung bei Abholung"),
    STRIPE: _("Online-Zahlung"),
    VORKASSE: _("Vorkasse (Überweisung)"),
    INVOICE: _("Kauf auf Rechnung"),
}
METHODS = tuple(METHOD_LABELS)

# Тип покупателя: частное лицо или фирма (Р-3 — от него зависит доступность счёта).
PRIVATE = "private"
COMPANY = "company"
CUSTOMER_TYPES = [
    (PRIVATE, _("Private")),
    (COMPANY, _("Company")),
]

# Виды сделок, у которых есть способ оплаты (kind контракта Transaction).
KINDS = ("order", "booking", "stay", "ticket", "job")


def label(code: str):
    """Человеческая подпись способа (неизвестный код → сам код)."""
    return METHOD_LABELS.get(code, code)


def _stripe_ready(tenant) -> bool:
    from apps.billing import connect

    return bool(
        getattr(tenant, "payments_enabled", False) and connect.is_connect_configured()
    ) and bool(getattr(tenant, "stripe_connect_id", ""))


def invoice_enabled(tenant) -> bool:
    """Счёт юрлицу включён у бизнеса (Р-1: счёт выпускается автоматически)."""
    return bool(getattr(tenant, "invoice_b2b_enabled", False))


def available(tenant, kind: str = "order", *, customer_type: str = PRIVATE) -> list[str]:
    """Способы оплаты для вида сделки и типа покупателя.

    Порядок = порядок пикера, первый — дефолт. Правила:
    * онлайн — при подключённом Stripe-Connect (у заказов дополнительно тумблер
      предоплаты, как в E7-2 — прежнее поведение чекаута корзины);
    * Vorkasse — при тумблере и заполненном IBAN;
    * счёт — только фирме и только при `invoice_b2b_enabled` (Р-3);
    * оплата на месте — всегда (последний, как раньше).
    """
    methods: list[str] = []
    if kind == "order":
        stripe_ok = _stripe_ready(tenant) and getattr(tenant, "orders_prepay", False)
    else:
        stripe_ok = _stripe_ready(tenant)
    if stripe_ok:
        methods.append(STRIPE)
    if getattr(tenant, "vorkasse_enabled", False) and getattr(tenant, "bank_iban", ""):
        methods.append(VORKASSE)
    if customer_type == COMPANY and invoice_enabled(tenant):
        methods.append(INVOICE)
    methods.append(ON_SITE)
    return methods


def normalize(code: str, tenant, kind: str = "order", *, customer_type: str = PRIVATE) -> str:
    """Выбранный способ или первый доступный (мусор/недоступное → дефолт).

    Тот же fail-safe, что был у чекаута корзины: подмена поля не даёт способа,
    которого бизнес не предлагает.
    """
    allowed = available(tenant, kind, customer_type=customer_type)
    code = (code or "").strip()
    return code if code in allowed else allowed[0]


def customer_type_of(raw: str) -> str:
    """Тип покупателя из POST; мусор → частное лицо (fail-closed для счёта)."""
    return COMPANY if (raw or "").strip() == COMPANY else PRIVATE


def hold_days(tenant, method: str) -> int:
    """Р-4: сколько держать место/номер/билет без оплаты.

    Счёт — до срока оплаты счёта (по умолчанию 14 дней), Vorkasse — 3 дня,
    оплата на месте и онлайн-оплата удержания не требуют (0 = не ограничиваем).
    """
    if method == INVOICE:
        return int(getattr(tenant, "invoice_terms_days", 0) or 14)
    if method == VORKASSE:
        return int(getattr(tenant, "vorkasse_hold_days", 0) or 3)
    return 0
