"""CO-2c: привязка покупателя-фирмы к справочнику компаний (решение владельца В-3).

Только по ТОЧНОМУ совпадению USt-IdNr (после нормализации) и только если клиент ещё
ни к кому не привязан. Новых компаний с витрины не создаём — справочник не засоряется
свободным текстом; добавить фирму можно кнопкой на карточке сделки.
"""

import logging
import re

logger = logging.getLogger(__name__)
_NOISE = re.compile(r"[\s.\-/]")


def normalize_vat(value: str) -> str:
    return _NOISE.sub("", (value or "").upper())


def link_by_vat(customer, vat_id: str):
    """→ привязанная компания или None. Сбой не роняет бронирование."""
    from django.db import transaction

    from .models import Company

    key = normalize_vat(vat_id)
    if customer is None or not key or getattr(customer, "company_id", None):
        return None
    try:
        with transaction.atomic():
            # vat_id в справочнике — свободный ввод владельца: сверяем нормализованно.
            matches = [
                c
                for c in Company.objects.exclude(vat_id="").only("pk", "vat_id")
                if normalize_vat(c.vat_id) == key
            ]
            if len(matches) != 1:
                return None
            customer.company_id = matches[0].pk
            customer.save(update_fields=["company"])
            return matches[0]
    except Exception:  # noqa: BLE001 — привязка вторична, бронь важнее
        logger.warning("crm: link_by_vat failed", exc_info=True)
        return None


def link_deal(deal) -> None:
    if getattr(deal, "customer_type", "") == "company":
        link_by_vat(getattr(deal, "customer", None), getattr(deal, "billing_vat_id", ""))
