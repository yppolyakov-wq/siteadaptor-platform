"""В5: учёт результатов каталога города — агрегат «день × бизнес × предложение ×
действие × канал» (план docs/v5-portal-analytics-plan-2026-10-17.md).

Порядок для каждого события: робот? → тот же посетитель уже засчитан сегодня? → лимит
частоты → запись. Посетителя различает HMAC(суточная соль, IP|UA) — соль живёт в кэше
48 часов и в БД не попадает, поэтому через двое суток хэш не восстановить, а в таблице
только числа. Недоступный кэш = событие не считаем (недосчёт честнее накрутки).

Запись — один `INSERT … ON CONFLICT DO UPDATE` на пачку (маячок шлёт до 48 карточек),
без буфера: штатный RedisCache Django не умеет HINCRBY/RENAME, а дедуп и так сводит
поток к уникальным посетителям. Всё fail-safe: учёт никогда не роняет страницу.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from apps.core import bots, ratelimit

logger = logging.getLogger(__name__)

SALT_TTL = 48 * 3600
SEEN_TTL = 25 * 3600


def _cfg(key: str):
    return settings.AGGREGATOR_PORTAL_STATS.get(key)


def _salt(day) -> bytes:
    key = f"pstat:salt:{day.isoformat()}"
    cache.add(key, secrets.token_hex(32), SALT_TTL)  # гонка воркеров: побеждает первый
    value = cache.get(key)
    if not value:
        raise RuntimeError("salt unavailable")
    return value.encode()


def _visitor(request, day) -> str:
    ip = ratelimit.client_ip(request)
    ua = request.META.get("HTTP_USER_AGENT", "")
    return hmac.new(_salt(day), f"{ip}|{ua}".encode(), hashlib.sha256).hexdigest()[:16]


def _first_today(day, visitor: str, action: str, row: tuple) -> bool:
    ident = hashlib.md5("|".join(map(str, row)).encode()).hexdigest()  # noqa: S324 — не крипто
    return bool(cache.add(f"pstat:seen:{day.isoformat()}:{action}:{ident}:{visitor}", 1, SEEN_TTL))


def _rows(listings, tenant_schema, kind, ref, listing_id, is_demo):
    if listings:
        for lst in listings:
            yield (lst.tenant_schema, lst.listing_kind, lst.source_ref, lst.pk, bool(lst.is_demo))
    elif tenant_schema:
        yield (tenant_schema, kind or "", ref or "", listing_id, bool(is_demo))


def record(
    request,
    *,
    action: str,
    channel: str,
    listings=None,
    tenant_schema: str = "",
    kind: str = "",
    ref: str = "",
    listing_id: int | None = None,
    is_demo: bool = False,
) -> int:
    """Засчитать событие для листингов (или для бизнеса целиком). Возвращает число
    засчитанных строк; любое исключение глотается и пишется в лог только типом."""
    try:
        return _record(
            request, action, channel, listings, tenant_schema, kind, ref, listing_id, is_demo
        )
    except Exception as exc:  # noqa: BLE001 — учёт не смеет ронять страницу
        logger.warning("portal stats write failed: %s", type(exc).__name__)
        return 0


def _record(request, action, channel, listings, tenant_schema, kind, ref, listing_id, is_demo):
    from .models import PortalStat

    if not _cfg("enabled"):
        return 0
    if action not in PortalStat.ACTIONS_CODES or channel not in PortalStat.CHANNEL_CODES:
        return 0
    if request is None or bots.is_bot(request):
        return 0
    day = timezone.localdate()
    visitor = _visitor(request, day)
    fresh = [
        row
        for row in _rows(listings, tenant_schema, kind, ref, listing_id, is_demo)
        if _first_today(day, visitor, action, row[:3])
    ]
    if not fresh:
        return 0
    limit = _cfg("rate_limit") or 300
    if ratelimit.hit("pstat", ratelimit.client_ip(request), limit=limit, window=3600):
        return 0
    _bump(day, action, channel, fresh)
    return len(fresh)


def _bump(day, action: str, channel: str, rows) -> None:
    """Пачка инкрементов одним запросом. Таблица SHARED (public) — имя с схемой, чтобы
    запись из контекста тенанта (витрина: обращение/сделка) шла туда же."""
    from .models import PortalStat

    table = f'"public".{connection.ops.quote_name(PortalStat._meta.db_table)}'
    values, params = [], []
    for schema, kind, ref, listing_id, demo in rows:
        values.append("(%s, %s, %s, %s, %s, %s, %s, %s, 1)")
        params += [day, schema[:63], kind[:20], ref[:64], listing_id, action, channel, demo]
    sql = (
        f"INSERT INTO {table} (day, tenant_schema, listing_kind, source_ref, listing_id, "  # noqa: S608
        "action, channel, is_demo, count) VALUES " + ", ".join(values) + " "
        "ON CONFLICT (day, tenant_schema, listing_kind, source_ref, action, channel) "
        "DO UPDATE SET count = " + table + ".count + EXCLUDED.count, "
        "listing_id = COALESCE(EXCLUDED.listing_id, " + table + ".listing_id)"
    )
    with connection.cursor() as cur:
        cur.execute(sql, params)


def purge(*, today=None) -> int:
    """Удалить агрегаты старше retention (beat, раз в сутки)."""
    from .models import PortalStat

    today = today or timezone.localdate()
    cutoff = today - timedelta(days=_cfg("retention_days") or 400)
    deleted, _ = PortalStat.objects.filter(day__lt=cutoff).delete()
    return deleted
