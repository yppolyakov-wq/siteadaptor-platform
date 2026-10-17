"""В5: учёт результатов каталога города — агрегат «день × бизнес × предложение ×
действие × канал» (план docs/v5-portal-analytics-plan-2026-10-17.md).

Порядок для каждого события: робот? → лимит частоты → тот же посетитель уже засчитан
сегодня? → запись. Посетителя различает HMAC(суточная соль, IP|UA). В БД попадают только
числа; в кэше же метка посетителя (псевдоним) живёт до 25 часов вместе с солью — потом
обе истекают и метку не восстановить (строка для Datenschutzerklärung: «kurzzeitig
pseudonymisiert im Cache, ohne Cookies»). Недоступный кэш = событие не считаем.

Цифры ориентировочные: без cookie дедуп обходится сменой UA/IP, поэтому учёт НЕ годится
для биллинга или цены featured-размещения.

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
from django.db import connection, transaction
from django.utils import timezone

from apps.core import bots, ratelimit

logger = logging.getLogger(__name__)

SEEN_TTL = 25 * 3600
SALT_TTL = SEEN_TTL  # соль не переживает метки, которые она защищает
MAX_BATCH = 48  # карточек в одной пачке маячка
PURGE_BATCH = 10_000


def _cfg(key: str):
    return settings.AGGREGATOR_PORTAL_STATS.get(key)


def channel_for(request) -> str:
    """Канал = поверхность: портал города или главный домен `/entdecken/`."""
    return "portal" if getattr(request, "portal", None) is not None else "entdecken"


def should_count(request, method: str = "GET") -> bool:
    """Дешёвый пред-гейт ДО запроса в БД: бот на cache hit не платит запросом.
    HEAD/OPTIONS не считаем — это не просмотр человеком. Маячок показов (V5-4) — POST."""
    try:
        return request.method == method and bool(_cfg("enabled")) and not bots.is_bot(request)
    except Exception:  # noqa: BLE001 — учёт не смеет ронять страницу
        return False


def first_sight(request, action: str, pk) -> bool:
    """Пред-гейт БЕЗ БД для страниц под кэшем: повторный просмотр тем же посетителем за
    день и превышение лимита частоты отсекаются до запроса листинга — иначе кэш страницы
    перестал бы беречь БД (ревью V5-2). Отдельный бакет: основной лимит `record` не
    расходуется дважды. Любой сбой → False (не считаем, страницу не трогаем)."""
    try:
        limit = _cfg("rate_limit") or 300
        if ratelimit.hit("pstat-pre", ratelimit.client_ip(request), limit=limit, window=3600):
            return False
        day = timezone.localdate()
        key = f"pstat:pre:{day.isoformat()}:{action}:{int(pk)}:{_visitor(request, day)}"
        return bool(cache.add(key, 1, SEEN_TTL))
    except Exception:  # noqa: BLE001 — учёт не смеет ронять страницу
        return False


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


def _seen_key(day, visitor: str, action: str, row: tuple) -> str:
    ident = hashlib.md5("|".join(map(str, row)).encode()).hexdigest()  # noqa: S324 — не крипто
    return f"pstat:seen:{day.isoformat()}:{action}:{ident}:{visitor}"


def _first_today(day, visitor: str, action: str, row: tuple) -> bool:
    return bool(cache.add(_seen_key(day, visitor, action, row), 1, SEEN_TTL))


def _rows(listings, tenant_schema, kind, ref, listing_id, is_demo):
    """Строки к записи, уже обрезанные под поля и без повторов ключа: дубль в одном
    `INSERT … ON CONFLICT` — ошибка «cannot affect row a second time». Сортировка даёт
    параллельным пачкам один порядок блокировок (без взаимоблокировок).

    `tenant_schema`/`kind`/`ref` — только серверные значения (листинг из БД или схема
    текущего запроса), никогда не из параметров запроса: иначе мусор в общей таблице."""
    raw = []
    if listings:
        for lst in listings:
            raw.append((lst.tenant_schema, lst.listing_kind, lst.source_ref, lst.pk, lst.is_demo))
    elif tenant_schema:
        raw.append((tenant_schema, kind or "", ref or "", listing_id, is_demo))
    seen, out = set(), []
    for schema, k, r, pk, demo in raw:
        key = ((schema or "")[:63], (k or "")[:20], (r or "")[:64])
        if key in seen or not key[0]:
            continue
        seen.add(key)
        out.append((*key, pk, bool(demo)))
        if len(out) >= MAX_BATCH:
            break
    return sorted(out, key=lambda row: row[:3])


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
    once_key: str = "",
) -> int:
    """Засчитать событие для листингов (или для бизнеса целиком). Возвращает число
    засчитанных строк; любое исключение глотается и пишется в лог только типом.

    `once_key` (V5-5, обращения/сделки): дедуп по ОБЪЕКТУ, а не «посетитель за день» —
    два заказа одного человека = две сделки, повтор того же заказа = одна."""
    try:
        return _record(
            request,
            action,
            channel,
            listings,
            tenant_schema,
            kind,
            ref,
            listing_id,
            is_demo,
            once_key,
        )
    except Exception as exc:  # noqa: BLE001 — учёт не смеет ронять страницу
        logger.warning("portal stats write failed: %s", type(exc).__name__)
        return 0


def _record(
    request, action, channel, listings, tenant_schema, kind, ref, listing_id, is_demo, once_key=""
):
    from .models import PortalStat

    if not _cfg("enabled"):
        return 0
    if action not in PortalStat.ACTIONS_CODES or channel not in PortalStat.CHANNEL_CODES:
        return 0
    if request is None or bots.is_bot(request):
        return 0
    rows = _rows(listings, tenant_schema, kind, ref, listing_id, is_demo)
    if not rows:
        return 0
    # Лимит ДО дедупа: иначе смена UA плодила бы ключи дедупа в кэше без всякого лимита.
    limit = _cfg("rate_limit") or 300
    if ratelimit.hit("pstat", ratelimit.client_ip(request), limit=limit, window=3600):
        return 0
    day = timezone.localdate()
    if once_key:
        key = f"pstat:once:{action}:{rows[0][0]}:{once_key}"[:240]
        if not cache.add(key, 1, SEEN_TTL):
            return 0
        try:
            _bump(day, action, channel, rows[:1])
        except Exception:
            cache.delete(key)
            raise
        return 1
    visitor = _visitor(request, day)
    fresh = [row for row in rows if _first_today(day, visitor, action, row[:3])]
    if not fresh:
        return 0
    try:
        _bump(day, action, channel, fresh)
    except Exception:
        # Метки дедупа уже стоят, а записи нет: без отката этот визит пропал бы на весь день.
        cache.delete_many([_seen_key(day, visitor, action, row[:3]) for row in fresh])
        raise
    return len(fresh)


def _bump(day, action: str, channel: str, rows) -> None:
    """Пачка инкрементов одним запросом. Таблица SHARED (public) — имя с схемой, чтобы
    запись из контекста тенанта (витрина: обращение/сделка) шла туда же."""
    from .models import PortalStat

    table = f'"public".{connection.ops.quote_name(PortalStat._meta.db_table)}'
    values, params = [], []
    for schema, kind, ref, listing_id, demo in rows:
        values.append("(%s, %s, %s, %s, %s, %s, %s, %s, 1)")
        params += [day, schema, kind, ref, listing_id, action, channel, demo]
    sql = (
        f"INSERT INTO {table} (day, tenant_schema, listing_kind, source_ref, listing_id, "  # noqa: S608
        "action, channel, is_demo, count) VALUES " + ", ".join(values) + " "
        "ON CONFLICT (tenant_schema, day, action, channel, listing_kind, source_ref) "
        "DO UPDATE SET count = " + table + ".count + EXCLUDED.count, "
        "listing_id = COALESCE(EXCLUDED.listing_id, " + table + ".listing_id)"
    )
    # Savepoint: учёт зовут и изнутри атомика сделки — сбой INSERT не обрывает её.
    with transaction.atomic(), connection.cursor() as cur:
        cur.execute(sql, params)


def purge(*, today=None) -> int:
    """Удалить агрегаты старше retention (beat, раз в сутки)."""
    from .models import PortalStat

    today = today or timezone.localdate()
    cutoff = today - timedelta(days=_cfg("retention_days") or 400)
    old = PortalStat.objects.filter(day__lt=cutoff)
    total = 0
    while True:  # пачками: первый прогон после простоя не держит одну длинную транзакцию
        batch = list(old.order_by().values_list("pk", flat=True)[:PURGE_BATCH])
        if not batch:
            return total
        deleted, _ = PortalStat.objects.filter(pk__in=batch).delete()
        total += deleted
