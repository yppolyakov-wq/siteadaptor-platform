"""Один Telegram-бот — один хозяин (ops 2026-11-02).

Telegram отдаёт сообщения бота ровно на ОДИН адрес вебхука. Если тот же бот подключён
в двух бизнесах (или бизнес вставил токен бота портала/платформы), последнее
подключение молча забирает вебхук у первого, а отключение у любого снимает его у обоих.
На проде так и вышло: @a123siteadaptor_bot висел на двух бизнесах.

Личность бота — его числовой id, он же префикс токена до «:» (токен можно перевыпустить
в @BotFather, id остаётся). Токены бизнесов шифрованы и лежат в схемах — сравниваем,
расшифровав по схеме; подключение бота — редкое действие, обход схем допустим.
Хозяином считается только АКТИВНЫЙ бот: отключённый вебхука не держит.
"""

import logging

from django.db import ProgrammingError, transaction
from django_tenants.utils import get_tenant_model, schema_context

logger = logging.getLogger(__name__)

PLATFORM = "platform"


def bot_id(token: str) -> str:
    """Числовой id бота из токена `<id>:<secret>`; '' если токен не такой формы."""
    head, sep, _ = (token or "").strip().partition(":")
    return head if sep and head.isdigit() else ""


def tenant_label(schema: str) -> str:
    return f"tenant:{schema}"


def portal_label(host: str) -> str:
    return f"portal:{host}"


def owners_of(token: str, *, exclude: str = "") -> list[str]:
    """Где этот бот уже подключён и активен: метки `tenant:<схема>`, `portal:<хост>`,
    `platform`. `exclude` — метка того, кто подключает сейчас (себя не считаем)."""
    wanted = bot_id(token)
    if not wanted:
        return []
    found: list[str] = []

    def _same(other: str) -> bool:
        return bool(other) and bot_id(other) == wanted

    from apps.telegram.models import TelegramBot

    for schema in (
        get_tenant_model()
        .objects.exclude(schema_name="public")
        .order_by("pk")
        .values_list("schema_name", flat=True)
    ):
        label = tenant_label(schema)
        if label == exclude:
            continue
        with schema_context(schema):
            try:
                # Точка сохранения: ошибка схемы без таблицы не ломает внешнюю транзакцию.
                with transaction.atomic():
                    tokens = list(
                        TelegramBot.objects.filter(is_active=True)
                        .exclude(token="")
                        .values_list("token", flat=True)
                    )
            except ProgrammingError:  # схема без таблицы бота (шаблон, недомигрированная)
                continue
            except Exception as exc:  # noqa: BLE001 — ревью: не глотать молча
                # Сбой одной схемы (БД, расшифровка) не должен ронять подключение у
                # всех, но и тихо пропускать дубль нельзя — в лог с типом ошибки.
                logger.warning("bot ownership scan failed for %s: %s", schema, type(exc).__name__)
                continue
        if any(_same(t) for t in tokens):
            found.append(label)

    from apps.aggregator.models import PortalBot

    with schema_context("public"):
        for host, tok in (
            PortalBot.objects.filter(is_active=True)
            .exclude(token="")
            .values_list("portal__host", "token")
        ):
            label = portal_label(host)
            if label != exclude and _same(tok):
                found.append(label)
        if exclude != PLATFORM:
            try:
                from apps.platform_bot import config

                if config.enabled() and _same(config.token()):
                    found.append(PLATFORM)
            except Exception as exc:  # noqa: BLE001 — нет настроек платформы: не мешаем
                logger.warning("platform bot config unavailable: %s", type(exc).__name__)
    return found
