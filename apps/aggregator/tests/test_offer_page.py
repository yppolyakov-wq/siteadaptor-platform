"""T-8.24: страница предложения внутри портала (план t8-24-portal-offer-page-plan-2026-10-11)."""

import uuid

import pytest
from django.core.cache import cache
from django.http import Http404
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.aggregator import views
from apps.aggregator.models import AggregatorListing, AggregatorPortal

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear():
    cache.clear()
    yield
    cache.clear()


def _portal(**kw):
    defaults = {
        "host": "solingen.siteadaptor.de",
        "kind": "city",
        "city": "Solingen",
        "title": {"de": "Angebote in Solingen"},
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorPortal.objects.create(**defaults)


def _listing(**kw):
    defaults = {
        "tenant_schema": "t1",
        "tenant_slug": "baeckerei",
        "business_name": "Bäckerei Klinge",
        "business_type": "bakery",
        "city": "Solingen",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Brotkorb"},
        "teaser": {"de": "Frisch vom Morgen"},
        "new_price": "4.50",
        "old_price": "6.00",
        "detail_url": "https://baeckerei.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _get(path="/angebot/1/", portal=None):
    req = RequestFactory().get(path)
    if portal is not None:
        req.portal = portal
    return req


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_offer_page_renders_with_cta_canonical_and_jsonld():
    portal = _portal()
    listing = _listing()
    resp = views.offer_page(_get(portal=portal), listing.pk)
    html = resp.content.decode()
    assert resp.status_code == 200
    assert "Brotkorb" in html and "Frisch vom Morgen" in html
    # Кнопка ведёт на сайт бизнеса с атрибуцией портала.
    assert 'href="https://baeckerei.siteadaptor.de/p/1/?ch=portal" data-offer-cta' in html
    # Стратегия А: canonical — страница бизнеса.
    assert '<link rel="canonical" href="https://baeckerei.siteadaptor.de/p/1/">' in html
    assert '"@type":"Offer"' in html and '"price":"4.50"' in html


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_offer_page_404_when_hidden_suspended_or_outside_portal():
    portal = _portal()
    hidden = _listing(hidden_at=timezone.now())
    other_city = _listing(city="Hilden", tenant_schema="t2")
    demo = _listing(is_demo=True, tenant_schema="t3")
    for item in (hidden, other_city, demo):
        with pytest.raises(Http404):
            views.offer_page(_get(portal=portal), item.pk)
    with pytest.raises(Http404):
        views.offer_page(_get(portal=portal), 999999)
    # Демо открывается порталом-превью (show_demo).
    preview = _portal(host="preview.siteadaptor.de", show_demo=True)
    assert views.offer_page(_get(portal=preview), demo.pk).status_code == 200


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_more_and_similar_strips_exclude_the_offer_itself():
    portal = _portal()
    listing = _listing(district="wald", city_category="lebensmittel")
    same_biz = _listing(title={"de": "Brezel"})
    neighbour = _listing(
        tenant_schema="t2",
        tenant_slug="cafe",
        business_name="Café Wald",
        title={"de": "Kuchen"},
        district="wald",
        city_category="lebensmittel",
    )
    resp = views.offer_page(_get(portal=portal), listing.pk)
    ctx_html = resp.content.decode()
    more = ctx_html.split("data-offer-more", 1)[1].split("data-offer-similar", 1)[0]
    similar = ctx_html.split("data-offer-similar", 1)[1]
    assert "Brezel" in more and "Brotkorb" not in more
    assert "Kuchen" in similar and "Brotkorb" not in similar and "Brezel" not in similar
    assert same_biz.pk and neighbour.pk


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_feed_cards_link_to_offer_page():
    listing = _listing()
    html = render_to_string("aggregator/_cards.html", {"items": [listing]})
    assert f'href="/angebot/{listing.pk}/"' in html


@override_settings(ROOT_URLCONF="config.urls_public")
def test_offer_page_on_main_domain():
    listing = _listing()
    resp = views.offer_page(_get(f"/entdecken/angebot/{listing.pk}/"), listing.pk)
    assert resp.status_code == 200
    html = render_to_string("aggregator/_cards.html", {"items": [listing]})
    assert f'href="/entdecken/angebot/{listing.pk}/"' in html


def test_feed_cards_fall_back_to_business_site_without_route():
    # Тенантный urlconf (роута нет) — карточка ведёт на сайт бизнеса, как раньше.
    listing = _listing()
    html = render_to_string("aggregator/_cards.html", {"items": [listing]})
    assert listing.portal_url in html
