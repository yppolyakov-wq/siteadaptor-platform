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


def test_root_mounted_cabinet_not_touched():
    # Разделы кабинета на корне субдомена ВНЕ /dashboard/ (catalog/imports/promotions/
    # crm/willkommen) — тоже кабинет владельца, middleware их не трогает (остаются DENY).
    for path in (
        "/catalog/products/",
        "/imports/",
        "/promotions/redeem/",
        "/promotions/vouchers/redeem/",
        "/crm/",
        "/willkommen/",
    ):
        resp = _call(path)
        assert "X-Frame-Options" not in resp, path


def test_existing_deny_survives_on_cabinet_roots():
    # Реальный прод-стек: XFrameOptionsMiddleware уже выставил DENY на cabinet-странице
    # вне /dashboard/. StorefrontFrameOptionsMiddleware НЕ должен перебить его на SAMEORIGIN
    # (иначе clickjacking-защита кабинета ослабляется — workflow-finding 2026-06-30).
    for path in ("/catalog/products/", "/promotions/vouchers/redeem/", "/crm/", "/imports/"):
        resp = HttpResponse("cabinet")
        resp["X-Frame-Options"] = "DENY"
        out = _call(path, response=resp)
        assert out["X-Frame-Options"] == "DENY", path


def test_customer_account_stays_sameorigin():
    # Клиентский ЛК /konto/ — это витрина (ссылка «Mein Konto» в шапке может кликаться
    # в превью), остаётся SAMEORIGIN, не попадает в blocklist кабинета.
    resp = _call("/konto/")
    assert resp["X-Frame-Options"] == "SAMEORIGIN"


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
