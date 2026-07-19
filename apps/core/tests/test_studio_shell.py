"""ST-3: Studio-оболочка — рейка уровней + page-лента + брендинг (гейт classic_ui).

План st3-studio-shell-plan-2026-07-19.md: переупаковка существующего хрома —
существующие id/классы билдера НЕ переименованы (их держат замки
test_home_builder); новый хром отсутствует в «Klassische Ansicht».
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views as core_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _html(tenant):
    request = RequestFactory().get("/dashboard/site/home/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    request.tenant = tenant
    return core_views.home_builder_view(request).content.decode()


def test_studio_rail_and_pages_strip_render():
    tenant = TenantFactory(slug="stsh", name="StSh", business_type="bakery")
    html = _html(tenant)
    assert 'id="st-rail"' in html and 'data-st-level="look"' in html
    assert 'data-st-level="pages"' in html and 'data-st-level="media"' in html
    assert 'id="st-pages"' in html and "st-page-btn" in html
    assert ">Studio</span>" in html  # брендинг в топ-баре
    # кросс-фейд врезан в swapPreview
    assert "transition:opacity" in html
    # существующие якоря хрома целы (замки старого билдера)
    assert 'id="bld-root"' in html and 'id="bld-area-tabs"' in html
    assert 'id="home-prev-frame"' in html


def test_studio_chrome_hidden_in_classic():
    tenant = TenantFactory(
        slug="stshc",
        name="StShC",
        business_type="bakery",
        site_config={"classic_ui": True},
    )
    html = _html(tenant)
    assert 'id="st-rail"' not in html and 'id="st-pages"' not in html
    assert ">Studio</span>" not in html
    # прежний билдер жив
    assert 'id="bld-root"' in html and 'id="bld-area-tabs"' in html
