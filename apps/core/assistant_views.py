"""AIS-A A-0: шторка «✨ Assistent» (GET, без ИИ, ничего не пишет)."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.core import assistant, diagnoses, drawer, ratelimit

#: Тяжёлые диагнозы по кнопке: не чаще 20 раз в минуту на пользователя.
HEAVY_LIMIT, HEAVY_WINDOW = 20, 60


def _seite(request) -> str:
    """Только известные имена экранов: URL из запроса в шторку не попадает."""
    from apps.core import nav_registry, readiness

    raw = (request.GET.get("seite") or "")[:80]
    known = (
        {e.url_name for e in nav_registry.ENTRIES}
        | {a.url_name for a in nav_registry.ANCHORS}
        | {i.url_name for i in readiness.REGISTRY}
        | set(assistant.SCREEN_EXTRA)
    )
    return raw if raw in known else ""


@login_required
@require_GET
def assistant_view(request):
    run_key = request.GET.get("pruefen") or ""
    limited = False
    if run_key not in diagnoses.BY_KEY or diagnoses.BY_KEY[run_key].cost != diagnoses.HEAVY:
        run_key = ""
    elif ratelimit.hit(
        "assistant-diag",
        f"{connection.schema_name}:{request.user.pk}",
        limit=HEAVY_LIMIT,
        window=HEAVY_WINDOW,
    ):
        run_key, limited = "", True
    ctx = assistant.build(
        request, seite=_seite(request), q=request.GET.get("q") or "", run_key=run_key
    )
    ctx.update(
        {
            "nav": "dashboard",
            "limited": limited,
            "pruefen": run_key,
            "next_url": drawer.drawer_next(request, request.path),
            # Полная страница из мастера/Mini App — «← Zurück» туда, откуда пришли.
            "back_url": drawer.drawer_next(request, "") if request.GET.get("next") else "",
        }
    )
    # Шторка: заголовок диалога — h2, секции под ним — h3 (на странице — h1 → h2).
    ctx["hl"] = "h3" if drawer.is_box(request) else "h2"
    if drawer.is_box(request):
        return drawer.fragment(render(request, "core/_assistant_body.html", ctx))
    return render(request, "core/assistant.html", ctx)
