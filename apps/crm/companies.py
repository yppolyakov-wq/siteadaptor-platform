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


def _same_mail_domain(customer, company) -> bool:
    """Ревью безопасности CO-2: USt-IdNr публичен — сам по себе он не доказывает, что
    бронирует сотрудник фирмы (иначе посетитель получил бы в счёт адрес из справочника
    владельца). Нужна ещё почта на домене фирмы из справочника."""
    mail = (getattr(customer, "email", "") or "").lower()
    known = (getattr(company, "email", "") or "").lower()
    if "@" not in mail or "@" not in known:
        return False
    return mail.rsplit("@", 1)[1] == known.rsplit("@", 1)[1]


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
            # Нормализация в БД (без полного скана справочника в Python).
            from django.db.models import Value
            from django.db.models.functions import Replace, Upper

            norm = Upper("vat_id")
            for ch in (" ", ".", "-", "/"):
                norm = Replace(norm, Value(ch), Value(""))
            matches = list(
                Company.objects.annotate(vat_key=norm)
                .filter(vat_key=key)
                .only("pk", "vat_id", "email")[:2]
            )
            if len(matches) != 1 or not _same_mail_domain(customer, matches[0]):
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
