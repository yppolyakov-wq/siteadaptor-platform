"""STU-15b: раскладка страницы события («Tabs» / «Volle Breite»).

Тематические секции события переупорядочиваются владельцем (M20U-4), поэтому вкладки
обязаны идти В ТОМ ЖЕ порядке — подписи приезжают парами key+label из того же реестра,
что и обычное тело.
"""

import uuid
from datetime import timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.events import public_views
from apps.events.models import Event
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _html(cfg=None):
    ev = Event.objects.create(
        title=f"Konzert {uuid.uuid4().hex[:6]}",
        description="Ein Abend mit Live-Musik.",
        starts_at=timezone.now() + timedelta(days=7),
        status=Event.STATUS_PUBLISHED,
    )
    request = RequestFactory().get(f"/veranstaltung/{ev.pk}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[], site_config=cfg or {})
    return public_views.veranstaltung_detail(request, pk=ev.pk).content.decode()


def test_default_layout_is_unchanged():
    html = _html()
    assert "data-pd-tabs" not in html and "data-detail-layout" not in html


def test_tabs_layout_keeps_the_owner_order():
    html = _html({"event_detail": {"layout": "tabs", "order": ["program", "idea"]}})
    assert "data-pd-tabs" in html
    first, second = html.find('data-pd-panel="program"'), html.find('data-pd-panel="idea"')
    assert first >= 0 and second >= 0 and first < second, "порядок вкладок разошёлся с телом"


def test_wide_layout_marks_the_page_shell():
    html = _html({"event_detail": {"layout": "breit"}})
    assert 'data-detail-layout="breit"' in html
