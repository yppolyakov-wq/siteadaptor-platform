"""T-8.8: машиночитаемость каталога города — JSON-LD по видам, sitemap, robots,
llms.txt, открытый фид (план docs/t8-8-machine-readable-plan-2026-10-15.md §4).
Паттерн test_portal_seo.py: RequestFactory + request.portal + ROOT_URLCONF портала."""

import json
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, timedelta

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.aggregator import open_feed, portal_views, tasks, views
from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_HOST = "solingen.siteadaptor.de"
_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


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
        "title": {"de": "Entdecke Solingen"},
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
        "listing_kind": "promotion",
        "source_ref": str(uuid.uuid4()),
        "title": {"de": "Brotkorb"},
        "teaser": {"de": "Frisch vom Morgen"},
        "new_price": "4.50",
        "old_price": "6.00",
        "currency": "EUR",
        "city_category": "brot-backwaren",
        "detail_url": "https://baeckerei.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _get(path="/", portal=None, **extra):
    req = RequestFactory().get(path, HTTP_HOST=_HOST, **extra)
    req.portal = portal
    return req


def _ld(html: str) -> dict:
    blocks = [json.loads(m) for m in _LD_RE.findall(html)]
    offer = [b for b in blocks if b.get("@type") != "CollectionPage"]
    assert offer, "нет JSON-LD предложения"
    return offer[0]


# --- JSON-LD страницы предложения -----------------------------------------------


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("promotion", "Product"),
        ("product", "Product"),
        ("menu", "Product"),
        ("stay", "HotelRoom"),
        ("service", "Service"),
        ("event", "Event"),
        ("business", "LocalBusiness"),
    ],
)
@override_settings(ROOT_URLCONF="config.urls_portal")
def test_jsonld_type_per_kind(kind, expected):
    portal = _portal()
    now = timezone.now()
    lst = _listing(listing_kind=kind, starts_at=now, ends_at=now + timedelta(days=2))
    html = views.offer_page(_get(portal=portal), lst.pk).content.decode()
    ld = _ld(html)
    assert ld["@type"] == expected
    assert ld["url"] == "https://baeckerei.siteadaptor.de/p/1/"


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_event_has_start_and_location_city():
    portal = _portal()
    now = timezone.now()
    lst = _listing(listing_kind="event", starts_at=now, district="graefrath")
    ld = _ld(views.offer_page(_get(portal=portal), lst.pk).content.decode())
    assert ld["startDate"].startswith(now.date().isoformat())
    assert ld["location"]["address"]["addressLocality"] == "Solingen"
    assert ld["eventStatus"].endswith("EventScheduled")


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_stay_offer_has_unit_price_per_day():
    portal = _portal()
    lst = _listing(listing_kind="stay", new_price="89.00")
    ld = _ld(views.offer_page(_get(portal=portal), lst.pk).content.decode())
    assert ld["offers"]["priceSpecification"]["unitCode"] == "DAY"
    assert ld["containedInPlace"]["@type"] == "LodgingBusiness"


@pytest.mark.parametrize(
    "kind,avail,expected",
    [
        ("product", "sold_out", "https://schema.org/SoldOut"),
        ("product", "on_request", "https://schema.org/MadeToOrder"),
        ("product", "", "https://schema.org/InStock"),
        ("promotion", "", "https://schema.org/InStock"),
        ("stay", "", None),
        ("service", "", None),
    ],
)
@override_settings(ROOT_URLCONF="config.urls_portal")
def test_availability_mapping(kind, avail, expected):
    portal = _portal()
    lst = _listing(listing_kind=kind, availability=avail)
    ld = _ld(views.offer_page(_get(portal=portal), lst.pk).content.decode())
    assert ld["offers"].get("availability") == expected


@override_settings(ROOT_URLCONF="config.urls_portal", TIME_ZONE="Europe/Berlin")
def test_price_valid_until_is_local_date():
    portal = _portal()
    from datetime import datetime

    ends = datetime(2026, 10, 20, 23, 30, tzinfo=UTC)  # 21.10 в Берлине
    lst = _listing(ends_at=ends)
    ld = _ld(views.offer_page(_get(portal=portal), lst.pk).content.decode())
    assert ld["offers"]["priceValidUntil"] == "2026-10-21"


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_seller_is_full_localbusiness_without_private_data():
    portal = _portal()
    TenantFactory(
        schema_name="t1",
        slug="baeckerei",
        name="Bäckerei Klinge",
        city="Solingen",
        address="Hauptstr. 1",
        contact_phone="+49 212 123456",
        contact_email="owner-secret@example.com",
    )
    lst = _listing()
    html = views.offer_page(_get(portal=portal), lst.pk).content.decode()
    ld = _ld(html)
    seller = ld["offers"]["seller"]
    assert seller["address"]["streetAddress"] == "Hauptstr. 1"
    assert "owner-secret@example.com" not in html


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_orphan_listing_falls_back_to_minimal_seller():
    portal = _portal()
    lst = _listing(tenant_schema="ghost")
    ld = _ld(views.offer_page(_get(portal=portal), lst.pk).content.decode())
    assert ld["offers"]["seller"] == {
        "@type": "LocalBusiness",
        "name": "Bäckerei Klinge",
        "address": {"@type": "PostalAddress", "addressLocality": "Solingen"},
    }


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_old_price_never_in_jsonld_and_featured_identical():
    portal = _portal()
    plain = _listing()
    featured = _listing(
        source_ref="f", featured_until=timezone.now() + timedelta(days=1), tenant_slug="b2"
    )
    html_plain = views.offer_page(_get(portal=portal), plain.pk).content.decode()
    html_feat = views.offer_page(_get(portal=portal), featured.pk).content.decode()
    ld_plain, ld_feat = _ld(html_plain), _ld(html_feat)
    assert "6.00" not in json.dumps(ld_plain)
    assert ld_plain["offers"] == ld_feat["offers"]
    assert "sponsored" not in json.dumps(ld_feat)


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_mystery_listing_has_no_offer_and_no_price_in_html():
    portal = _portal()
    lst = _listing(new_price=None, old_price=None, discount_percent=None)
    html = views.offer_page(_get(portal=portal), lst.pk).content.decode()
    assert "offers" not in _ld(html)
    assert "4,50" not in html and "6,00" not in html


def test_sync_strips_price_of_mystery_promotion():
    TenantFactory(schema_name="public", slug="x", name="X", city="Solingen")
    promo = Promotion.objects.create(
        status="active",
        title={"de": "Mystery"},
        compare_at_price="10.00",
        discount_percent=50,
        discount_style="mystery",
    )
    assert tasks.sync_listing("public", str(promo.id)) == "upserted"
    lst = AggregatorListing.objects.get(promo_uuid=promo.id)
    assert lst.new_price is None and lst.old_price is None and lst.discount_percent is None


def test_localbusiness_ld_parity_with_data():
    from apps.core.seo import _dumps, localbusiness_data, localbusiness_ld

    t = TenantFactory(schema_name="p1", slug="p1", name="P", city="Solingen", address="A 1")
    assert localbusiness_ld(t, url="https://p1.example/") == _dumps(
        localbusiness_data(t, url="https://p1.example/")
    )
    assert localbusiness_ld(None, url="x") == "" and localbusiness_data(None, url="x") == {}


# --- sitemap / robots -----------------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_sitemap_has_businesses_with_lastmod_but_no_offers_or_hidden():
    portal = _portal()
    _listing(tenant_slug="baeckerei", district="graefrath")
    _listing(tenant_slug="hidden-biz", source_ref="h", hidden_at=timezone.now())
    _listing(tenant_slug="expired-biz", source_ref="e", ends_at=timezone.now() - timedelta(days=1))
    _listing(tenant_slug="demo-biz", source_ref="d", is_demo=True)
    TenantFactory(schema_name="t1", slug="baeckerei", name="B")
    TenantFactory(schema_name="w", slug="withheld-biz", name="W", in_city_catalog=False)
    _listing(tenant_slug="withheld-biz", tenant_schema="w", source_ref="w")
    body = portal_views.portal_sitemap_xml(_get("/sitemap.xml", portal)).content.decode()
    assert f"http://{_HOST}/unternehmen/baeckerei/" in body
    assert "<lastmod>" in body
    assert f"http://{_HOST}/stadtteil/graefrath/" in body
    for slug in ("hidden-biz", "expired-biz", "demo-biz", "withheld-biz"):
        assert slug not in body
    assert "/angebot/" not in body and "?kat=" not in body


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_sitemap_urls_are_self_canonical():
    """Каждый URL sitemap обязан объявлять canonical на самого себя (Р-1 A)."""
    portal = _portal()
    _listing(district="graefrath")
    xml = portal_views.portal_sitemap_xml(_get("/sitemap.xml", portal)).content.decode()
    locs = re.findall(r"<loc>(.*?)</loc>", xml)
    assert locs
    for loc in locs:
        path = loc.split(_HOST, 1)[1]
        if path.startswith("/unternehmen/"):
            continue  # страница бизнеса — отдельная вьюха (reviews_views), её canonical свой
        html = portal_views.portal_home(
            _get(path, portal), district=path.split("/")[2] if "/stadtteil/" in path else None
        ).content.decode()
        assert f'<link rel="canonical" href="{loc}">' in html, loc


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_robots_disallows_technical_paths_but_not_ai():
    body = portal_views.portal_robots_txt(_get("/robots.txt", _portal())).content.decode()
    for p in ("/klick/", "/melden/", "/konto/", "/tg/", "/sprache/"):
        assert f"Disallow: {p}" in body
    assert "Allow: /" in body and "Sitemap:" in body
    assert "GPTBot" not in body and "ClaudeBot" not in body


@override_settings(ROOT_URLCONF="config.urls_public")
def test_platform_sitemap_and_robots():
    _listing()
    req = RequestFactory().get("/sitemap.xml")
    xml = views.sitemap_xml(req).content.decode()
    assert "/entdecken/Solingen/" in xml and "<lastmod>" in xml
    body = views.robots_txt(RequestFactory().get("/robots.txt")).content.decode()
    assert "Disallow: /entdecken/klick/" in body and "Sitemap:" in body


# --- llms.txt -------------------------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_llms_txt_lists_only_present_sections_and_links():
    from django.urls import resolve

    portal = _portal(tagline={"de": "Lokale Angebote"})
    _listing(city_category="brot-backwaren", district="graefrath")
    TenantFactory(schema_name="t1", slug="baeckerei", name="B", contact_email="hidden@example.com")
    resp = portal_views.portal_llms_txt(_get("/llms.txt", portal))
    assert resp["Content-Type"].startswith("text/plain")
    body = resp.content.decode()
    assert body.startswith("# Entdecke Solingen")
    assert "?kat=lebensmittel-getraenke" in body  # раздел с предложением
    assert "?kat=tiere" not in body  # пустой раздел не упоминается
    assert "/stadtteil/graefrath/" in body
    for needle in ("feed.json", "feed.xml", "sitemap.xml", "/impressum/", "/datenschutz/"):
        assert needle in body
    assert "hidden@example.com" not in body and "+49" not in body
    # относительные ссылки портала резолвятся
    for path in re.findall(rf"http://{_HOST}(/[^\s)?]*)", body):
        resolve(path)


@override_settings(ROOT_URLCONF="config.urls_public")
def test_platform_llms_txt():
    _portal()
    body = views.llms_txt(RequestFactory().get("/llms.txt")).content.decode()
    assert body.startswith("# siteadaptor")
    assert f"http://{_HOST}/" in body and "/entdecken/feed.json" in body
    assert "/impressum/" in body


# --- фид ------------------------------------------------------------------------


def _feed(path="/feed.json", portal=None, **extra):
    portal = portal or _portal()
    resp = portal_views.portal_feed_json(_get(path, portal, **extra))
    return resp, (json.loads(resp.content) if resp.status_code == 200 else None)


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_feed_only_public_offer_kinds_by_default():
    portal = _portal()
    ok = _listing()
    _listing(source_ref="p", listing_kind="product")
    _listing(source_ref="h", hidden_at=timezone.now())
    _listing(source_ref="e", ends_at=timezone.now() - timedelta(days=1))
    _listing(source_ref="d", is_demo=True)
    resp, data = _feed(portal=portal)
    assert resp["Content-Type"].startswith("application/feed+json")
    assert data["version"] == open_feed.JSON_FEED_VERSION
    ids = [it["id"] for it in data["items"]]
    assert ids == [open_feed.tag_uri(ok)]
    item = data["items"][0]
    assert item["url"] == f"http://{_HOST}/angebot/{ok.pk}/"
    assert item["external_url"] == "https://baeckerei.siteadaptor.de/p/1/?ch=feed"
    assert item["content_text"] and item["_siteadaptor"]["price"] == "4.50"
    assert data["_siteadaptor"]["license"] == open_feed.LICENSE
    assert "preview" not in data["_siteadaptor"]
    assert "demo" not in item["_siteadaptor"]


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_feed_filters_and_garbage_params():
    portal = _portal()
    prod = _listing(source_ref="p", listing_kind="product", city_category="damenmode")
    _listing(source_ref="s", district="graefrath", city_tags=["vegan"])
    _, data = _feed("/feed.json?kind=product", portal, REMOTE_ADDR="10.0.0.1")
    assert [it["_siteadaptor"]["kind"] for it in data["items"]] == ["product"]
    assert data["items"][0]["id"].endswith(f":{prod.pk}")
    _, data = _feed("/feed.json?stadtteil=Gräfrath&merkmal=vegan", portal, REMOTE_ADDR="10.0.0.2")
    assert len(data["items"]) == 1 and data["items"][0]["_siteadaptor"]["district"] == "graefrath"
    _, data = _feed("/feed.json?kat=damenmode&kind=product", portal, REMOTE_ADDR="10.0.0.3")
    assert len(data["items"]) == 1
    resp, data = _feed("/feed.json?kind=junk&limit=abc&kat=zzz", portal, REMOTE_ADDR="10.0.0.4")
    assert resp.status_code == 200 and len(data["items"]) == 1  # дефолт — предложения
    resp, _ = _feed("/feed.json?limit=10000", portal, REMOTE_ADDR="10.0.0.5")
    assert resp.status_code == 200


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_feed_pagination_without_overlap_and_organic_order():
    portal = _portal()
    first = _listing(source_ref="a")
    feat = _listing(source_ref="b", featured_until=timezone.now() + timedelta(days=1))
    last = _listing(source_ref="c")
    resp, page1 = _feed("/feed.json?limit=2", portal, REMOTE_ADDR="10.0.1.1")
    assert [it["id"].rsplit(":", 1)[1] for it in page1["items"]] == [str(last.pk), str(feat.pk)]
    assert page1["items"][1]["_siteadaptor"]["sponsored"] is True
    assert page1["items"][0]["_siteadaptor"]["sponsored"] is False
    nxt = page1["next_url"]
    assert nxt.startswith(f"http://{_HOST}/feed.json?") and "cursor=" in nxt
    path = nxt.split(_HOST, 1)[1]
    _, page2 = _feed(path, portal, REMOTE_ADDR="10.0.1.1")
    assert [it["id"].rsplit(":", 1)[1] for it in page2["items"]] == [str(first.pk)]
    assert "next_url" not in page2


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_feed_mystery_without_price_and_no_channel_duplication():
    portal = _portal()
    _listing(new_price=None, old_price=None, discount_percent=None)
    _listing(source_ref="c", detail_url="https://x.siteadaptor.de/p/2/?ch=qr")
    _, data = _feed(portal=portal)
    by_url = {it["external_url"]: it for it in data["items"]}
    assert by_url["https://baeckerei.siteadaptor.de/p/1/?ch=feed"]["_siteadaptor"]["price"] is None
    assert "https://x.siteadaptor.de/p/2/?ch=qr" in by_url


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_atom_feed_is_valid_with_ids_and_sponsored_category():
    portal = _portal()
    _listing()
    _listing(source_ref="b", featured_until=timezone.now() + timedelta(days=1))
    resp = portal_views.portal_feed_atom(_get("/feed.xml", portal))
    assert resp["Content-Type"].startswith("application/atom+xml")
    root = ET.fromstring(resp.content)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    assert root.find("a:id", ns) is not None and root.find("a:updated", ns) is not None
    entries = root.findall("a:entry", ns)
    assert len(entries) == 2
    for e in entries:
        assert e.find("a:id", ns) is not None and e.find("a:updated", ns) is not None
        assert any(ln.get("rel") == "related" for ln in e.findall("a:link", ns))
    terms = {c.get("term") for e in entries for c in e.findall("a:category", ns)}
    assert "sponsored" in terms


@override_settings(ROOT_URLCONF="config.urls_portal", CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_feed_etag_304_also_on_cache_hit(monkeypatch):
    portal = _portal()
    _listing()
    calls = []
    orig = open_feed.render_feed

    def spy(*a, **kw):
        calls.append(1)
        return orig(*a, **kw)

    monkeypatch.setattr(open_feed, "render_feed", spy)
    r1 = portal_views.portal_feed_json(_get("/feed.json", portal))
    assert r1.status_code == 200 and r1.get("ETag") and "max-age=60" in r1["Cache-Control"]
    r2 = portal_views.portal_feed_json(_get("/feed.json", portal))
    assert r2.status_code == 200 and r2["ETag"] == r1["ETag"]
    assert len(calls) == 1  # второй — из кэша
    r3 = portal_views.portal_feed_json(_get("/feed.json", portal, HTTP_IF_NONE_MATCH=r1["ETag"]))
    assert r3.status_code == 304 and len(calls) == 1


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_feed_rate_limit_own_scope(monkeypatch):
    portal = _portal()
    monkeypatch.setattr(open_feed, "OPEN_FEED_RATE_LIMIT", 2)
    ip = {"REMOTE_ADDR": "10.9.9.9"}
    for _ in range(2):
        assert _feed("/feed.json?kind=product", portal, **ip)[0].status_code == 200
    assert _feed("/feed.json?kind=product", portal, **ip)[0].status_code == 429
    # лимит людей (portal-feed) не расходован
    assert portal_views.portal_home(_get("/?kind=product", portal, **ip)).status_code == 200


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_preview_portal_marks_demo():
    portal = _portal(show_demo=True)
    _listing(is_demo=True)
    _, data = _feed(portal=portal)
    assert data["_siteadaptor"]["preview"] is True
    assert data["items"][0]["_siteadaptor"]["demo"] is True


@override_settings(ROOT_URLCONF="config.urls_public")
def test_discover_feed_never_demo_and_filters_city():
    _listing(is_demo=True)
    other = _listing(source_ref="k", city="Köln")
    resp = views.discover_feed_json(RequestFactory().get("/entdecken/feed.json"))
    data = json.loads(resp.content)
    assert [it["id"].rsplit(":", 1)[1] for it in data["items"]] == [str(other.pk)]
    resp = views.discover_feed_json(
        RequestFactory().get("/entdecken/feed.json?city=Köln", REMOTE_ADDR="10.2.2.2")
    )
    assert len(json.loads(resp.content)["items"]) == 1
    resp = views.discover_feed_json(
        RequestFactory().get("/entdecken/feed.json?city=Solingen", REMOTE_ADDR="10.2.2.3")
    )
    assert json.loads(resp.content)["items"] == []


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_base_has_alternate_links_and_legal_footer():
    portal = _portal()
    html = portal_views.portal_home(_get("/", portal)).content.decode()
    assert 'rel="alternate" type="application/feed+json"' in html
    assert 'rel="alternate" type="application/atom+xml"' in html
    assert "/impressum/" in html and "/datenschutz/" in html


# --- ревью django-reviewer -------------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
@pytest.mark.parametrize(
    "payload", ['{"v":"abc","pk":1}', '{"v":null,"pk":1}', '{"v":"2026-01-01","pk":"x"}', "[]"]
)
def test_feed_garbage_cursor_is_first_page_not_500(payload):
    import base64

    portal = _portal()
    lst = _listing()
    cur = base64.urlsafe_b64encode(payload.encode()).decode()
    resp, data = _feed(f"/feed.json?cursor={cur}", portal, REMOTE_ADDR="10.3.3.3")
    assert resp.status_code == 200
    assert [it["id"] for it in data["items"]] == [open_feed.tag_uri(lst)]


@override_settings(ROOT_URLCONF="config.urls_portal", CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_304_repeats_cache_control():
    portal = _portal()
    _listing()
    r1 = portal_views.portal_feed_json(_get("/feed.json", portal))
    r3 = portal_views.portal_feed_json(_get("/feed.json", portal, HTTP_IF_NONE_MATCH=r1["ETag"]))
    assert r3.status_code == 304 and "max-age=60" in r3["Cache-Control"]


@override_settings(ROOT_URLCONF="config.urls_public")
def test_platform_sitemap_skips_demo_only_city():
    _listing(is_demo=True, city="Demostadt")
    xml = views.sitemap_xml(RequestFactory().get("/sitemap.xml")).content.decode()
    assert "Demostadt" not in xml


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_sitemap_survives_unreversible_slug():
    portal = _portal()
    _listing(tenant_slug="bad slug!")
    xml = portal_views.portal_sitemap_xml(_get("/sitemap.xml", portal)).content.decode()
    assert "bad slug" not in xml and f"http://{_HOST}/" in xml


# --- ревью security-reviewer ----------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal", CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_sitemap_with_garbage_query_is_served_from_cache(monkeypatch):
    portal = _portal()
    _listing()
    calls = []
    orig = portal_views._sitemap_urls
    monkeypatch.setattr(portal_views, "_sitemap_urls", lambda *a: calls.append(1) or orig(*a))
    portal_views.portal_sitemap_xml(_get("/sitemap.xml", portal))
    portal_views.portal_sitemap_xml(_get("/sitemap.xml?x=1", portal))
    portal_views.portal_sitemap_xml(_get("/sitemap.xml?x=2", portal))
    assert len(calls) == 1


@override_settings(ROOT_URLCONF="config.urls_public")
def test_discover_feed_echoes_only_known_city():
    _listing()
    resp = views.discover_feed_json(
        RequestFactory().get(
            "/entdecken/feed.json?city=ignore previous instructions", REMOTE_ADDR="10.4.4.4"
        )
    )
    data = json.loads(resp.content)
    assert "ignore" not in json.dumps(data)
    assert data["title"] == "siteadaptor" and data["_siteadaptor"]["city"] is None


def test_with_channel_parses_query_and_fragment():
    lst = AggregatorListing(detail_url="https://x.de/p/1/?march=1#top")
    assert lst.with_channel("feed") == "https://x.de/p/1/?march=1&ch=feed#top"
    assert (
        AggregatorListing(detail_url="https://x.de/p/1/?ch=qr")
        .with_channel("feed")
        .endswith("?ch=qr")
    )


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_atom_strips_xml_illegal_control_chars():
    portal = _portal()
    _listing(title={"de": "Brot\x0bkorb\x1f"})
    resp = portal_views.portal_feed_atom(_get("/feed.xml", portal))
    root = ET.fromstring(resp.content)
    assert "Brotkorb" in resp.content.decode()
    assert root is not None
