"""H1.1: StorefrontFrameOptionsMiddleware — витрина кадрируется same-origin (чтобы
live-preview редактора мог переходить по ссылкам), кабинет/логин остаются DENY,
embed-виджет (xframe_options_exempt) не трогаем.
"""

from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.middleware import StorefrontFrameOptionsMiddleware


def _mw(response):
    return StorefrontFrameOptionsMiddleware(lambda request: response)


def _call(path, response=None):
    response = response if response is not None else HttpResponse("ok")
    req = RequestFactory().get(path)
    return _mw(response)(req)


def test_storefront_pages_get_sameorigin():
    for path in ("/", "/sortiment/", "/sortiment/abc/", "/termin/", "/veranstaltung/", "/anfrage/"):
        resp = _call(path)
        assert resp["X-Frame-Options"] == "SAMEORIGIN", path


def test_dashboard_and_accounts_not_touched():
    # Кабинет/логин/админка — middleware НЕ выставляет SAMEORIGIN (остаётся DENY от
    # XFrameOptionsMiddleware, которого тут нет → заголовка просто нет).
    for path in ("/dashboard/site/home/", "/accounts/login/", "/admin/"):
        resp = _call(path)
        assert "X-Frame-Options" not in resp, path


def test_embed_exempt_response_not_overridden():
    # G10 iframe-виджет (?embed=1) помечен xframe_options_exempt — middleware его не трогает.
    resp = HttpResponse("widget")
    resp.xframe_options_exempt = True
    out = _call("/unterkunft/", response=resp)
    assert "X-Frame-Options" not in out  # остался открытым для чужих сайтов


def test_overrides_existing_deny_on_storefront():
    # Если что-то уже выставило DENY на storefront-ответе — перебиваем на SAMEORIGIN.
    resp = HttpResponse("ok")
    resp["X-Frame-Options"] = "DENY"
    out = _call("/sortiment/", response=resp)
    assert out["X-Frame-Options"] == "SAMEORIGIN"
