"""FB-30.10: предпросмотр дизайна показывает полный набор примеров — баннер с фото и текстом,
вопросы, галерею, команду, акции; отзывы-примеры — только владельцу (вход в кабинет), иначе
на публичной витрине стояли бы выдуманные отзывы. В базу ничего не пишется."""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.catalog.tests.test_storefront import _req
from apps.core import design_samples
from apps.promotions import public_views

pytestmark = pytest.mark.django_db

DESIGN = "?preview=1&look=klar"
SECTIONS = [
    {"key": k, "enabled": True}
    for k in ("hero", "promotions", "faq", "gallery", "team", "testimonials", "products")
]


def _owner():
    from apps.core.tests.test_m21_6_content_pages import _user

    return _user()  # владелец: Membership в этой схеме


def _home(query="", owner=False, **site):
    req = _req("/" + query)
    req.tenant.site_config = {"sections": SECTIONS, **site}
    req.user = (owner if owner is not True else _owner()) if owner else AnonymousUser()
    return public_views.storefront_home(req).content.decode()


def test_empty_site_in_the_design_preview_gets_samples_everywhere():
    html = _home(DESIGN)
    for key in ("faq", "gallery", "team", "promotions"):
        assert f'data-sample-section="{key}"' in html, key
    assert "data-sample-hero" in html, "баннер с фото-примером"


def test_samples_are_marked_inert_and_carry_no_structured_data():
    html = _home(DESIGN)
    assert html.count("data-sample-note") >= 4
    faq = html[html.index('data-sample-section="faq"') - 400 :]
    assert "FAQPage" not in faq[:3000], "вопросы-примеры не уходят в поисковики"


def test_fake_reviews_only_for_the_owner():
    assert 'data-sample-section="testimonials"' not in _home(DESIGN)
    assert 'data-sample-section="testimonials"' in _home(DESIGN, owner=True)


def test_live_site_and_plain_preview_show_no_samples():
    for query in ("", "?preview=1"):
        html = _home(query)
        assert "data-sample-section" not in html and "data-sample-hero" not in html, query


def test_own_content_is_never_replaced():
    html = _home(DESIGN, faq=[{"q": "Echte Frage?", "a": "Echte Antwort."}])
    assert "Echte Frage?" in html and 'data-sample-section="faq"' not in html


def test_samples_write_nothing():
    owner = _owner()
    with CaptureQueriesContext(connection) as ctx:
        _home(DESIGN, owner=owner)
    writes = [q["sql"] for q in ctx.captured_queries
              if q["sql"].split(" ", 1)[0].upper() in ("INSERT", "UPDATE", "DELETE")]  # fmt: skip
    assert writes == []


def test_site_with_samples_keeps_the_original_untouched():
    site = {"faq": [], "gallery": [], "sections": SECTIONS}
    req = _req("/" + DESIGN)
    req.user = AnonymousUser()
    out, keys = design_samples.site_with_samples(site, req)
    assert site["faq"] == [] and out["faq"] and "faq" in keys


def test_price_list_style_shows_the_sample_products_too():
    """Стенд пекарни: вид «прайс-лист» в предпросмотре был пустым — запрос к базе."""
    rows = [{"key": "products", "enabled": True, "style": "preisliste"}]
    req = _req("/" + DESIGN)
    req.user = AnonymousUser()
    req.tenant.site_config = {"sections": rows}
    html = public_views.storefront_home(req).content.decode()
    assert "data-sample-products" in html
    assert design_samples.products()[0].name["de"] in html
