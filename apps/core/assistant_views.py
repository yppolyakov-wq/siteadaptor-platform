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


def _panel_ctx(request, tab: str) -> dict:
    """AIS A-3c: вкладки панели и данные не-KI вкладок (без диагнозов — дёшево)."""
    from apps.core import assistant_panel

    ctx = {
        "tab": tab,
        "tabs": assistant_panel.tabs_for(request, tab, _seite(request)),
        "support_unread": assistant_panel.support_unread(request),
    }
    if tab == "support":
        ctx["support"] = assistant_panel.support_ctx(request)
    elif tab == "kunden":
        ctx["kunden"] = assistant_panel.kunden_ctx(request)
    return ctx


def _render(request, ctx: dict):
    # Шторка: заголовок диалога — h2, секции под ним — h3 (на странице — h1 → h2).
    ctx["hl"] = "h3" if drawer.is_box(request) else "h2"
    ctx["hl_sub"] = "h4" if drawer.is_box(request) else "h3"  # A-1: группы результатов
    ctx.setdefault("nav", "dashboard")
    ctx.setdefault("next_url", drawer.drawer_next(request, request.path))
    ctx.setdefault("back_url", drawer.drawer_next(request, "") if request.GET.get("next") else "")
    if drawer.is_box(request):
        return drawer.fragment(render(request, "core/_assistant_body.html", ctx))
    return render(request, "core/assistant.html", ctx)


@login_required
@require_GET
def assistant_view(request):
    from apps.core import assistant_panel

    tab = assistant_panel.resolve_tab(request)
    if tab != "ki":
        return _render(request, _panel_ctx(request, tab))
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
    from apps.core import assistant_ai, setup_assistant

    antwort = request.GET.get("antwort") or ""
    try:  # A-3a: «Was möchten Sie anlegen?» — видимой кнопкой, если экран тут открывается
        anlegen = setup_assistant.reachable(request, "setup-ask") and bool(
            setup_assistant.allowed_entities(request.tenant, request.user)
        )
    except Exception:  # noqa: BLE001 — кнопка-дополнение не роняет шторку
        anlegen = False
    ctx.update(
        {
            "ai_enabled": assistant_ai.enabled(),
            "anlegen": anlegen,
            "answer": _answer_ctx(request, antwort) if antwort else None,
            "nav": "dashboard",
            "limited": limited,
            "pruefen": run_key,
            "next_url": drawer.drawer_next(request, request.path),
            # Полная страница из мастера/Mini App — «← Zurück» туда, откуда пришли.
            "back_url": drawer.drawer_next(request, "") if request.GET.get("next") else "",
        }
    )
    ctx.update(_panel_ctx(request, "ki"))
    from apps.core import assistant_history

    ctx["history"] = assistant_history.recent(request)  # A-3d: только чтение
    ctx["history_days"] = assistant_history.RETENTION_DAYS
    return _render(request, ctx)


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

    from apps.core import assistant_ai, assistant_router

    seite = _seite_value(request.POST.get("seite"))
    # AIS A-5a: какая ветка понимает фразу — решает реестр обработчиков (assistant_router)
    _key, got = assistant_router.route(request, request.POST.get("frage", ""), seite)
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


@login_required
@require_POST
@drawer.drawer_aware
def assistant_history_clear(request):
    """AIS A-3d: «Verlauf löschen» — только свои строки этого пользователя."""
    from django.contrib import messages
    from django.shortcuts import redirect
    from django.urls import reverse
    from django.utils.translation import gettext as _

    from apps.core import assistant_history

    assistant_history.clear(request.user)
    messages.success(request, _("Verlauf gelöscht."))
    return redirect(reverse("assistant"))


def _actions_response(request, job: str, *, code: str = ""):
    """Ответ на «Alles übernehmen»/«Rückgängig»: шторка — свежий фрагмент ответа (тот же,
    что у опроса); без JS — 302 на страницу помощника с сообщением."""
    from django.contrib import messages
    from django.http import HttpResponse
    from django.shortcuts import redirect
    from django.urls import reverse
    from django.utils.html import escape

    from apps.core import assistant_actions, assistant_ai

    text = str(assistant_actions.error_text(code)) if code else ""
    valid = bool(assistant_ai.JOB_RE.fullmatch(str(job or "")))
    if not request.headers.get("X-Sf-Drawer"):
        if text:
            messages.error(request, text)
        return redirect(reverse("assistant") + (f"?antwort={job}" if valid else ""))
    ans = _answer_ctx(request, job) if valid else None
    if ans is None:
        resp = HttpResponse(
            f'<div data-assistant-reply><p tabindex="-1" data-assistant-result'
            f' class="text-sm">{escape(text or assistant_actions.error_text("expired"))}</p></div>'
        )
    else:
        ans["action_message"] = text
        resp = render(
            request,
            "core/_assistant_answer.html",
            {"ans": ans, "hl": "h3", "hl_sub": "h4", "next_url": drawer.drawer_next(request, "")},
        )
    resp["Cache-Control"] = "no-store"
    return resp


@login_required
@require_POST
def assistant_apply(request, job):
    """AIS A-4a: «Alles übernehmen» — пакет ТОЛЬКО из кэша задачи этого пользователя;
    POST меняет значения полей и галочки по индексу. Повтор — тот же отчёт."""
    from apps.core import assistant_actions, assistant_ai

    # A-4e: «сырой» ответ ИИ здесь не превращается в пакет — применить можно только то,
    # что владелец видел в предпросмотре
    entry = assistant_ai.job_state(request, job, convert=False)
    if entry is None or entry.get("state") != "done" or not entry.get("actions"):
        return _actions_response(request, job, code="expired")
    try:
        assistant_actions.apply(request, job, entry, request.POST)
    except assistant_actions.ApplyError as exc:
        if exc.code == "invalid":
            assistant_ai.keep_action_input(request, job, entry, request.POST, exc.errors)
        return _actions_response(request, job, code=exc.code)
    return _actions_response(request, job)


@login_required
@require_POST
def assistant_undo(request, job):
    """AIS A-4a: «Rückgängig» — только автор, 10 минут, по снимку полей."""
    from apps.core import assistant_actions, assistant_ai

    if not assistant_ai.JOB_RE.fullmatch(str(job or "")):
        return _actions_response(request, job, code="expired")
    try:
        assistant_actions.undo(request, job)
    except assistant_actions.ApplyError as exc:
        return _actions_response(request, job, code=exc.code)
    return _actions_response(request, job)
