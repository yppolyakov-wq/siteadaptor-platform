"""UX-D D1.1: шторка кабинета — серверная половина и подключение."""

import json
from pathlib import Path

import pytest
from django.contrib import messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.test import RequestFactory

from apps.core import drawer

ROOT = Path(__file__).resolve().parents[3]


def _req(headers=None, get=None):
    req = (
        RequestFactory().post("/x/", **(headers or {}))
        if get is None
        else RequestFactory().get("/x/", get)
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    return req


@drawer.drawer_aware
def _ok_view(request):
    messages.success(request, "Gespeichert.")
    return redirect("/back/")


@drawer.drawer_aware
def _err_view(request):
    messages.error(request, "Nicht möglich.")
    return redirect("/back/")


@drawer.drawer_aware
def _forbidden(request):
    return HttpResponseForbidden("no")


def test_redirect_becomes_json_only_for_drawer_requests():
    plain = _ok_view(_req())
    assert plain.status_code == 302
    req = _req({"HTTP_X_SF_DRAWER": "1"})
    data = json.loads(_ok_view(req).content)
    assert data == {
        "ok": True,
        "messages": [{"level": "success", "text": "Gespeichert."}],
    }
    # сообщения израсходованы — не всплывут повторно на следующей странице
    assert req._messages.used is True


def test_error_message_makes_ok_false():
    data = json.loads(_err_view(_req({"HTTP_X_SF_DRAWER": "1"})).content)
    assert data["ok"] is False and data["messages"][0]["text"] == "Nicht möglich."


def test_non_redirect_responses_pass_through():
    assert _forbidden(_req({"HTTP_X_SF_DRAWER": "1"})).status_code == 403


@pytest.mark.parametrize(
    "bad", ["//evil.example", "/\\evil.example", "https://evil.example/", "/\tx"]
)
def test_drawer_next_rejects_foreign_targets(bad):
    req = RequestFactory().get("/x/", {"next": bad}, HTTP_HOST="hotel.example")
    assert drawer.drawer_next(req, "/dashboard/") == "/dashboard/"


def test_with_param_never_glues_query_by_hand():
    assert (
        drawer.with_param("/dashboard/stays/buchung/1/", "buchung", 5)
        == "/dashboard/stays/buchung/1/?buchung=5"
    )
    assert drawer.with_param("/v/?tab=stay&buchung=1", "buchung", 5) == "/v/?tab=stay&buchung=5"


def test_drawer_is_mounted_once_in_the_cabinet_shell():
    base = (ROOT / "templates/tenant/_base_dashboard.html").read_text()
    assert base.count('{% include "core/_drawer.html" %}') == 1
    tpl = (ROOT / "templates/core/_drawer.html").read_text()
    assert (
        'aria-labelledby="sf-drawer-title"' in tpl
        and "data-drawer-close" in tpl
        and "aria-label=" in tpl
    )
    assert ".ui-drawer" in (ROOT / "static/css/app.css").read_text()


def test_drawer_js_never_builds_fragment_urls_from_pathname():
    """Разведка D1: компактная шахматка слала fetch на location.pathname и вставляла в
    панель целую страницу. Шторка берёт адрес только из href ссылки."""
    js = (ROOT / "static/js/cabinet.js").read_text()
    part = js.split("// ---- core/_drawer.html ----", 1)[1].split("// ---- ", 1)[0]
    assert (
        "fragmentUrl(u)" in part and "cabinetUrl(" in part
    )  # только страницы кабинета этого сайта
    assert "location.pathname + location.search" not in part


def test_drawer_fragments_carry_no_inline_handlers_or_scripts():
    """Ревью безопасности D1: фрагмент вставляется через innerHTML — inline-обработчики
    `on…=` там исполнились бы (CSP пока report-only). Скрипты не исполняются, но и не
    нужны: весь JS шторки — в cabinet.js."""
    import re

    for name in ("templates/stays/_booking_drawer.html",):
        text = (ROOT / name).read_text()
        assert "<script" not in text
        assert not re.search(r"\son[a-z]+=", text), name
