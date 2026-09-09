"""STU-15b: раскладка страницы детали — «Tabs» и «Volle Breite» у услуги.

До этой волны раскладка была только у страницы товара (DL-16.6), хотя тело детали
услуги, номера и события собирается тем же data-driven циклом секций (UA4-2), и в
Studio у этих типов страницы выбора не было вовсе. Разметка и ПОРЯДОК секций от
раскладки не зависят — паритет-замок `test_service_detail_section_order_parity`
остаётся в силе, здесь проверяется только оболочка.
"""

import uuid

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.booking import public_views
from apps.booking.models import Service
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(site_config=None):
    request = RequestFactory().get("/leistung/")
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type="cafe", site_config=site_config or {})
    return request


def _service():
    return Service.objects.create(
        name="Haarschnitt",
        description="Waschen, schneiden, föhnen.",
        duration_minutes=30,
        price_cents=4900,
        is_active=True,
    )


def _html(cfg=None):
    s = _service()
    return public_views.service_detail(_req(cfg), pk=s.pk).content.decode()


def test_default_layout_is_unchanged():
    html = _html()
    assert "data-pd-tabs" not in html
    assert "data-detail-layout" not in html


def test_tabs_layout_turns_sections_into_panels():
    html = _html({"service_detail": {"layout": "tabs"}})
    assert "data-pd-tabs" in html, "секции не собраны вкладками"
    assert 'data-pd-panel="description"' in html
    # Подпись панели — из ЕДИНОГО реестра секций (та же, что в инспекторе Studio).
    assert "Über diese Leistung" in html or "Beschreibung" in html


def test_wide_layout_marks_the_page_shell():
    html = _html({"service_detail": {"layout": "breit"}})
    assert 'data-detail-layout="breit"' in html
    assert "data-pd-tabs" not in html, "«breit» не должен собирать вкладки"


def test_unknown_layout_falls_back_to_the_default_view():
    html = _html({"service_detail": {"layout": "quatsch"}})
    assert "data-pd-tabs" not in html and "data-detail-layout" not in html


# ── STU-15c: дефолт сортировки листинга услуг ────────────────────────────────


def _listing(cfg=None, params=None):
    Service.objects.create(name="B-Kur", duration_minutes=30, price_cents=9900, is_active=True)
    Service.objects.create(name="A-Kur", duration_minutes=30, price_cents=1900, is_active=True)
    request = RequestFactory().get("/termin/", params or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type="cafe", site_config=cfg or {})
    return public_views.termin_index(request).content.decode()


def _order(html):
    return [html.find("A-Kur"), html.find("B-Kur")]


def test_listing_default_order_is_unchanged():
    a, b = _order(_listing())
    assert a >= 0 and b >= 0 and a < b  # Meta ordering по имени


def test_owner_default_sort_applies_without_a_query():
    """Дешёвое первым — выбор владельца действует, пока посетитель не выбрал сам."""
    a, b = _order(_listing({"services_sort": "price_desc"}))
    assert b < a, "дефолт владельца не применён (дорогое должно идти первым)"


def test_visitor_choice_beats_the_owner_default():
    a, b = _order(_listing({"services_sort": "price_desc"}, {"sort": "price_asc"}))
    assert a < b, "?sort= посетителя обязан перекрывать дефолт владельца"
