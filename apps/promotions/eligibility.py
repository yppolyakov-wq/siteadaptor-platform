"""KA-12 PR-5: «nur für Neukunden» / «einmal pro Kunde» — проверка в `create_order`.

Правило — в `Promotion.metadata["customer_rule"]` ("" / "new" / "once"), без миграции.
Клиент узнаётся так же, как заказ его заводит (e-mail без учёта регистра, иначе телефон).
Неизвестный адрес = новый клиент: обойти правило новым адресом можно — это осознанно
(как у «1 купон на человека»), правило — маркетинговое, не защита денег."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop

from .services import OutOfStock

NEW = "new"
ONCE = "once"
CHOICES = [
    ("", _("Für alle")),
    (NEW, _("Nur für Neukunden (erste Bestellung)")),
    (ONCE, _("Einmal pro Kunde")),
]
RULES = {NEW, ONCE}
# Ревью PR-5: одна нейтральная фраза — по разному тексту «nur Neukunden» / «nur einmal»
# можно было бы проверить, есть ли у адреса заказы. Правило акции видно на её странице.
NOT_ELIGIBLE_MSG = gettext_noop(
    "Der Aktionspreis gilt für diese Bestellung nicht (siehe Bedingungen der Aktion)."
)


class PromoNotEligible(OutOfStock):
    """Клиент не подходит под правило акции. Подкласс промо-OutOfStock — все чекауты,
    которые уже ловят исчерпанный лимит, ловят и это без 500."""

    def __init__(self, promo, rule):
        super().__init__()
        self.promo = promo
        self.rule = rule


def rule_of(promo) -> str:
    meta = promo.metadata if isinstance(getattr(promo, "metadata", None), dict) else {}
    value = meta.get("customer_rule") or ""
    return value if value in RULES else ""


def _customer(email: str, phone: str):
    from .models import Customer

    if email:
        found = Customer.objects.filter(email__iexact=email.strip()).order_by("created_at").first()
        if found is not None:
            return found
    digits = _digits(phone)
    if digits:
        # Телефон в заказе хранится как ввели («0171 123» / «+49171123»): сравниваем
        # цифры. Кандидатов немного (по хвосту номера), сравнение — в Python.
        tail = digits[-6:]
        for cand in Customer.objects.filter(phone__contains=tail[-4:]).order_by("created_at"):
            if _digits(cand.phone).endswith(tail) and _same_number(cand.phone, phone):
                return cand
    return None


def _digits(value) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _same_number(a, b) -> bool:
    """«0171…» ≡ «+49171…» ≡ «0049171…» (DE): сравниваем номер без префикса страны/нуля."""

    def core(v):
        d = _digits(v)
        for prefix in ("0049", "49"):
            if str(v or "").strip().startswith(("+", "00")) and d.startswith(prefix):
                return d[len(prefix) :]
        return d.lstrip("0")

    return core(a) == core(b) and bool(core(a))


def check(promos, *, email: str = "", phone: str = "") -> None:
    """Бросает PromoNotEligible для первой акции, правило которой клиент нарушает."""
    from apps.orders.models import Order, OrderItem

    ruled = [(p, rule_of(p)) for p in promos if rule_of(p)]
    if not ruled:
        return
    # Ревью PR-5: два параллельных заказа с одного адреса оба прошли бы чтение —
    # транзакционная advisory-блокировка на (акция, клиент) до конца заказа.
    key = (email or "").strip().lower() or _digits(phone)
    if key:
        from django.db import connection

        with connection.cursor() as cur:
            for promo, _rule in sorted(ruled, key=lambda pr: str(pr[0].pk)):
                cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))", [f"promo-rule:{promo.pk}:{key}"]
                )
    customer = _customer(email or "", phone or "")
    if customer is None:
        return  # новый клиент — подходит под оба правила
    live = Order.objects.filter(customer=customer).exclude(
        status__in=(Order.STATUS_CANCELLED, Order.STATUS_RETURNED)
    )
    for promo, rule in ruled:
        if rule == NEW and live.exists():
            raise PromoNotEligible(promo, rule)
        if (
            rule == ONCE
            and OrderItem.objects.filter(order__in=live, promotion_id=promo.pk).exists()
        ):
            raise PromoNotEligible(promo, rule)
