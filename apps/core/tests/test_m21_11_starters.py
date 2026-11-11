"""M21.11 P4: заготовки «＋ Neue Seite» — GET заполняет форму и ничего не пишет."""

import pytest

from apps.core import content_page_views as views
from apps.core import page_starters
from apps.core.models import ContentPage
from apps.core.tests.test_m21_10_text_pages_hub import _req, _tenant

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_hub_offers_every_starter():
    html = views.pages_list(_req()).content.decode()
    for key, _label in page_starters.STARTERS:
        assert f'data-page-starter="{key}"' in html
    assert "?vorlage=faq" in html


@pytest.mark.parametrize("key", ["faq", "anfahrt", "zahlung"])
def test_starter_prefills_form_without_writing(key):
    html = views.page_new(_req(f"/x/?vorlage={key}")).content.decode()
    title, body = page_starters.build(key, _tenant())
    assert title and body
    from django.utils.html import escape

    assert escape(title) in html
    assert not ContentPage.objects.exists()


def test_anfahrt_uses_business_data_escaped():
    tenant = _tenant(address="Hauptstr. 1 <b>x</b>", opening_hours="Mo–Fr 9–18")
    _title, body = page_starters.build("anfahrt", tenant)
    assert "Hauptstr. 1" in body and "<b>" not in body
    assert "Mo–Fr 9–18" in body or "<li>" in body


def test_unknown_or_empty_starter_is_empty_page():
    assert page_starters.build("nope") == ("", "")
    assert page_starters.build("leer") == ("", "")
    html = views.page_new(_req("/x/?vorlage=<x-evil>")).content.decode()
    assert "x-evil" not in html
    assert not ContentPage.objects.exists()
