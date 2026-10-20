"""Удаление ключей кэша по шаблону (DSGVO: данные со случайными ключами — черновики,
ссылки кнопок). Лучшее усилие: приватный API Redis-бэкенда Django; не Redis или ошибка —
0 (гарантия остаётся за TTL и за отказом в правах после удаления связей)."""

from __future__ import annotations

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


def delete_matching(pattern: str, limit: int = 5000) -> int:
    try:
        full = cache.make_key(pattern)
        client = cache._cache.get_client(full, write=True)
        keys, deleted = [], 0
        for key in client.scan_iter(match=full, count=500):
            keys.append(key)
            if len(keys) >= 500:
                deleted += client.delete(*keys)
                keys = []
            if deleted + len(keys) >= limit:
                break
        if keys:
            deleted += client.delete(*keys)
        return int(deleted)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache scan delete skipped: %s", type(exc).__name__)
        return 0
