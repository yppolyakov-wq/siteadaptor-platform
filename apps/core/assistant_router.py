"""AIS A-5a: один «мозг» помощника — реестр обработчиков фразы вместо цепочки if/elif во вьюхе.

План — docs/ais-a5-one-brain-plan-2026-11-06.md §1. Порядок и поведение 1:1 с прежним
`assistant_views.assistant_ask` (замок паритета — `test_assistant_router`): первый обработчик,
узнавший фразу, её и обрабатывает. Новая ветка добавляется ТОЛЬКО в `HANDLERS` (AST-замок:
во вьюхе нет вызовов `*.intent(`).

`intent(request, q)` — без записи в кэш и без ИИ: попадание (любой объект) или None.
`handle(request, q, raw, seite, hit)` — ставит задачу и возвращает `{"job"}` или `{"code"}`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Handler:
    key: str
    intent: Callable
    handle: Callable


# ───────────────────────── обработчики (порядок = приоритет) ─────────────────────────


def _bulk_intent(request, q):
    from apps.core import assistant_bulk

    return assistant_bulk.intent(request.tenant, request.user, q) or None


def _bulk_handle(request, q, raw, seite, hit):
    # AIS A-4d: «alle Kuchen 10 % teurer» — все товары категории (≤ 50) одним пакетом;
    # раньше A-4b: «blende alle Kuchen aus» — товары, а не сама категория
    from apps.core import assistant_ai, assistant_bulk

    return assistant_ai.put_actions(request, q, builder=assistant_bulk.build)


def _changes_intent(request, q):
    from apps.core import assistant_changes

    return assistant_changes.intent(request.tenant, request.user, q) or None


def _changes_handle(request, q, raw, seite, hit):
    # AIS A-4b: «измени цену / скрой / перенеси» существующего — пакет изменений
    from apps.core import assistant_ai

    return assistant_ai.put_actions(request, q)


def _pages_intent(request, q):
    from apps.core import assistant_pages

    return assistant_pages.intent(request.tenant, request.user, q) or None


def _pages_handle(request, q, raw, seite, hit):
    # AIS A-4c: «покажи товары списком / 4 в ряд» — настройка страницы
    from apps.core import assistant_ai, assistant_pages

    return assistant_ai.put_actions(request, q, builder=assistant_pages.build)


def _escalate_intent(request, q):
    from apps.core import assistant_escalate

    return assistant_escalate.intent(request, q) or None


def _escalate_handle(request, q, raw, seite, hit):
    # AIS A-5d: «funktioniert nicht / ich brauche einen Menschen» — предложение отправить в Support
    from apps.core import assistant_escalate

    return assistant_escalate.handle(request, q, seite)


def _followup_intent(request, q):
    from apps.core import assistant_followup

    return assistant_followup.intent(request, q)


def _followup_handle(request, q, raw, seite, hit):
    # AIS A-5c: «und den Käsekuchen auch» — то же действие, что в прошлом ходе, новый объект
    from apps.core import assistant_ai, assistant_followup

    prev, found = hit
    return assistant_ai.put_actions(
        request, q, builder=lambda tenant, user, text: assistant_followup.build(prev, found)
    )


def _mixed_intent(request, q):
    from apps.core import assistant_ai_actions

    if not assistant_ai_actions.mixed(request.tenant, request.user, q):
        return None
    return assistant_ai_actions.wants(request, q)


def _mixed_handle(request, q, raw, seite, hit):
    # AIS A-4e-3: «Kategorie Torten anlegen und Apfelstrudel ausblenden» — создание И
    # изменение в одной фразе: правила создания взяли бы только первую половину
    from apps.core import assistant_ai, assistant_ai_actions

    got = assistant_ai_actions.ask(request, q, {**hit, "mixed": True})
    if got.get("code") in ("quota", "busy", "unavailable"):
        got = assistant_ai.put_plan(request, q)  # без ИИ — прежний план создания
    return got


def _create_intent(request, q):
    from apps.core import setup_assistant

    return setup_assistant.create_intent(request.tenant, request.user, q) or None


def _create_handle(request, q, raw, seite, hit):
    # AIS A-3a: «создай …» — план с предзаполненной формой, и без ИИ тоже
    from apps.core import assistant_ai

    return assistant_ai.put_plan(request, q)


def _ai_actions_intent(request, q):
    from apps.core import assistant_ai_actions

    return assistant_ai_actions.wants(request, q)


def _ai_actions_handle(request, q, raw, seite, hit):
    # AIS A-4e: правила не поняли, но во фразе есть действие или имя товара — ИИ
    # предлагает пакет из закрытого реестра, факты проверяет сервер
    from apps.core import assistant_ai_actions

    return assistant_ai_actions.ask(request, q, hit)


def _answer_handle(request, q, raw, seite, hit):
    # AIS A-2: вопрос; без ИИ — статьи, а не отказ
    from apps.core import assistant, assistant_ai

    # AS-1: «Wo stelle ich das ein?» — часть ответа (отдельной формы поиска больше нет)
    try:
        where = tuple(assistant.where_for_text(request, q))
    except Exception:  # noqa: BLE001 — подсказка экранов не роняет ответ
        logger.warning("assistant router: where failed", exc_info=True)
        where = ()
    token = assistant_ai.WHERE.set(where)
    try:
        got = assistant_ai.ask(request, raw, seite)
        if got.get("code") == "disabled":
            got = assistant_ai.put_articles(request, q)
    finally:
        assistant_ai.WHERE.reset(token)
    return got


ANSWER = Handler("answer", lambda request, q: True, _answer_handle)

HANDLERS: tuple[Handler, ...] = (
    Handler("bulk", _bulk_intent, _bulk_handle),
    Handler("changes", _changes_intent, _changes_handle),
    Handler("pages", _pages_intent, _pages_handle),
    Handler("escalate", _escalate_intent, _escalate_handle),
    Handler("followup", _followup_intent, _followup_handle),
    Handler("mixed", _mixed_intent, _mixed_handle),
    Handler("create", _create_intent, _create_handle),
    Handler("ai_actions", _ai_actions_intent, _ai_actions_handle),
    ANSWER,
)


def _pick(request, q: str, code: str) -> tuple[Handler, object]:
    if code:  # пустой/длинный вопрос — тот же отказ, что у вопроса A-2
        return ANSWER, True
    for handler in HANDLERS:
        hit = handler.intent(request, q)
        if hit is not None:
            return handler, hit
    return ANSWER, True


def classify(request, raw: str) -> str:
    """Какой обработчик возьмёт фразу (без записи и без ИИ) — для тестов и диагностики."""
    from apps.core import assistant_ai

    q, code = assistant_ai.prepare_question(raw)
    return _pick(request, q, code)[0].key


def route(request, raw: str, seite: str = "") -> tuple[str, dict]:
    """Фраза → (ключ обработчика, {"job"} | {"code"})."""
    from apps.core import assistant_ai, assistant_stats

    q, code = assistant_ai.prepare_question(raw)
    handler, hit = _pick(request, q, code)
    logger.info("assistant route=%s", handler.key)  # без текста вопроса
    # A-6b: ключ обработчика едет в запись задачи (`assistant_ai._put`) — отчёт без текста
    token = assistant_ai.ROUTE.set(handler.key)
    try:
        got = handler.handle(request, q, raw, seite, hit)
    finally:
        assistant_ai.ROUTE.reset(token)
    assistant_stats.bump(assistant_ai._schema_name(), handler.key, got.get("code") or "ok")
    return handler.key, got
