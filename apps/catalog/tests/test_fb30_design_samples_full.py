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
    html = _home(DESIGN, owner=True)
    for key in ("faq", "gallery", "team", "promotions"):
        assert f'data-sample-section="{key}"' in html, key
    assert "data-sample-hero" in html, "баннер с фото-примером"


def test_samples_are_marked_inert_and_carry_no_structured_data():
    html = _home(DESIGN, owner=True)
    assert html.count("data-sample-note") >= 4
    assert "FAQPage" not in html, "вопросы-примеры не уходят в поисковики"
    hero = html[html.index("data-sample-hero") :][:3000]
    assert 'data-edit="hero_text"' not in hero, "текст-пример не правится как настоящий"


def test_invented_content_only_for_the_owner():
    """Ревью: `?preview=1&look=` открыт любому посетителю — выдуманные отзывы, вопросы,
    команда, текст баннера и акции с ценой «statt» видит только владелец."""
    public = _home(DESIGN)
    for key in ("testimonials", "faq", "team", "gallery", "promotions"):
        assert f'data-sample-section="{key}"' not in public, key
    assert "data-sample-hero" not in public and "data-sample-promotions" not in public
    owner = _home(DESIGN, owner=True)
    assert 'data-sample-section="testimonials"' in owner


def test_design_preview_is_not_indexed_or_cached():
    from django.contrib.auth.models import AnonymousUser as Anon

    req = _req("/" + DESIGN)
    req.user = Anon()
    req.tenant.site_config = {"sections": SECTIONS}
    resp = public_views.storefront_home(req)
    assert resp["X-Robots-Tag"].startswith("noindex")
    assert "no-store" in resp["Cache-Control"]
    plain = _req("/")
    plain.user = Anon()
    plain.tenant.site_config = {"sections": SECTIONS}
    assert "X-Robots-Tag" not in public_views.storefront_home(plain)


def test_member_of_another_business_is_not_the_owner():
    from django.contrib.auth import get_user_model

    stranger = get_user_model().objects.create_user(username="fremd-fb30", password="pw1234567")
    assert 'data-sample-section="testimonials"' not in _home(DESIGN, owner=stranger)


def test_picked_banner_gets_no_hero_sample():
    from apps.core import banners

    b = banners.create({"title": "Echt", "image": {"url": "/media/hero/a.jpg"}})
    html = _home(DESIGN, owner=True, hero_banners={"pick": [str(b.pk)]})
    assert "data-sample-hero" not in html


def test_live_site_and_plain_preview_show_no_samples():
    for query in ("", "?preview=1"):
        html = _home(query)
        assert "data-sample-section" not in html and "data-sample-hero" not in html, query


def test_own_content_is_never_replaced():
    html = _home(DESIGN, owner=True, faq=[{"q": "Echte Frage?", "a": "Echte Antwort."}])
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
    req.user = _owner()
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


# --- часть 2: страница товара-примера и переключатель страниц предпросмотра ---


def _detail(pk, query="", user=True):
    req = _req(f"/sortiment/{pk}/{query}")
    req.user = (_owner() if user is True else user) if user else AnonymousUser()
    return public_views.product_detail(req, pk=pk)


def test_sample_product_page_opens_only_in_the_design_preview_of_an_empty_shop():
    import uuid

    from django.http import Http404

    from apps.catalog.tests.factories import ProductFactory

    sample = design_samples.products()[0]
    resp = _detail(sample.pk, DESIGN)
    html = resp.content.decode()
    assert resp.status_code == 200 and sample.name["de"] in html
    assert "data-sample-product" in html and " inert" in html, "покупка неактивна"
    assert resp["X-Robots-Tag"].startswith("noindex")
    with pytest.raises(Http404):
        _detail(sample.pk, user=None)  # без предпросмотра — нет
    with pytest.raises(Http404):
        _detail(sample.pk, DESIGN, user=None)  # посторонний — нет (выдуманная цена)
    with pytest.raises(Http404):
        _detail(uuid.UUID(int=99), DESIGN, user=None)  # не пример
    ProductFactory(name={"de": "Echter Tee", "en": ""}, base_price="3.00")
    with pytest.raises(Http404):
        _detail(sample.pk, DESIGN, user=None)  # свои товары есть — примеров нет


def test_sample_product_page_writes_nothing():
    sample = design_samples.products()[0]
    owner = _owner()
    with CaptureQueriesContext(connection) as ctx:
        _detail(sample.pk, DESIGN, user=owner)
    writes = [q["sql"] for q in ctx.captured_queries
              if q["sql"].split(" ", 1)[0].upper() in ("INSERT", "UPDATE", "DELETE")]  # fmt: skip
    assert writes == []


def test_preview_pages_offer_home_listing_and_product():
    from apps.core.modules import default_disabled_for

    req = _req("/")
    req.tenant.business_type = "online_shop"
    req.tenant.disabled_modules = list(default_disabled_for("online_shop"))
    pages = design_samples.preview_pages(req, "?preview=1&look=klar&bundle=fokus")
    assert [p["key"] for p in pages] == ["home", "liste", "produkt"]
    assert pages[0]["url"].startswith("/?preview=1")
    assert pages[1]["url"].startswith("/sortiment/?preview=1")
    sample = design_samples.products()[0]
    assert pages[2]["url"].startswith(f"/sortiment/{sample.pk}/?preview=1")


def test_preview_pages_of_a_salon_show_its_booking_list_and_no_product_page():
    from apps.core.modules import default_disabled_for

    req = _req("/")
    req.tenant.business_type = "friseur"
    req.tenant.disabled_modules = list(default_disabled_for("friseur"))
    pages = design_samples.preview_pages(req, "?preview=1")
    assert [p["key"] for p in pages] == ["home", "liste"]
    assert pages[1]["url"].startswith("/termin/")
