"""«Seitenvorlagen» (STU-19b) — экран снесён в FB-27 R4 (решение владельца 2026-11-11:
«убрать сразу»). Настройки типа страницы правятся в «Seitenaufbau»: в панели
«★ Hauptliste», а у страниц без основного списка — на строке «Einstellungen der Seite».

Здесь остались: старые адреса (302 в «Seitenaufbau»), `cabinet_url` — куда ведут ссылки
«настройка этой страницы» из Студии и от помощника, — и вход помощника настройки
(`setup_plan_for`). Чтение и запись настроек — по-прежнему только `page_settings`.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core import ratelimit, setup_assistant

#: Первый тип старых вкладок «Sortiment» / «Aktionen» (адрес без `?typ=`).
_LEGACY_FIRST = {"sortiment": "catalog", "aktionen": "promos"}


def cabinet_url(type_code: str, setting: str = "") -> str:
    """Экран кабинета, где правятся настройки этого типа страницы — строка
    «Seitenaufbau» (`setting` — какую настройку раскрыть)."""
    from apps.core import site_schema

    return site_schema.settings_url(type_code, setting)


PLAN_LIMIT = 20  # questions per user per window (the AI layer has its own daily budget)
PLAN_WINDOW = 600


def _setup_plan(request):
    """STU-19c: answer of the "Was möchten Sie anlegen?" bar (GET ?frage=)."""
    return setup_plan_for(request, request.GET.get("frage") or "")


def setup_plan_for(request, text: str):
    """The plan for a phrase, checked for this request (rights, package, Mini App).
    AIS A-3a: also the answer of the assistant drawer to "create X"."""
    text = (text or "").strip()
    if not text:
        return None
    if ratelimit.hit("setup-plan", str(request.user.pk), limit=PLAN_LIMIT, window=PLAN_WINDOW):
        return setup_assistant.Plan(note=_("Zu viele Fragen — bitte kurz warten."))
    plan = setup_assistant.build_plan(text, request.tenant, request.user)
    return setup_assistant.for_request(plan, request)


def _to_schema(request, default: str = ""):
    """Старые адреса «Seitenvorlagen» → «Seitenaufbau». Тип, на который смотрел
    владелец, сохраняется; вопрос помощнику (`?frage=`) уходит на его экран."""
    frage = (request.GET.get("frage") or "").strip()
    if frage:
        return redirect(reverse("setup-ask") + "?" + urlencode({"frage": frage}))
    return redirect(cabinet_url(request.GET.get("typ", "") or default))


@login_required
def page_templates_sortiment(request):
    return _to_schema(request, _LEGACY_FIRST["sortiment"])


@login_required
def page_templates_aktionen(request):
    return _to_schema(request, _LEGACY_FIRST["aktionen"])


@login_required
def page_templates_website(request):
    return _to_schema(request)
