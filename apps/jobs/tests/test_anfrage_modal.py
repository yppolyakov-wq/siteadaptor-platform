"""MEN-11: форма заявки в попапе (запрос владельца «не уводить на страницу»)."""

import pytest
from django.http import Http404
from django.test import RequestFactory

from apps.jobs import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(tenant=None, query=""):
    request = RequestFactory().get(f"/anfrage/formular/{query}")
    request.tenant = tenant if tenant is not None else TenantFactory.build()
    return request


def test_modal_serves_same_form_and_posts_to_standard_receiver():
    """Фрагмент несёт ТУ ЖЕ форму: POST уходит в штатный /anfrage/ (honeypot и
    rate-limit там же) — новых анонимных приёмников не заводим."""
    body = public_views.anfrage_modal(_req()).content.decode()
    assert 'action="/anfrage/"' in body
    assert 'name="website"' in body  # honeypot на месте
    assert 'name="title"' in body and 'name="name"' in body
    assert "data-quick-close" in body  # закрывается generic-модалкой
    assert "data-anfrage-modal" in body


def test_modal_prefills_subject():
    body = public_views.anfrage_modal(
        _req(query="?betreff=Hochzeitsmen%C3%BC%20Wahl")
    ).content.decode()
    assert 'value="Hochzeitsmenü Wahl"' in body


def test_modal_shows_event_fields_when_configured():
    """AF-1: событийные поля кейтеринга приходят и в попап."""
    tenant = TenantFactory.build(
        site_config={
            "anfrage": {"fields": ["date", "guests", "event_type"], "event_types": ["Hochzeit"]}
        }
    )
    body = public_views.anfrage_modal(_req(tenant=tenant)).content.decode()
    assert 'name="event_date"' in body and 'name="guest_count"' in body
    assert "Hochzeit" in body


def test_modal_requires_jobs_module():
    tenant = TenantFactory.build(disabled_modules=["jobs"])
    with pytest.raises(Http404):
        public_views.anfrage_modal(_req(tenant=tenant))
