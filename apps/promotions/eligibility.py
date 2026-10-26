"""KA-12 PR-5: «nur für Neukunden» / «einmal pro Kunde» — проверка в `create_order`.

Правило — в `Promotion.metadata["customer_rule"]` ("" / "new" / "once"), без миграции.
Клиент узнаётся так же, как заказ его заводит (e-mail без учёта регистра, иначе телефон).
Неизвестный адрес = новый клиент: обойти правило новым адресом можно — это осознанно
(как у «1 купон на человека»), правило — маркетинговое, не защита денег."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from .services import OutOfStock

NEW = "new"
ONCE = "once"
CHOICES = [
    ("", _("Für alle")),
    (NEW, _("Nur für Neukunden (erste Bestellung)")),
    (ONCE, _("Einmal pro Kunde")),
]
RULES = {NEW, ONCE}


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
    if phone and phone.strip():
        return Customer.objects.filter(phone=phone.strip()).order_by("created_at").first()
    return None


def check(promos, *, email: str = "", phone: str = "") -> None:
    """Бросает PromoNotEligible для первой акции, правило которой клиент нарушает."""
    from apps.orders.models import Order, OrderItem

    ruled = [(p, rule_of(p)) for p in promos if rule_of(p)]
    if not ruled:
        return
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
