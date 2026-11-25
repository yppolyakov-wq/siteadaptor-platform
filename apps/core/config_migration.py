"""Общая механика переноса настроек сайта (`Tenant.site_config`) командами деплоя.

Вынесено из `page_axes_migration` (FB-31.7) для FB-33 M2c (`detach_quick_links`), чтобы
блокировка, сверка «настройки не менялись», снимок и откат были ОДНИМ писателем
(вердикт architect, `docs/fb33-editor-model-2026-11-19.md`). Здесь только механика: что и
как переносится, решает модуль переноса.

* `write_with_snapshot` — внутри транзакции: строка под блокировкой (не дольше
  `LOCK_TIMEOUT`), настройки не менялись с расчёта (`config_hash`) и `guard()` истинен —
  записать и снять снимок ключей `touched`; иначе None (перенос считается заново).
* `undo` — откат последнего снимка причины `reason`; настройки с тех пор меняли —
  «changed», ничего не трогаем (решает владелец).
* `rolled_back` — владелец откатил: перенос не повторяется на следующих деплоях.

Откаты разных причин независимы (фильтр по `reason`), но идут в обратном порядке: откат
более раннего переноса после более позднего вернёт «changed» (хэш уже другой).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

LOCK_TIMEOUT = "2s"
#: SQLSTATE «lock_not_available» — строка занята дольше `LOCK_TIMEOUT`
LOCK_NOT_AVAILABLE = "55P03"


def is_lock_timeout(exc) -> bool:
    """Занято (lock_timeout), а не обрыв соединения и пр. psycopg 3 даёт код в `sqlstate`,
    psycopg 2 — в `pgcode`; Django кладёт исходное исключение в `__cause__`."""
    cause = getattr(exc, "__cause__", None)
    code = getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)
    return code == LOCK_NOT_AVAILABLE


def config_hash(cfg) -> str:
    raw = json.dumps(cfg or {}, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def lock(model, pk):
    """Строка под блокировкой, но не дольше `LOCK_TIMEOUT` (деплой не висит на занятом сайте)."""
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
    return model.objects.select_for_update().get(pk=pk)


def bump(schema: str, *, label: str) -> bool:
    """Сброс кэша витрины после записи; сбой — в лог и `False`, не сбой переноса (данные
    записаны; команда считает такие сайты и выходит с ошибкой)."""
    from apps.core.pagecache import bump_storefront_cache

    try:
        ok = bump_storefront_cache(schema)
    except Exception:  # noqa: BLE001
        ok = False
    if not ok:
        logger.warning("%s: cache bump failed for %s", label, schema)
    return ok


def rolled_back(tenant_pk, reason: str) -> bool:
    from apps.tenants.models import SiteConfigSnapshot

    return SiteConfigSnapshot.objects.filter(
        tenant_id=tenant_pk, reason=reason, undone_at__isnull=False
    ).exists()


def write_with_snapshot(
    tenant_pk,
    before: dict,
    new: dict,
    *,
    reason: str,
    touched: tuple[str, ...],
    lock_row: Callable | None = None,
    guard: Callable[[], bool] | None = None,
    send_signals: bool = True,
) -> str | None:
    """Под блокировкой (вызывать внутри `transaction.atomic()`): настройки не менялись —
    записать `new` и снять снимок ключей `touched`, вернуть схему; менялись — None.

    `send_signals=False` — запись `.update()` мимо `save()`: не срабатывают приёмник SE-5a
    (сброс кэша витрины ДО коммита — гонка: читатель кладёт старый конфиг под новую версию;
    вызывающий сбрасывает кэш сам в `on_commit`), приёмник аудита `tenant.updated`
    (вызывающий пишет своё событие) и `auto_now` у `updated_at`."""
    from apps.tenants.models import SiteConfigSnapshot, Tenant

    locked = (lock_row or lock)(Tenant, tenant_pk)
    if config_hash(locked.site_config or {}) != config_hash(before):
        return None
    if guard is not None and not guard():
        return None
    if send_signals:
        locked.site_config = new
        locked.save(update_fields=["site_config"])
    else:
        Tenant.objects.filter(pk=locked.pk).update(site_config=new)
    # хэш — после записи и чтения из базы (JSONB): откат сравнивает то же самое
    locked.refresh_from_db(fields=["site_config"])
    SiteConfigSnapshot.objects.create(
        tenant=locked,
        reason=reason,
        before={k: before.get(k) for k in touched},  # только тронутые ключи
        after_hash=config_hash(locked.site_config or {}),
    )
    return locked.schema_name


def undo(
    tenant_pk,
    *,
    reason: str,
    touched: tuple[str, ...],
    label: str,
    lock_row: Callable | None = None,
) -> str:
    """Откат последнего снимка `reason`: "undone" | "none" (нечего) | "changed"."""
    from django.db import transaction
    from django.utils import timezone

    from apps.tenants.models import SiteConfigSnapshot, Tenant

    with transaction.atomic():
        locked = (lock_row or lock)(Tenant, tenant_pk)
        snap = (
            SiteConfigSnapshot.objects.select_for_update()
            .filter(tenant=locked, reason=reason, undone_at__isnull=True)
            .order_by("-created_at", "-id")
            .first()
        )
        if snap is None:
            return "none"
        if config_hash(locked.site_config or {}) != snap.after_hash:
            return "changed"
        restored = dict(locked.site_config or {})
        for key in touched:
            old = (snap.before or {}).get(key)
            if old is None:
                restored.pop(key, None)
            else:
                restored[key] = old
        locked.site_config = restored
        locked.save(update_fields=["site_config"])
        snap.undone_at = timezone.now()
        snap.save(update_fields=["undone_at"])
        transaction.on_commit(lambda s=locked.schema_name: bump(s, label=label))
    return "undone"
