"""AIS-A A-0: шторка «✨ Assistent» (GET, без ИИ, ничего не пишет)."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from apps.core import assistant, diagnoses, drawer, ratelimit

#: Тяжёлые диагнозы по кнопке: не чаще 20 раз в минуту на пользователя.
HEAVY_LIMIT, HEAVY_WINDOW = 20, 60
#: Дешёвые диагнозы на каждое открытие шторки: не чаще 60 раз в минуту.
OPEN_LIMIT, OPEN_WINDOW = 60, 60


def _seite_value(raw) -> str:
    raw = (raw or "")[:80]
    return raw if raw in assistant.known_screens() else ""


def _seite(request) -> str:
    """Только известные имена экранов: URL из запроса в шторку не попадает."""
    return _seite_value(request.GET.get("seite"))


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
    q = request.GET.get("q") or ""
    # Поиск не пересчитывает диагнозы; частые открытия — тоже нет (лимит на пользователя).
    diagnose = not q and not ratelimit.hit(
        "assistant-open",
        f"{connection.schema_name}:{request.user.pk}",
        limit=OPEN_LIMIT,
        window=OPEN_WINDOW,
    )
    if not q and not diagnose:
        limited = True
    ctx = assistant.build(
        request,
        seite=_seite(request),
        q=q,
        run_key=run_key,
        diagnose=diagnose,
        artikel=(request.GET.get("artikel") or "")[:40],
    )
    from apps.core import assistant_ai

    antwort = request.GET.get("antwort") or ""
    ctx.update(
        {
            "ai_enabled": assistant_ai.enabled(),
            "answer": _answer_ctx(request, antwort) if antwort else None,
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
    ctx["hl_sub"] = "h4" if drawer.is_box(request) else "h3"  # A-1: группы результатов
    if drawer.is_box(request):
        return drawer.fragment(render(request, "core/_assistant_body.html", ctx))
    return render(request, "core/assistant.html", ctx)


def _answer_ctx(request, job: str) -> dict | None:
    """Ответ ИИ для шаблона (pending/done) или None — чужой/мусорный/протухший job."""
    from apps.core import assistant_ai

    entry = assistant_ai.job_state(request, job)
    if entry is None:
        return None
    ans = assistant_ai.present(request, entry)
    ans["job"] = job
    return ans


@login_required
@require_POST
def assistant_ask(request):
    """AIS A-2: «✨ KI fragen». Шторка (X-Sf-Drawer) — JSON {job, url}; без JS — 302 на
    страницу помощника с ?antwort=<job>. Вопрос в URL не попадает (только id задачи)."""
    from django.contrib import messages
    from django.http import JsonResponse
    from django.shortcuts import redirect
    from django.urls import reverse

    from apps.core import assistant_ai

    seite = _seite_value(request.POST.get("seite"))
    got = assistant_ai.ask(request, request.POST.get("frage", ""), seite)
    is_drawer = bool(request.headers.get("X-Sf-Drawer"))
    if got.get("code"):
        text = str(assistant_ai.error_text(got["code"]))
        if is_drawer:
            return JsonResponse({"code": got["code"], "message": text})
        messages.error(request, text)
        return redirect(reverse("assistant") + (f"?seite={seite}" if seite else ""))
    url = reverse("assistant-answer", args=[got["job"]])
    if is_drawer:
        return JsonResponse({"job": got["job"], "url": url})
    query = f"?antwort={got['job']}" + (f"&seite={seite}" if seite else "")
    return redirect(reverse("assistant") + query)


@login_required
@require_GET
def assistant_answer(request, job):
    """Опрос ответа: фрагмент (pending/done), только чтение. Чужой job — 404."""
    from django.http import Http404

    ans = _answer_ctx(request, job)
    if ans is None:
        raise Http404
    resp = render(
        request,
        "core/_assistant_answer.html",
        {"ans": ans, "hl": "h3", "hl_sub": "h4", "next_url": drawer.drawer_next(request, "")},
    )
    resp["X-Sf-Answer-State"] = ans["state"]
    resp["Cache-Control"] = "no-store"
    return resp
