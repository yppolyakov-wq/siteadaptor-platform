"""UX-D D4.4: виджет бронирования и фид метапоиска — на «Kanal-Manager» (раньше —
под-вкладка «Kanäle & Export» списка номеров). Копирование — кнопкой, без onclick."""

import re
import uuid
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core.models import Membership
from apps.stays import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path, data=None):
    req = RequestFactory().get(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(disabled_modules=[], business_type="hotel")
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": Membership.ROLE_OWNER})
    return req


def test_channels_page_has_widget_and_feed_with_copy_buttons():
    html = views.channels(_req("/dashboard/stays/channels/")).content.decode()
    assert "data-embed-feed" in html
    assert "?embed=1" in html and "/feed" in html  # embed_url и feed_url отрисованы
    assert 'data-copy-target="ch-embed"' in html and 'id="ch-embed"' in html
    assert 'data-copy-target="ch-feed"' in html and 'id="ch-feed"' in html


def test_units_list_no_longer_hosts_widget_or_feed():
    html = views.units(_req("/dashboard/stays/units/")).content.decode()
    assert "?embed=1" not in html and 'data-st-tab="kanaele"' not in html
    assert "data-channels-link" in html


def test_old_kanaele_bookmark_redirects_to_channels():
    resp = views.units(_req("/dashboard/stays/units/", {"tab": "einstellungen", "sec": "kanaele"}))
    assert resp.status_code == 302 and resp.url == "/dashboard/stays/channels/"


def test_no_inline_handlers_on_channels_template():
    text = (ROOT / "templates/stays/channels.html").read_text()
    assert not re.search(r"\son[a-z]+=", text)


def test_copy_helper_lives_in_cabinet_js():
    js = (ROOT / "static/js/cabinet.js").read_text()
    assert "[data-copy-target]" in js and "navigator.clipboard" in js
