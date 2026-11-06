"""AIS-5: эндпоинты «🌐 Übersetzen» (план docs/ais-5-translate-plan-2026-11-06.md).

Ответ — JSON: ``{"job": id}``, ``{"state": "done", "items": {...}}`` (тот же текст уже
переведён — из кэша, без модели и без лимита) или ``{"code": …}``. Ничего не пишет."""

from __future__ import annotations

import re

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET, require_POST


def _schema() -> str:
    from django.db import connection

    return getattr(connection, "schema_name", "") or ""


@login_required
@require_POST
def i18n_translate_start(request):
    from apps.ai.api import is_enabled
    from apps.core import i18n_translate as it
    from apps.core import ratelimit, view_perms

    if not is_enabled(it.TASK):
        return JsonResponse({"code": "disabled"})
    schema = _schema()
    tenant = getattr(request, "tenant", None)
    screen = it.screen_from(request.POST.get("screen", ""), schema)
    # Право ЗАПИСИ того экрана, с которого нажали: перевод — часть правки этой формы.
    if not screen or not view_perms.allowed(request.user, screen, "POST"):
        return JsonResponse({"code": "forbidden"})
    target = request.POST.get("target", "")
    if not it.target_allowed(tenant, target):
        return JsonResponse({"code": "bad"})
    try:
        items = it.parse_items(request.POST.get("items", ""))
    except it.BadRequest as exc:
        return JsonResponse({"code": exc.code})
    if not items:
        return JsonResponse({"state": "done", "items": {}, "skipped": 0})
    value = it.digest(items, target)
    hit = it.cached(schema, value, items)
    if hit is not None and len(hit) == len(items):
        return JsonResponse({"state": "done", "items": hit, "skipped": 0})
    user_key = f"{schema}:{request.user.pk}"
    if ratelimit.hit("ai-translate-user", user_key, limit=it.RATE_LIMIT, window=it.RATE_WINDOW):
        return JsonResponse({"code": "quota"})
    if ratelimit.hit("ai-translate", schema, limit=it.RATE_LIMIT_TENANT, window=it.RATE_WINDOW):
        ratelimit.refund("ai-translate-user", user_key)
        return JsonResponse({"code": "quota"})
    try:
        job = it.start_job(
            schema=schema, user_pk=request.user.pk, items=items, target=target, value=value
        )
    except it.BadRequest as exc:  # уже идёт задача этого пользователя
        ratelimit.refund("ai-translate-user", user_key)
        ratelimit.refund("ai-translate", schema)
        return JsonResponse({"code": exc.code})
    except Exception:  # noqa: BLE001 — очередь недоступна: попытка не сгорает
        import logging

        logging.getLogger(__name__).exception("i18n translate: job not queued")
        ratelimit.refund("ai-translate-user", user_key)
        ratelimit.refund("ai-translate", schema)
        return JsonResponse({"code": "unavailable"})
    return JsonResponse({"job": job})


@login_required
@require_GET
def i18n_translate_result(request, job):
    from apps.core import i18n_translate as it

    if not re.fullmatch(r"[0-9a-f]{32}", job or ""):
        raise Http404
    state = it.job_state(schema=_schema(), user_pk=request.user.pk, job=job)
    if state is None:
        raise Http404
    return JsonResponse(state)


# ─────────────────────────── AIS-7 «✨ Text vorschlagen» ───────────────────────────

#: Экран → разрешённые виды текста (подпись экрана + право записи доказывают форму).
DRAFT_SCREENS = {
    "catalog:product-edit": ("product",),
    "catalog:product-create": ("product",),  # только подсказка «Erst speichern»
    "booking:service-edit": ("service",),
    "site-home": ("about", "hero"),
}


@login_required
@require_POST
def text_draft_start(request):
    from django.conf import settings

    from apps.ai.api import is_enabled
    from apps.core import i18n_translate, ratelimit, text_draft, text_facts, view_perms

    if not is_enabled(text_draft.TASK):
        return JsonResponse({"code": "disabled"})
    schema = _schema()
    tenant = getattr(request, "tenant", None)
    screen = i18n_translate.screen_from(request.POST.get("screen", ""), schema)
    kind = request.POST.get("kind", "")
    if (
        not screen
        or kind not in DRAFT_SCREENS.get(screen, ())
        or not view_perms.allowed(request.user, screen, "POST")
    ):
        return JsonResponse({"code": "forbidden"})
    locale = request.POST.get("locale") or settings.LANGUAGE_CODE
    active = list(getattr(tenant, "active_locales", None) or [settings.LANGUAGE_CODE])
    if locale not in active or locale not in text_draft.LANGUAGE_NAMES:
        return JsonResponse({"code": "bad"})
    if kind in (text_facts.KIND_PRODUCT, text_facts.KIND_SERVICE):
        locale = settings.LANGUAGE_CODE  # описания — в базовом поле
    pk = request.POST.get("pk", "")
    obj = None
    if kind in (text_facts.KIND_PRODUCT, text_facts.KIND_SERVICE):
        obj = text_draft.load_object(kind, pk)
        if obj is None:
            return JsonResponse({"code": "gone"})
    facts = text_facts.facts_for(kind, obj, tenant)
    value = text_draft.digest(kind, facts, locale)
    hit = text_draft.cached(schema, value)
    if hit is not None:
        return JsonResponse({"state": "done", "fields": hit, "rejected": []})
    user_key = f"{schema}:{request.user.pk}"
    if ratelimit.hit(
        "ai-draft-user", user_key, limit=text_draft.RATE_LIMIT, window=text_draft.RATE_WINDOW
    ):
        return JsonResponse({"code": "quota"})
    if ratelimit.hit(
        "ai-draft", schema, limit=text_draft.RATE_LIMIT_TENANT, window=text_draft.RATE_WINDOW
    ):
        ratelimit.refund("ai-draft-user", user_key)
        return JsonResponse({"code": "quota"})
    try:
        job = text_draft.start_job(
            schema=schema,
            user_pk=request.user.pk,
            kind=kind,
            pk=str(getattr(obj, "pk", "") or ""),
            locale=locale,
            value=value,
        )
    except text_draft.Busy:
        ratelimit.refund("ai-draft-user", user_key)
        ratelimit.refund("ai-draft", schema)
        return JsonResponse({"code": "busy"})
    except Exception:  # noqa: BLE001 — очередь недоступна: попытка не сгорает
        import logging

        logging.getLogger(__name__).exception("text draft: job not queued")
        ratelimit.refund("ai-draft-user", user_key)
        ratelimit.refund("ai-draft", schema)
        return JsonResponse({"code": "unavailable"})
    return JsonResponse({"job": job})


@login_required
@require_GET
def text_draft_result(request, job):
    from apps.core import text_draft

    if not re.fullmatch(r"[0-9a-f]{32}", job or ""):
        raise Http404
    state = text_draft.job_state(schema=_schema(), user_pk=request.user.pk, job=job)
    if state is None:
        raise Http404
    return JsonResponse(state)
