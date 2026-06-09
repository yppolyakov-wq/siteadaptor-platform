"""Адаптеры каналов: type → publish/remove. Сейчас только `log` (внутренний,
ничего наружу не шлёт). Внешние адаптеры (Instagram, Google Business Profile,
маркетплейсы) — Phase 2 (P2.9). Адаптер возвращает external_ref при publish и
бросает исключение при ошибке (задача переведёт публикацию в failed + last_error).
"""

import logging

logger = logging.getLogger("publishing")


def _log_publish(publication) -> str:
    logger.info("publish promo=%s channel=%s", publication.promotion_id, publication.channel_id)
    return f"log:{publication.promotion_id}:{publication.channel_id}"


def _log_remove(publication) -> None:
    logger.info("remove promo=%s channel=%s", publication.promotion_id, publication.channel_id)


# type → (publish, remove)
_ADAPTERS = {
    "log": (_log_publish, _log_remove),
}


def publish(publication) -> str:
    """Опубликовать в канал; вернуть external_ref. Бросает при ошибке."""
    pub_fn, _ = _ADAPTERS[publication.channel.type]
    return pub_fn(publication) or ""


def remove(publication) -> None:
    """Снять из канала. Бросает при ошибке."""
    _, rm_fn = _ADAPTERS[publication.channel.type]
    rm_fn(publication)
