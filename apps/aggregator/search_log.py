"""T-8.21: журнал поисковых запросов каталога города — агрегат «день × запрос × город».

План — docs/t8-21-search-log-plan-2026-10-15.md. Данные МИНИМИЗИРОВАНЫ, но не анонимны
по построению (Р-2): ни IP, ни пользователя, ни сессии, ни времени внутри дня; e-mail/
телефон/IBAN в тексте запроса заменяются пометками до записи, но имя или адрес, введённые
в строку поиска, регулярками не ловятся — поэтому одиночные запросы (searches == 1)
удаляются раньше остальных (`retention_days_single`). Запись синхронная, но fail-safe (Р-3):
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
_EMAIL = re.compile(r"\S+@\S+")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,4})?\b", re.I)
# Телефон: 7+ цифр с любыми разделителями (пробел, -, /, ., скобки); PLZ (5) и цены целы.
_PHONE = re.compile(r"\(?\+?[\d][\d \-/().]{5,}\d")
_WS = re.compile(r"\s+")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def _cfg(key: str):
    return settings.AGGREGATOR_SEARCH_LOG[key]


def scrub(text: str) -> str:
    """Убрать из свободного текста то, что похоже на персональные данные (Р-2).

    Регистронезависимо (зовётся ДО casefold и после — IBAN в нижнем регистре тоже ловится)."""
    text = _EMAIL.sub("‹email›", text or "")
    text = _IBAN.sub("‹iban›", text)
    return _PHONE.sub(
        lambda m: "‹nummer›" if sum(c.isdigit() for c in m.group()) >= 7 else m.group(), text
    )


def normalize_query(q: str) -> str:
    """Чистка → NFC → casefold → один пробел → обрезка. Умляуты не сворачиваем — читает
    человек. Управляющие символы (NUL и т.п.) вырезаются: Postgres их не принимает."""
    q = _CTRL.sub(" ", unicodedata.normalize("NFC", q or ""))
    q = scrub(_WS.sub(" ", q).strip()).casefold()
    return _WS.sub(" ", q).strip()[:QUERY_MAX]


def normalize_city(city: str) -> str:
    """Город — ТОЛЬКО из реестра (`core.districts`): свободный `?city=` в журнал не пишется
    (иначе любой текст плодил бы строки и мусорил фильтр админки)."""
    from apps.core import districts

    return districts.city_label(city or "")[:CITY_MAX]


def filters_key(f, extra: dict | None = None) -> tuple[str, dict]:
    """(каноническая строка ключа, словарь для показа). Цены — до целых евро (Р-7),
    сортировка не входит (на поиск не влияет). ``extra`` — область поверхности (вкладка,
    район из пути, тип бизнеса…): без неё «brot» на вкладке «Angebote» (0) и на «Alle»
    (12) слились бы в одну строку и «Nichts gefunden» врал бы."""
    from .search import carry

    pairs = [(str(k), str(v)[:50]) for k, v in (extra or {}).items() if v]
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
        if k in ("kat", "merkmal"):
            shown.setdefault(k, []).append(v)
        else:
            shown[k] = v
    key = urlencode(pairs)
    if len(key) > FILTERS_KEY_MAX:  # ключ и показ обязаны совпадать — режем оба
        key = key[:FILTERS_KEY_MAX]
        shown = {"_truncated": key}
    return key, shown


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
    extra: dict | None = None,
) -> None:
    """Fail-safe обёртка: никакое исключение журнала не выходит наружу (Р-3).
    В лог ошибки сам запрос не попадает (только тип исключения)."""
    try:
        _log(
            outcome,
            surface=surface,
            city=city,
            portal_host=portal_host,
            lang=lang,
            first_page=first_page,
            extra=extra,
        )
    except Exception as exc:  # noqa: BLE001 — журнал не смеет ронять поиск
        logger.warning("search log write failed: %s", type(exc).__name__)


def _log(outcome, *, surface, city, portal_host, lang, first_page, extra) -> None:
    from .models import SearchQueryLog

    if not _cfg("enabled") or not first_page:
        return
    query = normalize_query(outcome.query)
    if query and len(query) < _cfg("min_len"):
        query = ""  # одиночная буква не запрос; фильтры при ней — всё ещё поиск
    if not (query or outcome.filters.active):
        return
    key, shown = filters_key(outcome.filters, extra)
    ident = {
        "day": timezone.localdate(),
        "surface": surface,
        "portal_host": (portal_host or "")[:253],
        "city": normalize_city(city),
        "lang": (lang or "")[:8],
        "query_norm": query,
        "filters_key": key,
    }
    with transaction.atomic():  # savepoint: сбой (и подсчёта тоже) не отравит внешнюю транзакцию
        if outcome.mode == "empty":
            results = 0
        else:
            results = _count_capped(outcome.qs, settings.AGGREGATOR_SEARCH["max_results"])
        zero = int(results == 0)
        trigram = int(outcome.mode == "trigram" and results > 0)
        deltas = {
            "searches": F("searches") + 1,
            "zero_results": F("zero_results") + zero,
            "trigram_hits": F("trigram_hits") + trigram,
            "last_mode": outcome.mode,
            "last_results": results,
        }
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
    """Удалить агрегаты старше retention (beat, раз в сутки). FK нет → простые DELETE.
    Одиночные запросы (`searches == 1`) — раньше (`retention_days_single`): именно в них
    вероятнее всего имя или адрес, которые регулярки не ловят (минимизация, Р-2)."""
    from .models import SearchQueryLog

    today = today or timezone.localdate()
    cutoff = today - timedelta(days=_cfg("retention_days"))
    deleted, _ = SearchQueryLog.objects.filter(day__lt=cutoff).delete()
    single_cutoff = today - timedelta(days=_cfg("retention_days_single"))
    deleted_single, _ = SearchQueryLog.objects.filter(
        day__lt=single_cutoff, searches__lte=1
    ).delete()
    return deleted + deleted_single
