"""STU-15b: раскладка страницы номера («Tabs» / «Volle Breite»).

Особенность номера: часть секций по умолчанию живёт ПОД галереей (HF-3), а часть —
в теле. В раскладке «Tabs» деление снимается: иначе вкладки собрали бы только часть
секций, а рассказ о номере остался бы снаружи.
"""

import uuid

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.stays import public_views
from apps.stays.models import StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _html(cfg=None):
    unit = StayUnit.objects.create(
        name=f"FeWo {uuid.uuid4().hex[:6]}", price_cents=9000, description="Blick auf den See."
    )
    request = RequestFactory().get(f"/unterkunft/{unit.pk}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[], site_config=cfg or {})
    return public_views.unterkunft_unit(request, pk=unit.pk).content.decode()


def test_default_layout_is_unchanged():
    html = _html()
    assert "data-pd-tabs" not in html and "data-detail-layout" not in html


def test_tabs_layout_collects_every_section():
    html = _html({"stay_detail": {"layout": "tabs"}})
    assert "data-pd-tabs" in html
    # описание по умолчанию рендерится ПОД галереей — во вкладках оно обязано быть
    assert 'data-pd-panel="description"' in html
    assert html.count('data-pd-panel="description"') == 1, "секция задвоилась"


def test_wide_layout_marks_the_page_shell():
    html = _html({"stay_detail": {"layout": "breit"}})
    assert 'data-detail-layout="breit"' in html
