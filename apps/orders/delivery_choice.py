"""SH-24 (фидбэк владельца 2026-09-03 «нужна опция доставки: самовывоз или
доставка»): выбор способа получения — ОДИН источник правды для всех продажных
поверхностей.

Раньше выбор жил только в форме корзины: покупка по акции (`/p/<uuid>/kaufen/`)
и принятие предложения (`/o/<token>/`) форсили самовывоз, поэтому у бизнеса с
доставкой часть заказов молча приезжала «на вынос». Здесь — та же проверка, что
на чекауте (адрес, зона по индексу, минимум заказа), но без `messages`/`redirect`:
вызывающая вьюха сама решает, как показать ошибку.

План — `docs/order-feedback-plan-2026-09-03.md` §7.
"""

from __future__ import annotations

from django.utils.translation import gettext as _

from .services import delivery_quote


class DeliveryChoice:
    """Результат разбора POST: способ получения, стоимость, адрес, ошибка."""

    __slots__ = ("delivery", "shipping_cents", "shipping_address", "error")

    def __init__(self, *, delivery=False, shipping_cents=0, shipping_address="", error=""):
        self.delivery = delivery
        self.shipping_cents = shipping_cents
        self.shipping_address = shipping_address
        self.error = error

    def __bool__(self) -> bool:  # «выбор пригоден» = ошибки нет
        return not self.error


def resolve(post, tenant, subtotal_cents: int) -> DeliveryChoice:
    """Разобрать выбор «Abholung | Lieferung» из POST.

    Доставка включается ТОЛЬКО при `tenant.delivery_enabled` — подмена поля
    формой у бизнеса без доставки остаётся самовывозом (fail-closed).
    """
    if (post.get("fulfillment") or "") != "delivery" or not getattr(
        tenant, "delivery_enabled", False
    ):
        return DeliveryChoice()
    street = (post.get("street") or "").strip()
    plz = (post.get("plz") or "").strip()
    city = (post.get("city") or "").strip()
    if not (street and plz and city):
        return DeliveryChoice(error=_("Please enter your full delivery address."))
    quote = delivery_quote(tenant, subtotal_cents, plz)
    if not quote["deliverable"]:
        return DeliveryChoice(
            error=_("Sorry, we don't deliver to postal code %(plz)s.") % {"plz": plz}
        )
    if quote["min_cents"] and subtotal_cents < quote["min_cents"]:
        return DeliveryChoice(
            error=_("Minimum order for delivery is %(min)s €.")
            % {"min": f"{quote['min_cents'] / 100:.2f}".replace(".", ",")}
        )
    return DeliveryChoice(
        delivery=True,
        shipping_cents=quote["fee_cents"],
        shipping_address=f"{street}\n{plz} {city}",
    )


def context(tenant) -> dict:
    """Данные для партиала `storefront/_fulfillment_choice.html`.

    Тот же набор ключей, что собирает корзина, — чтобы партиал одинаково
    рендерился на всех трёх поверхностях (корзина, покупка по акции, принятие
    предложения). Без доставки возвращает только флаг: партиал печатает
    «Abholung im Geschäft».
    """
    if not getattr(tenant, "delivery_enabled", False):
        return {"delivery_enabled": False}
    fee = getattr(tenant, "delivery_fee_cents", 0) or 0
    free = getattr(tenant, "delivery_free_cents", 0) or 0
    minimum = getattr(tenant, "delivery_min_cents", 0) or 0
    return {
        "delivery_enabled": True,
        "delivery_fee_cents": fee,
        "delivery_fee_eur": f"{fee / 100:.2f}",
        "delivery_free_cents": free,
        "delivery_free_eur": f"{free / 100:.2f}",
        "delivery_min_cents": minimum,
        "delivery_min_eur": f"{minimum / 100:.2f}",
    }
