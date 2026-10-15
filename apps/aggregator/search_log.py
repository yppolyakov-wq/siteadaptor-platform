"""T-8.21: журнал поисковых запросов каталога города — агрегат «день × запрос × город».

План — docs/t8-21-search-log-plan-2026-10-15.md. Персональных данных журнал не хранит
(Р-2): ни IP, ни пользователя, ни сессии, ни времени внутри дня; e-mail/телефон/IBAN в
тексте запроса заменяются пометками до записи. Запись синхронная, но fail-safe (Р-3):
сбой журнала только пишется в лог, поиск отвечает как обычно. Смотрит журнал только
платформа (суперпользователь, админка public). Старое удаляет beat ``purge_search_log``.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)

QUERY_MAX = 100
CITY_MAX = 100
FILTERS_KEY_MAX = 255
_EMAIL = re.compile(r"\S+@\S+\.\w+")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}\b")
_PHONE = re.compile(r"\+?\d(?:[\d \-/]{5,})\d")  # 7+ цифр с разделителями; PLZ (5) и цены целы
_WS = re.compile(r"\s+")


def _cfg(key: str):
    return settings.AGGREGATOR_SEARCH_LOG[key]


def scrub(text: str) -> str:
    """Убрать из свободного текста то, что похоже на персональные данные (Р-2)."""
    text = _EMAIL.sub("‹email›", text or "")
    text = _IBAN.sub("‹iban›", text)
    return _PHONE.sub(
        lambda m: "‹nummer›" if sum(c.isdigit() for c in m.group()) >= 7 else m.group(), text
    )


def normalize_query(q: str) -> str:
    """NFC + casefold + один пробел + чистка + обрезка. Умляуты не сворачиваем — читает человек."""
    q = unicodedata.normalize("NFC", q or "").casefold()
    return scrub(_WS.sub(" ", q).strip())[:QUERY_MAX]


def normalize_city(city: str) -> str:
    return normalize_query(city)[:CITY_MAX]


def filters_key(f) -> tuple[str, dict]:
    """(каноническая строка ключа, словарь для показа). Цены — до целых евро (Р-7),
    сортировка не входит (на поиск не влияет)."""
    from .search import carry

    pairs = []
    for k, v in carry("", f):
        if k == "sort":
            continue
        if k in ("preis_von", "preis_bis"):
            try:
                v = str(int(round(float(v))))
            except (TypeError, ValueError):
                continue
        pairs.append((k, v))
    pairs.sort()
    shown: dict = {}
    for k, v in pairs:
        shown.setdefault(k, []).append(v) if k in ("kat", "merkmal") else shown.__setitem__(k, v)
    return urlencode(pairs)[:FILTERS_KEY_MAX], shown


def _count_capped(qs, cap: int) -> int:
    """Число результатов с потолком: `cap + 1` = «больше cap» (Р-5). Один простой SELECT:
    `values_list("pk")` отбрасывает аннотации ранга, `order_by()` — сортировку."""
    return len(qs.order_by().values_list("pk", flat=True)[: cap + 1])


def log(
    outcome,
    *,
    surface: str,
    city: str = "",
    portal_host: str = "",
    lang: str = "",
    first_page: bool = True,
) -> None:
    """Fail-safe обёртка: никакое исключение журнала не выходит наружу (Р-3)."""
    try:
        _log(
            outcome,
            surface=surface,
            city=city,
            portal_host=portal_host,
            lang=lang,
            first_page=first_page,
        )
    except Exception:  # noqa: BLE001 — журнал не смеет ронять поиск
        logger.warning("search log write failed", exc_info=True)


def _log(outcome, *, surface, city, portal_host, lang, first_page) -> None:
    from .models import SearchQueryLog

    if not _cfg("enabled") or not first_page:
        return
    query = normalize_query(outcome.query)
    if not (query or outcome.filters.active):
        return
    if query and len(query) < _cfg("min_len"):
        return
    if outcome.mode == "empty":
        results = 0
    else:
        results = _count_capped(outcome.qs, settings.AGGREGATOR_SEARCH["max_results"])
    key, shown = filters_key(outcome.filters)
    zero = int(results == 0)
    trigram = int(outcome.mode == "trigram" and results > 0)
    ident = {
        "day": timezone.localdate(),
        "surface": surface,
        "portal_host": (portal_host or "")[:253],
        "city": normalize_city(city),
        "lang": (lang or "")[:8],
        "query_norm": query,
        "filters_key": key,
    }
    deltas = {
        "searches": F("searches") + 1,
        "zero_results": F("zero_results") + zero,
        "trigram_hits": F("trigram_hits") + trigram,
        "last_mode": outcome.mode,
        "last_results": results,
    }
    with transaction.atomic():  # savepoint: сбой не отравит внешнюю транзакцию
        rows = SearchQueryLog.objects.filter(**ident)
        if rows.update(**deltas):
            return
        try:
            with transaction.atomic():
                SearchQueryLog.objects.create(
                    **ident,
                    filters=shown,
                    searches=1,
                    zero_results=zero,
                    trigram_hits=trigram,
                    last_mode=outcome.mode,
                    last_results=results,
                )
        except IntegrityError:  # параллельный первый поиск создал строку раньше
            rows.update(**deltas)


def purge(*, today=None) -> int:
    """Удалить агрегаты старше retention (beat, раз в сутки). FK нет → один DELETE."""
    from .models import SearchQueryLog

    cutoff = (today or timezone.localdate()) - timedelta(days=_cfg("retention_days"))
    deleted, _ = SearchQueryLog.objects.filter(day__lt=cutoff).delete()
    return deleted
