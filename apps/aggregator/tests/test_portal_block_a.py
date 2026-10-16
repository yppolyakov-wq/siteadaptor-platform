"""Блок А фидбэка портала (план docs/backlog-portal-direction-2026-10-16.md §1).

А1 тексты · А2 чипы несут поиск · А3 «Für Unternehmen» · А4 профиль компании ·
А6 подложка карты. Замки написаны ДО кода.
"""

import uuid
from pathlib import Path

import pytest
from django.conf import settings
from django.core.cache import cache
from django.http import Http404
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from django.utils import translation

from apps.aggregator import portal_views, reviews_views, views
from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_HOST = "solingen.siteadaptor.de"


@pytest.fixture(autouse=True)
def _clear():
    cache.clear()
    yield
    cache.clear()


def _portal(**kw):
    defaults = {
        "host": _HOST,
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
        "tenant_slug": "brot",
        "business_name": "Brot & Co",
        "business_type": "bakery",
        "city": "Solingen",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Brotkorb"},
        "detail_url": "https://brot.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _get(portal, path="/"):
    req = RequestFactory().get(path, HTTP_HOST=_HOST)
    req.portal = portal
    return req


# --- А1: тексты ------------------------------------------------------------------


def _card_html(lang, **attrs):
    lst = _listing(**attrs.pop("listing", {}))
    for k, v in attrs.items():
        setattr(lst, k, v)
    with translation.override(lang):
        return render_to_string("aggregator/_cards.html", {"items": [lst]})


@pytest.mark.parametrize(
    "lang, expected, wrong",
    [("de", "Geöffnet bis 18:00", "Öffnen"), ("ru", "Открыто до 18:00", "Открыть")],
)
def test_open_status_reads_as_state_not_as_button(lang, expected, wrong):
    html = _card_html(lang, has_hours=True, open_now=True, open_until="18:00")
    assert expected in html
    assert wrong not in html


def test_open_status_without_until_is_a_state():
    html = _card_html("de", has_hours=True, open_now=True, open_until="")
    assert "Jetzt geöffnet" in html and "Öffnen" not in html


def test_new_badge_means_new_in_store_singular():
    html = _card_html("ru", listing={"listing_kind": "product"}, is_new=True)
    assert "Новинка" in html and "Новые" not in html
    html = _card_html("de", listing={"listing_kind": "product"}, is_new=True)
    assert "Neu im Sortiment" in html


def test_open_button_elsewhere_keeps_its_meaning():
    """«Open» как кнопка (скан, штампы) по-прежнему «Öffnen» — меняется только статус."""
    with translation.override("de"):
        assert translation.gettext("Open") == "Öffnen"


def test_cart_is_basket_in_russian():
    with translation.override("ru"):
        assert translation.gettext("Cart") == "Корзина"


# --- А2: чипы района/отрасли несут поиск и фильтры --------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_district_and_industry_chips_carry_query_and_filters():
    p = _portal()
    _listing(district="wald", title={"de": "Brot im Wald"}, new_price="3.00")
    _listing(district="mitte", title={"de": "Brot in Mitte"}, new_price="3.00")
    req = _get(p, "/stadtteil/wald/?q=Brot&sort=endet&preis_bis=10&cursor=abc")
    html = portal_views.portal_home(req, district="wald").content.decode()
    chips = html[html.index("data-district-chips") :]
    chips = chips[: chips.index("</nav>")]
    assert 'href="/stadtteil/mitte/?' in chips
    for frag in ("q=Brot", "sort=endet", "preis_bis=10"):
        assert frag in chips
    assert "cursor=" not in chips and "stadtteil=" not in chips
    # «Alle» тоже не сбрасывает поиск
    assert 'href="/?q=Brot' in chips


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_chips_drop_stadtteil_filter_param_on_root():
    p = _portal()
    _listing(district="wald")
    _listing(district="mitte")
    html = portal_views.portal_home(_get(p, "/?q=Brot&stadtteil=mitte")).content.decode()
    chips = html[html.index("data-district-chips") :]
    chips = chips[: chips.index("</nav>")]
    assert "q=Brot" in chips and "stadtteil=" not in chips


# --- А3: «Für Unternehmen» --------------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal", TENANT_DOMAIN_BASE="siteadaptor.de")
def test_for_business_link_in_header_and_page_ctas_to_quick_start():
    p = _portal()
    html = portal_views.portal_home(_get(p)).content.decode()
    assert html.count('href="/fuer-unternehmen/"') >= 2  # шапка + подвал
    resp = portal_views.for_business(_get(p, "/fuer-unternehmen/"))
    body = resp.content.decode()
    assert resp.status_code == 200
    assert "/aktion-starten/" in body
    assert str(settings.LITE_FREE_ACTIVE_PROMOS) in body


def test_for_business_route_is_before_facet_catch_all():
    from django.urls import resolve

    match = resolve("/fuer-unternehmen/", urlconf="config.urls_portal")
    assert match.url_name == "portal-for-business"


# --- А4: профиль компании ---------------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_business_card_links_to_business_page_and_old_url_redirects():
    p = _portal()
    TenantFactory(schema_name="t1", slug="brot", name="Brot & Co", city="Solingen")
    biz = _listing(listing_kind="business", promo_uuid=None, source_ref="biz")
    html = render_to_string("aggregator/_cards.html", {"items": [biz]})
    assert 'href="/unternehmen/brot/"' in html
    resp = views.offer_page(_get(p, f"/angebot/{biz.pk}/"), biz.pk)
    assert resp.status_code == 301 and resp["Location"] == "/unternehmen/brot/"
    resp = views.offer_page(_get(p, f"/angebot/{biz.pk}/?ch=feed"), biz.pk)
    assert resp["Location"] == "/unternehmen/brot/?ch=feed"  # атрибуция канала цела
    promo = _listing()
    assert views.offer_page(_get(p, f"/angebot/{promo.pk}/"), promo.pk).status_code == 200


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_business_page_has_website_and_excludes_itself_from_offers():
    p = _portal()
    TenantFactory(
        schema_name="t1",
        slug="brot",
        name="Brot & Co",
        city="Solingen",
        opening_hours="Mo–Fr 7–18 Uhr",
    )
    _listing(
        listing_kind="business",
        promo_uuid=None,
        source_ref="biz",
        title={"de": "Brot & Co Firmenkarte"},
        teaser={"de": "Handwerksbäckerei seit 1950"},
        detail_url="https://brot.siteadaptor.de/",
    )
    _listing(title={"de": "Brotkorb"})
    html = reviews_views.business_page(_get(p, "/unternehmen/brot/"), "brot").content.decode()
    assert "Firmenkarte" not in html  # компания не среди своих предложений
    assert "Brotkorb" in html
    assert "https://brot.siteadaptor.de/?ch=portal&amp;hl=de" in html  # «Zur Website» (+Б4 язык)
    assert "Handwerksbäckerei seit 1950" in html
    assert "Mo–Fr 7–18 Uhr" in html
    assert "application/ld+json" in html  # LocalBusiness-разметка (тип уточняется по виду бизнеса)


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_business_redirect_respects_scope():
    p = _portal(city="Wuppertal", host="wuppertal.siteadaptor.de")
    biz = _listing(listing_kind="business", promo_uuid=None, source_ref="biz")
    with pytest.raises(Http404):
        views.offer_page(_get(p, f"/angebot/{biz.pk}/"), biz.pk)


# --- А6: подложка карты -----------------------------------------------------------


@pytest.mark.parametrize(
    "tpl",
    ["templates/aggregator/_map.html", "templates/storefront/sections/_contact_map.html"],
)
def test_map_uses_current_osm_host_and_handles_tile_errors(tpl):
    src = (Path(settings.BASE_DIR) / tpl).read_text()
    assert "{s}.tile.openstreetmap.org" not in src
    assert "tile.openstreetmap.org" in src
    if tpl.startswith("templates/aggregator/"):
        assert "tileerror" in src and "Karte nicht verfügbar" in src


def test_with_channel_refuses_non_http_urls():
    lst = AggregatorListing(detail_url="javascript:alert(1)")
    assert lst.portal_url == ""
    assert (
        AggregatorListing(detail_url="https://x.de/p/1/").with_channel("portal")
        == "https://x.de/p/1/?ch=portal"
    )


# --- Е1: прошедшее событие без ends_at не видно НИГДЕ (правило в public()) ----------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_past_event_without_end_is_gone_from_every_public_path():
    from datetime import timedelta

    from django.utils import timezone

    p = _portal()
    TenantFactory(schema_name="t1", slug="brot", name="Brot & Co", city="Solingen")
    past = _listing(
        listing_kind="event",
        promo_uuid=None,
        source_ref="e1",
        title={"de": "Vorbei-Konzert"},
        starts_at=timezone.now() - timedelta(days=1),
    )
    promo = _listing(title={"de": "Laufende Aktion"}, starts_at=timezone.now() - timedelta(days=1))
    public = AggregatorListing.objects.public()
    assert not public.filter(pk=past.pk).exists()
    assert public.filter(pk=promo.pk).exists()  # у акции starts_at — начало окна
    html = reviews_views.business_page(_get(p, "/unternehmen/brot/"), "brot").content.decode()
    assert "Vorbei-Konzert" not in html and "Laufende Aktion" in html
    with pytest.raises(Http404):
        views.offer_page(_get(p, f"/angebot/{past.pk}/"), past.pk)
