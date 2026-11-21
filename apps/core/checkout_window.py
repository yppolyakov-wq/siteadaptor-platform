"""FB-33 C5: вкладка «Felder» у строки формы корзины (`cart/form`) в окне блока.

Поля оформления (`form_fields.checkout`) правятся тем же движком, что форма заявки
(`form_spec.panel/parse_post/merge/put`, черновик `draft["form"]` на хосте `cart`). Этот модуль
даёт только то, что у корзины своё: подсказки над полями по обстоятельствам бизнеса —
онлайн-оплата (e-mail приходит из оплаты) и заказ к столику (контакты не спрашиваются).
Правила самих режимов (что витрина делает с e-mail при Stripe и у столика) — в `form_spec`
(`_checkout_mode`); здесь только тексты для владельца, вкладка от них не меняется.
"""

from __future__ import annotations

import logging

from django.utils.translation import gettext

logger = logging.getLogger(__name__)

FORM = "checkout"
HOST = "cart"
#: id подсказки под полем e-mail (одна вкладка «Felder» в окне — id уникален)
EMAIL_HINT_ID = "ff-email-pay-hint"


def stripe_available(tenant) -> bool:
    """Корзина предлагает онлайн-оплату — тот же расчёт способов, что у `/warenkorb/`."""
    from apps.core import payment_methods as pm
    from apps.orders import payments as order_payments
    from apps.orders.models import Order

    try:
        methods = order_payments.available_methods(tenant, customer_type=pm.COMPANY)
    except Exception:  # noqa: BLE001 — подсказка окна не должна ронять кабинет
        logger.warning(
            "checkout window: payment methods unavailable (%s)",
            getattr(tenant, "schema_name", ""),
            exc_info=True,
        )
        return False
    return Order.METHOD_STRIPE in methods


def table_ordering(tenant) -> bool:
    """Заказ к столику: витрина берёт стол из `?tisch=` (сессия, `core/context.py`) у ЛЮБОГО
    бизнеса с заказами — поэтому признак один: включён модуль `orders`."""
    try:
        return bool(tenant.is_module_active("orders"))
    except Exception:  # noqa: BLE001
        return False


def hints(tenant) -> list[tuple[str, str]]:
    """Подсказки вкладки «Felder» корзины: [(ключ, текст)]. `email` — под полем e-mail,
    `table` — общая над полями."""
    out = []
    if stripe_available(tenant):
        out.append(
            (
                "email",
                gettext(
                    "Die Bestätigung kommt an die E-Mail aus der Zahlung, wenn hier keine "
                    "angegeben ist."
                ),
            )
        )
    if table_ordering(tenant):
        out.append(
            (
                "table",
                gettext(
                    "Bei Bestellung am Tisch (QR-Code) fragen wir nur die Notiz und Ihre "
                    "eigenen Fragen."
                ),
            )
        )
    return out


def decorate(selected, tenant) -> None:
    """Подсказки — в модель вкладки, только у корзины: общие — `hints`, у поля e-mail —
    `hint`/`hint_id` его строки (`aria-describedby` в `_bw_formfields.html`)."""
    fs = (selected or {}).get("form_spec")
    if not isinstance(fs, dict) or fs.get("form") != FORM:
        return
    general = []
    for key, text in hints(tenant):
        row = next((f for f in fs.get("fields") or () if f.get("key") == key), None)
        if row is not None:
            row["hint"], row["hint_id"] = text, EMAIL_HINT_ID
        else:
            general.append(text)
    if general:
        fs["hints"] = general
