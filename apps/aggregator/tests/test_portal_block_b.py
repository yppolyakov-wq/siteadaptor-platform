"""Блок Б фидбэка портала (план docs/backlog-portal-direction-2026-10-16.md §2).

Б1 результаты выше · Б2 Liste/Karte. Замки написаны ДО кода.
"""

import uuid

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings

from apps.aggregator import portal_views, views
from apps.aggregator.models import AggregatorListing, AggregatorPortal

pytestmark = pytest.mark.django_db

_HOST = "solingen.siteadaptor.de"


@pytest.fixture(autouse=True)
def _clear(isolated_ratelimit):
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
        "tenant_slug": "x",
        "business_name": "X",
        "business_type": "bakery",
        "city": "Solingen",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Brot"},
        "detail_url": "https://x.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _html(portal, path="/", **kw):
    req = RequestFactory().get(path, HTTP_HOST=_HOST)
    req.portal = portal
    return portal_views.portal_home(req, **kw).content.decode()


def _seed():
    _listing(title={"de": "Pizza Margherita"}, district="wald", business_type="restaurant")
    _listing(title={"de": "Reifenwechsel"}, district="mitte", business_type="kfz")
    _listing(title={"de": "Brot"}, district="graefrath", business_type="bakery")


# --- Б1: при поиске — сначала результаты, уточнение свёрнуто, чипы по найденному -----


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_search_shows_hit_count_and_collapses_refinement():
    p = _portal()
    _seed()
    html = _html(p, "/?q=Pizza")
    assert "data-hit-count" in html
    assert "1 Treffer" in html
    refine = html.index("data-portal-refine")
    assert html.index("data-district-chips") > refine  # районы — внутри свёрнутого блока
    assert html.rindex("Pizza Margherita") > refine  # карточка (в <head> — JSON-LD)


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_search_chips_are_built_from_found_pool():
    p = _portal()
    _seed()
    html = _html(p, "/?q=Pizza")
    chips = html[html.index("data-district-chips") : html.index("data-district-chips") + 3000]
    assert "/stadtteil/wald/" in chips
    assert "/stadtteil/mitte/" not in chips  # в Mitte пиццы нет — мёртвый чип не нужен


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_without_search_layout_is_unchanged():
    p = _portal()
    _seed()
    html = _html(p, "/stadtteil/wald/", district="wald")
    assert "data-portal-refine" not in html
    assert "data-hit-count" not in html
    # без поиска районы — над формой поиска, как раньше
    assert html.index("data-district-chips") < html.index('name="q"')


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_search_with_district_keeps_all_district_chips():
    p = _portal()
    _seed()
    html = _html(p, "/stadtteil/wald/?q=Pizza", district="wald")
    assert "/stadtteil/mitte/" in html  # переключение района при поиске не теряется


# --- Б2: список по умолчанию, карта по кнопке, Leaflet лениво -----------------------


def _with_coords(**kw):
    return _listing(latitude=51.17, longitude=7.08, **kw)


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_map_is_hidden_by_default_and_leaflet_not_loaded():
    p = _portal()
    _with_coords(district="wald")
    html = _html(p, "/stadtteil/wald/", district="wald")
    assert 'src="https://unpkg.com/leaflet' not in html  # Leaflet грузится только по клику
    assert 'id="agg-map-data"' in html
    assert "data-map-toggle" in html
    assert "data-map-open" not in html


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_map_opens_with_ansicht_karte_and_keeps_query():
    p = _portal()
    _with_coords(district="wald", title={"de": "Pizza"})
    html = _html(p, "/stadtteil/wald/?q=Pizza&ansicht=karte", district="wald")
    assert "data-map-open" in html
    # ссылка «Liste» сохраняет запрос и убирает вид
    assert 'href="?q=Pizza"' in html


@override_settings(ROOT_URLCONF="config.urls_public")
def test_entdecken_city_page_also_lists_first():
    _with_coords(city="Solingen")
    req = RequestFactory().get("/entdecken/solingen/")
    html = views.city_listing(req, "Solingen").content.decode()
    assert 'src="https://unpkg.com/leaflet' not in html
    assert "data-map-toggle" in html


# --- Б3: «Ähnliches» — тот же вид и категория по городу, ближайшие первыми ----------


def _offer_html(portal, listing):
    req = RequestFactory().get(f"/angebot/{listing.pk}/", HTTP_HOST=_HOST)
    req.portal = portal
    return views.offer_page(req, listing.pk).content.decode()


def _section(html, marker):
    if marker not in html:
        return ""
    part = html.split(marker, 1)[1]
    return part.split("</section>", 1)[0]


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_similar_is_same_kind_and_category_not_same_district():
    p = _portal()
    phone = _listing(
        listing_kind="product",
        promo_uuid=None,
        source_ref="iphone",
        title={"de": "iPhone refurbished"},
        city_category="smartphones",
        district="wald",
        latitude=51.170,
        longitude=7.080,
    )
    _listing(
        tenant_schema="t2",
        listing_kind="product",
        promo_uuid=None,
        source_ref="kerzen",
        title={"de": "Kerzen-Set"},
        city_category="dekoration",
        district="wald",
    )
    _listing(
        tenant_schema="t3",
        listing_kind="product",
        promo_uuid=None,
        source_ref="far",
        title={"de": "Smartphone weit"},
        city_category="smartphones",
        district="mitte",
        latitude=51.300,
        longitude=7.200,
    )
    _listing(
        tenant_schema="t4",
        listing_kind="product",
        promo_uuid=None,
        source_ref="near",
        title={"de": "Smartphone nah"},
        city_category="smartphones",
        district="mitte",
        latitude=51.171,
        longitude=7.081,
    )
    html = _offer_html(p, phone)
    similar = _section(html, "data-offer-similar")
    assert "Kerzen-Set" not in similar  # тот же район, но чужая категория
    assert similar.index("Smartphone nah") < similar.index("Smartphone weit")
    near = _section(html, "data-offer-nearby")
    assert "Kerzen-Set" in near  # соседи по месту — отдельным блоком
    assert "Smartphone nah" not in near  # уже показан в «Ähnliches»


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_no_similar_block_without_matches():
    p = _portal()
    lone = _listing(city_category="smartphones", district="wald")
    _listing(tenant_schema="t2", title={"de": "Kerzen"}, city_category="dekoration")
    html = _offer_html(p, lone)
    assert "data-offer-similar" not in html


# --- Б4: язык портала едет на сайт продавца ------------------------------------------


def test_portal_url_carries_portal_language_but_feed_does_not():
    from django.utils import translation

    lst = AggregatorListing(detail_url="https://brot.siteadaptor.de/p/1/")
    with translation.override("ru"):
        assert lst.portal_url == "https://brot.siteadaptor.de/p/1/?ch=portal&hl=ru"
    assert "hl=" not in lst.with_channel("feed")


def _storefront_get(path, tenant):
    from apps.core.middleware import StorefrontLocaleClampMiddleware

    seen = {}

    def view(request):
        from django.http import HttpResponse
        from django.utils import translation

        seen["lang"] = translation.get_language()
        return HttpResponse("ok")

    req = RequestFactory().get(path)
    req.tenant = tenant
    return StorefrontLocaleClampMiddleware(view)(req), seen


def test_storefront_accepts_hl_only_from_enabled_locales():
    from types import SimpleNamespace

    from django.conf import settings
    from django.utils import translation

    tenant = SimpleNamespace(schema_name="t1", active_locales=["de", "en"], default_locale="de")
    with translation.override("de"):
        resp, seen = _storefront_get("/p/1/?hl=en", tenant)
        assert seen["lang"] == "en"
        assert resp.cookies[settings.LANGUAGE_COOKIE_NAME].value == "en"
    with translation.override("de"):
        resp, seen = _storefront_get("/p/1/?hl=ru", tenant)  # у бизнеса нет русского
        assert seen["lang"] == "de"
        assert settings.LANGUAGE_COOKIE_NAME not in resp.cookies


# --- Б5: позиции фирмы, найденные только по её имени, — группой «Von <Firma>» ----------


def _pizzabote():
    common = {"tenant_schema": "pb", "tenant_slug": "pizzabote", "business_name": "Pizzabote Wald"}
    _listing(
        **common,
        listing_kind="business",
        promo_uuid=None,
        source_ref="biz",
        title={"de": "Pizzabote Wald"},
    )
    _listing(**common, title={"de": "Caesar Salat"})
    _listing(**common, title={"de": "Pasta Arrabbiata"})
    _listing(**common, title={"de": "Pizza Funghi"})
    _listing(
        tenant_schema="other",
        tenant_slug="o",
        business_name="Trattoria",
        title={"de": "Salat Caprese"},
    )


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_firm_name_query_groups_items_matched_only_by_name():
    p = _portal()
    _pizzabote()
    html = _html(p, "/?q=Pizzabote")
    group = html.split("data-firm-group", 1)[1].split("</section>", 1)[0]
    assert "Caesar Salat" in group and "Pasta Arrabbiata" in group
    main = html.split("data-firm-group", 1)[1].split("</section>", 1)[1]  # лента после группы
    assert "Caesar Salat" not in main and "Pasta Arrabbiata" not in main
    assert "Pizzabote Wald" in main  # карточка самой фирмы — в выдаче
    assert "/unternehmen/pizzabote/" in group  # «Alle Angebote von …»


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_plain_word_query_keeps_firm_items_in_main_feed():
    p = _portal()
    _pizzabote()
    html = _html(p, "/?q=Salat")
    assert "data-firm-group" not in html
    assert "Caesar Salat" in html and "Salat Caprese" in html


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_umlaut_title_hit_stays_in_main_feed():
    """django-ревью: свёрнутое слово запроса не совпадало с заголовком «Müller …»."""
    p = _portal()
    common = {"tenant_schema": "mu", "tenant_slug": "mueller", "business_name": "Bäckerei Müller"}
    _listing(**common, title={"de": "Müller Brot"})
    _listing(**common, title={"de": "Croissant"})
    html = _html(p, "/?q=Müller")
    group = html.split("data-firm-group", 1)[1].split("</section>", 1)[0]
    assert "Croissant" in group and "Müller Brot" not in group


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_generic_word_matching_several_firms_does_not_group():
    """django-ревью: «Pizza» в именах двух пиццерий — выдача не трогается."""
    p = _portal()
    _listing(
        tenant_schema="a", tenant_slug="a", business_name="Pizza Roma", title={"de": "Tiramisu"}
    )
    _listing(
        tenant_schema="b", tenant_slug="b", business_name="Pizza Napoli", title={"de": "Lasagne"}
    )
    html = _html(p, "/?q=Pizza")
    assert "data-firm-group" not in html
    assert "Tiramisu" in html and "Lasagne" in html


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_firm_group_counted_in_hits_and_only_on_first_page():
    p = _portal()
    _pizzabote()
    html = _html(p, "/?q=Pizzabote")
    assert "4 Treffer" in html  # фирма + 3 позиции группы
    assert "data-firm-group" not in _html(p, "/?q=Pizzabote&cursor=24")
