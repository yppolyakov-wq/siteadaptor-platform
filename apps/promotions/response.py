"""T-8.2: отклик акции — что делает кнопка на её странице (план
docs/t8-2-zuruecklegen-plan-2026-10-10.md §1).

Одна точка истины для страницы акции, приёмников POST и формы владельца:
- ``booking`` — цель акции услуга/номер: штатная воронка записи/брони;
- ``buy`` — онлайн-заказ (только если модуль заказов включён и витрина не «Nur Aktionen»);
- ``reserve`` — «Zurücklegen»: старый движок резерва (срок, код+QR, сканер);
- ``inquire`` — «Anfragen»: окно заявки с темой акции (нужен модуль заявок);
- ``coupon`` — «Coupon holen»: личный код + QR, гасится на кассе сканером (T-8.3);
- ``show`` — без кнопки, только «So finden Sie uns».

Явный выбор владельца живёт в ``Promotion.metadata["response"]``; невыполнимый выбор
падает на автоматику, а не роняет страницу.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

BOOKING = "booking"
BUY = "buy"
RESERVE = "reserve"
INQUIRE = "inquire"
SHOW = "show"
COUPON = "coupon"

# Выбор в форме владельца ("" = автоматически).
CHOICES = [
    ("", _("Automatisch")),
    (RESERVE, _("Zurücklegen lassen")),
    (COUPON, _("Coupon holen")),
    (INQUIRE, _("Anfragen")),
    (SHOW, _("Nur zeigen")),
    (BUY, _("Online kaufen")),
]
CHOICE_KEYS = {key for key, _label in CHOICES}


def can_buy(tenant) -> bool:
    """Онлайн-заказ возможен: модуль заказов включён и витрина не «Nur Aktionen»."""
    if tenant is None:
        return True
    from apps.core import storefront_profile

    try:
        orders_on = tenant.is_module_active("orders")
    except Exception:  # noqa: BLE001 — стаб тенанта без модулей
        return True
    return orders_on and not storefront_profile.is_aktionen(tenant)


def can_inquire(tenant) -> bool:
    if tenant is None:
        return False
    try:
        return bool(tenant.is_module_active("jobs"))
    except Exception:  # noqa: BLE001
        return False


def chosen(promo) -> str:
    meta = promo.metadata if isinstance(getattr(promo, "metadata", None), dict) else {}
    value = meta.get("response") or ""
    return value if value in CHOICE_KEYS else ""


def response_for(promo, tenant) -> str:
    """Отклик акции для этого тенанта (см. модульный docstring)."""
    if getattr(promo, "target_kind", "") in ("service", "stay"):
        return BOOKING
    if tenant is None:
        # Нет тенанта в запросе (рендер без витрины) — прежнее поведение.
        return BUY
    wanted = chosen(promo)
    if wanted == SHOW:
        return SHOW
    if wanted == RESERVE:
        return RESERVE
    if wanted == COUPON:
        return COUPON
    if wanted == INQUIRE and can_inquire(tenant):
        return INQUIRE
    if wanted == BUY and can_buy(tenant):
        return BUY
    return BUY if can_buy(tenant) else RESERVE
