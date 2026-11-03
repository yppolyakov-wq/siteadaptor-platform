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
        "navigate": False,
        "open": "",
    }
    # сообщения израсходованы — не всплывут повторно на следующей странице
    assert req._messages.used is True


def test_error_message_makes_ok_false():
    data = json.loads(_err_view(_req({"HTTP_X_SF_DRAWER": "1"})).content)
    assert data["ok"] is False and data["messages"][0]["text"] == "Nicht möglich."


def test_non_redirect_responses_pass_through():
    assert _forbidden(_req({"HTTP_X_SF_DRAWER": "1"})).status_code == 403


@drawer.drawer_aware
def _form_error_view(request):
    from django.http import HttpResponse

    messages.error(request, "Datum belegt.")
    return drawer.fragment(HttpResponse("<form></form>"))


def test_non_redirect_carries_messages_in_header():
    """Фрагмент с ошибкой формы: сообщение не всплывёт позже на другой странице —
    шторка показывает его из заголовка."""
    req = _req({"HTTP_X_SF_DRAWER": "1"})
    resp = _form_error_view(req)
    assert json.loads(resp["X-Sf-Messages"])[0]["text"] == "Datum belegt."
    assert req._messages.used is True


def test_fragment_is_marked_and_never_cached():
    from django.http import HttpResponse

    resp = drawer.fragment(HttpResponse("x"))
    assert resp["X-Sf-Fragment"] == "1"
    assert "no-store" in resp["Cache-Control"] and resp["Vary"] == "X-Sf-Drawer"


@drawer.drawer_aware
def _to_invoice(request):
    return redirect("/finance/rechnungen/7/")


def test_redirect_elsewhere_than_next_means_navigate():
    req = RequestFactory().post(
        "/x/", {"next": "/dashboard/verkaeufe/?tab=stay"}, HTTP_X_SF_DRAWER="1"
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    data = json.loads(_to_invoice(req).content)
    assert data["navigate"] is True and data["location"] == "/finance/rechnungen/7/"


def test_open_after_is_passed_to_the_client():
    @drawer.drawer_aware
    def view(request):
        drawer.open_after(request, "/dashboard/stays/buchung/9/")
        return redirect("/back/")

    data = json.loads(view(_req({"HTTP_X_SF_DRAWER": "1"})).content)
    assert data["open"] == "/dashboard/stays/buchung/9/"


def test_is_box_by_header_only_on_get():
    get = RequestFactory().get("/x/", HTTP_X_SF_DRAWER="1")
    post = RequestFactory().post("/x/", HTTP_X_SF_DRAWER="1")
    assert drawer.is_box(get) and not drawer.is_box(post)


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


def _drawer_js():
    js = (ROOT / "static/js/cabinet.js").read_text()
    return js.split("// ---- core/_drawer.html ----", 1)[1].split("// ---- ", 1)[0]


def test_drawer_js_contract_strings():
    """ECC-ревью architect: шторка шлёт ТОЛЬКО `X-Sf-Drawer` — на `X-Requested-With`
    часть вьюх (перетаскивание, доска) отвечает своими кодами; редиректы не
    проглатываются (`redirect: "manual"`); в шторку вставляется только ответ с меткой
    `X-Sf-Fragment`; перерисовка областей — с `X-Sf-Refresh` (без тостов триала)."""
    part = _drawer_js()
    assert "X-Requested-With" not in part
    assert 'redirect: "manual"' in part
    assert "X-Sf-Fragment" in part and "X-Sf-Refresh" in part
    assert "sf:region-updated" in part and "popstate" in part


def test_refresh_regions_have_ids():
    """`sfRefreshRegions` ищет область в свежем ответе по id — без id она не обновится."""
    import re

    for path in (ROOT / "templates").rglob("*.html"):
        for tag in re.findall(r"<[a-z]+[^>]*\bdata-drawer-refresh\b[^>]*>", path.read_text()):
            assert re.search(r'\bid="[^"]+"', tag), (path, tag)


def test_drawer_aware_is_the_innermost_decorator():
    """Внешний drawer_aware увидел бы редирект login_required и отдал JSON вместо входа."""
    from apps.stays import views

    code = drawer.drawer_aware(lambda r: r).__code__
    for fn in (views.stay_action, views.booking_delete):
        chain = [fn]
        while hasattr(chain[-1], "__wrapped__"):
            chain.append(chain[-1].__wrapped__)
        # functools.wraps копирует __dict__ — метку несут все обёртки, поэтому
        # проверяем код: прямо над самой вьюхой должна стоять обёртка шторки
        assert len(chain) >= 2 and chain[-2].__code__ is code, fn


def _post(data):
    req = RequestFactory().post("/x/", data, HTTP_X_SF_DRAWER="1", HTTP_HOST="hotel.example")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    return req


@pytest.mark.parametrize("bad", ["//[", "//[x/", "http://[::1", "/\\evil"])
def test_malformed_next_never_500s_after_the_action(bad):
    """ECC django-review D1: urlsplit(«//[») бросал ValueError ПОСЛЕ записи действия."""
    resp = _ok_view(_post({"next": bad}))
    data = json.loads(resp.content)
    assert data["ok"] is True and data["navigate"] is False


def test_navigate_reflashes_messages_for_the_target_page():
    """ECC silent-failure D1: при переходе на другую страницу сообщение (отказ
    удаления) не должно пропасть — его показывает страница назначения."""

    @drawer.drawer_aware
    def refuse(request):
        messages.error(request, "Bezahlte Buchung nicht löschbar.")
        return redirect("/dashboard/stays/buchung/1/")

    req2 = _post({"next": "/dashboard/verkaeufe/?tab=stay"})
    data2 = json.loads(refuse(req2).content)
    assert data2["navigate"] is True and data2["ok"] is False
    assert [str(m) for m in req2._messages._queued_messages] == ["Bezahlte Buchung nicht löschbar."]


def test_message_header_is_capped():
    @drawer.drawer_aware
    def noisy(request):
        from django.http import HttpResponse

        for i in range(30):
            messages.warning(request, "x" * 1000 + str(i))
        return HttpResponse(status=409)

    resp = noisy(_req({"HTTP_X_SF_DRAWER": "1"}))
    items = json.loads(resp["X-Sf-Messages"])
    assert len(items) == drawer.MAX_HEADER_MESSAGES
    assert all(len(m["text"]) <= drawer.MAX_MESSAGE_CHARS for m in items)


def test_drawer_js_silent_failure_guards():
    """ECC silent-failure/a11y D1: сообщения переживают перезагрузку (carry), тост под
    модальным окном откладывается до закрытия, 5xx — «статус неясен», одна отправка
    за раз на всю шторку, флаг подтверждения не залипает."""
    js = (ROOT / "static/js/cabinet.js").read_text()
    part = _drawer_js()
    assert "carry(keepMsgs)" in part and "sessionStorage" in part
    assert "afterClose" in part and "if (dlg.open) { afterClose" in part
    assert "r.status >= 500" in part and "unclear(btn)" in part
    assert "if (busy) return;" in part
    danger = js.split("// ---- core/_danger_confirm.html ----", 1)[1].split("// ---- ", 1)[0]
    assert (
        "form.requestSubmit(btn);\n        // " in danger
        or "delete form.dataset.dangerConfirmed;" in danger.split("requestSubmit(btn);", 1)[1][:400]
    )


def test_live_regions_are_never_display_none():
    css = (ROOT / "static/src/app.css").read_text()
    assert ".ui-drawer-flash:empty { display: none" not in css
