"""SHP-5: приписка к цене о стоимости доставки (PAngV) — по списку способов бизнеса."""

import logging

from django import template

register = template.Library()
log = logging.getLogger(__name__)


def _costs_something(method) -> bool:
    """Доставка этим способом может стоить денег (не «всегда бесплатно»)."""
    if method.fee_cents or method.pricing == "weight":
        return True
    return any(isinstance(z, dict) and z.get("fee_cents") for z in method.zones or [])


@register.simple_tag(takes_context=True)
def shipping_note(context):
    """Нужна ли приписка «zzgl. Versandkosten» со ссылкой на «/versand/».

    Только самовывоз или доставка везде бесплатна — приписки нет. Есть курьер или
    Paketdienst с ценой — «zzgl. Versandkosten» со ссылкой на страницу сумм (§ 6 PAngV:
    стоимость доставки рядом с ценой). Без онлайн-заказов страницы нет — и ссылки.
    Результат — на запросе (тег стоит и в подвале, и у цены). Сбой — без приписки."""
    request = context.get("request")
    tenant = getattr(request, "tenant", None) if request is not None else None
    if tenant is None:
        return False
    cached = getattr(request, "_shipping_note", None)
    if cached is not None:
        return cached
    try:
        from apps.core.storefront_state import orders_active
        from apps.orders import shipping

        value = orders_active(tenant) and any(
            m.kind != "pickup" and _costs_something(m) for m in shipping.methods(tenant)
        )
    except Exception:  # noqa: BLE001 — витрина не падает из-за приписки
        log.exception("shipping_note failed")
        value = False
    try:
        request._shipping_note = value
    except AttributeError:
        pass
    return value
