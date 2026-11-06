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
