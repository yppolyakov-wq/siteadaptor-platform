"""KA-12 E6.6: сравнение контактов клиента.

Телефон вводят как угодно: «+49 171 1234567», «0171/1234567», «0049 171 …». Для
лимитов «на человека» это один клиент — сравниваем по ключу из цифр, храним как ввели.
Без библиотеки номеров: правило DACH-достаточное (``00``/``0`` → код страны 49).
"""

from __future__ import annotations

import hashlib
import re

_NON_DIGIT = re.compile(r"\D+")
DEFAULT_COUNTRY = "49"
_TAIL = 6  # хвост цифр для поиска кандидатов в БД


def phone_key(phone: str) -> str:
    digits = _NON_DIGIT.sub("", phone or "")
    if not digits:
        return ""
    if digits.startswith("00"):
        return digits[2:]
    if digits.startswith("0"):
        return DEFAULT_COUNTRY + digits[1:]
    return digits


def phone_candidates_regex(phone: str) -> str:
    """Регулярка для БД: последние цифры номера с любыми разделителями между ними."""
    # Хвост национальной части (без кода страны — у DACH он из двух цифр): у одной записи
    # «+49 171 …», у другой «0171 …». Точное сравнение — по ключу в Python.
    tail = phone_key(phone)[len(DEFAULT_COUNTRY) :][-_TAIL:]
    return r"\D*".join(tail) + r"\D*$" if tail else ""


def find_by_phone(queryset, phone: str, field: str = "phone"):
    """Строки queryset с тем же телефоном по ключу (самая ранняя первой) — список."""
    key = phone_key(phone)
    if not key:
        return []
    rows = queryset.filter(**{f"{field}__regex": phone_candidates_regex(phone)})
    return [row for row in rows if phone_key(getattr(row, field)) == key]


def contact_lock_key(prefix: str, email: str = "", phone: str = "") -> str:
    """Ключ advisory-блокировки «этот человек» (без ПДн в pg_locks — хэш)."""
    who = (email or "").strip().lower() or phone_key(phone)
    if not who:
        return ""
    return f"{prefix}:{hashlib.sha256(who.encode()).hexdigest()[:16]}"


def advisory_lock(key: str) -> None:
    """Блокировка до конца транзакции; ключ дополняется схемой (блокировки общие на БД)."""
    if not key:
        return
    from django.db import connection

    schema = getattr(connection, "schema_name", "") or "public"
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"{schema}:{key}"])
