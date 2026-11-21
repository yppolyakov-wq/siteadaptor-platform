"""FB-33 C5: вкладка «Felder» у строки формы корзины (`cart/form`) в окне блока.

Поля оформления (`form_fields.checkout`) правятся тем же движком, что форма заявки
(`form_spec.panel/parse_post/merge/put`, черновик `draft["form"]` на хосте `cart`). Этот модуль
даёт только то, что у корзины своё: подсказки над полями по обстоятельствам бизнеса —
онлайн-оплата (e-mail приходит из оплаты) и заказ к столику (контакты не спрашиваются).
Правила самих режимов (что витрина делает с e-mail при Stripe и у столика) — в `form_spec`
(`_checkout_mode`); здесь только тексты для владельца, вкладка от них не меняется.
"""

from __future__ import annotations

from django.utils.translation import gettext

FORM = "checkout"
HOST = "cart"


def stripe_available(tenant) -> bool:
    """Корзина предлагает онлайн-оплату — тот же расчёт способов, что у `/warenkorb/`."""
    from apps.core import payment_methods as pm
    from apps.orders import payments as order_payments
    from apps.orders.models import Order

    try:
        methods = order_payments.available_methods(tenant, customer_type=pm.COMPANY)
    except Exception:  # noqa: BLE001 — подсказка окна не должна ронять кабинет
        return False
    return Order.METHOD_STRIPE in methods


def table_ordering(tenant) -> bool:
    """Заказ к столику (QR «?tisch=») — тот же признак, что у «Tisch-QR» в кабинете:
    заведение со столами и включённые заказы."""
    from apps.core.directions import TABLE_TYPES

    if (getattr(tenant, "business_type", "") or "") not in TABLE_TYPES:
        return False
    try:
        return bool(tenant.is_module_active("orders"))
    except Exception:  # noqa: BLE001
        return False


def hints(tenant) -> list[str]:
    """Подсказки вкладки «Felder» корзины (пусто — подсказок нет)."""
    out = []
    if stripe_available(tenant):
        out.append(
            gettext(
                "Die Bestätigung kommt an die E-Mail aus der Zahlung, wenn hier keine "
                "angegeben ist."
            )
        )
    if table_ordering(tenant):
        out.append(gettext("Am Tisch fragen wir nur die Notiz und Ihre eigenen Fragen."))
    return out


def decorate(selected, tenant) -> None:
    """Подсказки — в модель вкладки (`selected["form_spec"]["hints"]`), только у корзины."""
    fs = (selected or {}).get("form_spec")
    if not isinstance(fs, dict) or fs.get("form") != FORM:
        return
    found = hints(tenant)
    if found:
        fs["hints"] = found
