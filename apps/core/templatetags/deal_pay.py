"""KA-12 B2-5 (E1.11): «Restbetrag online bezahlen» на подтверждении брони/записи/билета."""

from decimal import Decimal

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def rest_pay(context, kind, obj):
    """{url, eur} — можно доплатить остаток онлайн; иначе None (гейты balance_pay)."""
    from apps.core import balance_pay

    request = context.get("request")
    tenant = getattr(request, "tenant", None)
    if request is not None and request.GET.get("paid"):
        # Возврат из Stripe: вебхук мог ещё не прийти — повторная кнопка вела бы
        # к двойной оплате.
        return None
    try:
        if not balance_pay.rest_payable(kind, obj, tenant):
            return None
        return {
            "url": balance_pay.pay_path(kind, obj),
            "eur": Decimal(balance_pay.rest_cents(kind, obj)) / 100,
        }
    except Exception:  # noqa: BLE001 — кнопка не должна ронять подтверждение
        return None
