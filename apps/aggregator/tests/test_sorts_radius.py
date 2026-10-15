"""T-8.7 Р-5/Р-6: сортировки «Neu / Endet bald / Jetzt geöffnet / Nähe» и радиус «im Umkreis».

Замки: lat/lng никогда не попадают в журнал поиска (T-8.21), featured не поднимается
органически ни одним сортом (UWG §5a), блоки главной и сорт делят один порядок.
"""

import uuid
from datetime import timedelta

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.aggregator import geo, portal_home_blocks, portal_views, search, views
from apps.aggregator.models import AggregatorListing, AggregatorPortal, SearchQueryLog
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

CITY = "Solingen"
CENTER = (51.1716, 7.0836)


def _portal():
    return AggregatorPortal.objects.create(
        host=f"{uuid.uuid4().hex[:8]}.solingen.test",
        kind="city",
        city=CITY,
        title={"de": "Solingen"},
        is_active=True,
    )


def _tenant(**kw):
    kw.setdefault("city", CITY)
    return TenantFactory(**kw)


def _listing(tenant=None, **kw):
    tenant = tenant or _tenant()
    defaults = {
        "tenant_schema": tenant.schema_name,
        "tenant_slug": tenant.slug,
        "business_name": tenant.name,
        "business_type": tenant.business_type,
        "city": CITY,
        "listing_kind": AggregatorListing.KIND_PROMOTION,
        "source_ref": uuid.uuid4().hex,
        "title": {"de": "Brot"},
        "detail_url": f"https://{tenant.slug}.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _req(path="/", data=None, portal=None):
    request = RequestFactory().get(path, data or {}, HTTP_X_FORWARDED_FOR=uuid.uuid4().hex)
    SessionMiddleware(lambda r: None).process_request(request)
    request.portal = portal
    return request


def _order(resp, *titles):
    """Порядок заголовков в разметке (карточки не несут id — равняемся на текст)."""
    html = resp.content.decode()
    found = [(html.find(f'alt="{t}"') if f'alt="{t}"' in html else html.find(t), t) for t in titles]
    assert all(pos >= 0 for pos, _t in found), (titles, [p for p, _t in found])
    return [t for _pos, t in sorted(found)]


# --- парсинг ------------------------------------------------------------------------------


def test_sort_whitelist_and_naehe_requires_point():
    assert search.parse_filters(_req("/", {"sort": "endet"})).sort == "endet"
    assert search.parse_filters(_req("/", {"sort": "bogus"})).sort == ""
    assert search.parse_filters(_req("/", {"sort": "naehe"})).sort == ""  # без точки сброс
    assert search.parse_filters(_req("/", {"sort": "naehe"}), point=CENTER).sort == "naehe"


def test_radius_only_with_point_and_whitelisted():
    assert search.parse_filters(_req("/", {"umkreis": "5"})).radius_km is None
    assert search.parse_filters(_req("/", {"umkreis": "5"}), point=CENTER).radius_km == 5
    assert search.parse_filters(_req("/", {"umkreis": "7"}), point=CENTER).radius_km is None
    assert search.parse_filters(_req("/", {"umkreis": "x"}), point=CENTER).radius_km is None


def test_latlng_never_in_search_carry_but_umkreis_is():
    f = search.parse_filters(_req("/", {"umkreis": "5", "lat": "51.1", "lng": "7.0"}), point=CENTER)
    keys = dict(search.carry("", f))
    assert "lat" not in keys and "lng" not in keys
    assert keys["umkreis"] == "5"
    assert geo.carry(51.17161, 7.08362, 5) == [
        ("lat", "51.172"),
        ("lng", "7.084"),
        ("umkreis", "5"),
    ]


# --- порядок ------------------------------------------------------------------------------


def test_sort_endet_orders_by_end_nulls_last_offset_pagination_no_dupes():
    now = timezone.now()
    soon = _listing(ends_at=now + timedelta(hours=2), title={"de": "Bald"})
    later = _listing(ends_at=now + timedelta(days=5), title={"de": "Später"})
    never = _listing(title={"de": "Dauer"})
    pool = views.listings_for(city=CITY)
    f = search.SearchFilters(sort="endet")
    out = search.execute(pool, "", f, surface="portal", track=False)
    assert out.ranked is True
    assert [i.pk for i in out.qs] == [soon.pk, later.pk, never.pk]
    from apps.core.pagination import paginate_ranked

    first = paginate_ranked(out.qs, limit=2, cursor=None)
    second = paginate_ranked(out.qs, limit=2, cursor=first.next_cursor)
    assert [i.pk for i in first.items] + [i.pk for i in second.items] == [
        soon.pk,
        later.pk,
        never.pk,
    ]


def test_sort_offen_open_first_closed_kept(monkeypatch):
    open_tenant = _tenant()
    closed_tenant = _tenant()
    closed = _listing(closed_tenant, title={"de": "Zu"})
    opened = _listing(open_tenant, title={"de": "Auf"})
    monkeypatch.setattr(views, "_open_now_schemas", lambda schemas: {open_tenant.schema_name})
    out = search.execute(
        views.listings_for(city=CITY),
        "",
        search.SearchFilters(sort="offen"),
        surface="portal",
        track=False,
    )
    assert [i.pk for i in out.qs] == [opened.pk, closed.pk]


def test_sort_with_query_overrides_rank():
    old = _listing(title={"de": "Roggenbrot frisch"})
    AggregatorListing.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=3)
    )
    new = _listing(title={"de": "Brot"})
    out = search.execute(
        views.listings_for(city=CITY),
        "roggenbrot",
        search.SearchFilters(sort="neu"),
        surface="portal",
        track=False,
    )
    ids = [i.pk for i in out.qs]
    assert ids and ids[0] == new.pk if new.pk in ids else ids[0] == old.pk


def test_blocks_use_shared_orderings():
    assert [str(x) for x in portal_home_blocks._order("urgent")] == [
        str(x) for x in search.ORDERINGS["endet"]
    ]
    assert portal_home_blocks._order("anything") == search.ORDERINGS["neu"]


# --- радиус -------------------------------------------------------------------------------


def test_radius_filters_exact_distance_and_excludes_no_coords():
    near = _listing(latitude=51.1720, longitude=7.0840, title={"de": "Nah"})  # ~50 м
    far = _listing(latitude=51.2500, longitude=7.2000, title={"de": "Fern"})  # ~12 км
    nocoords = _listing(title={"de": "Ohne"})
    pool = views.listings_for(city=CITY)
    kept = set(geo.within_radius(pool, *CENTER, 5).values_list("pk", flat=True))
    assert kept == {near.pk}
    assert far.pk not in kept and nocoords.pk not in kept
    assert set(geo.within_radius(pool, *CENTER, 25).values_list("pk", flat=True)) == {
        near.pk,
        far.pk,
    }
    # без точки радиус игнорируется
    f = search.SearchFilters(radius_km=5)
    assert search.apply_filters(pool, f).count() == 3


# --- поверхности --------------------------------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_feed_sorts_and_radius_pills_and_log_without_coords():
    portal = _portal()
    now = timezone.now()
    _listing(
        ends_at=now + timedelta(hours=1), latitude=51.172, longitude=7.084, title={"de": "Nahbald"}
    )
    _listing(latitude=51.25, longitude=7.2, title={"de": "Fernweit"})
    req = _req(
        "/",
        {"sort": "endet", "lat": "51.1716", "lng": "7.0836", "umkreis": "5"},
        portal=portal,
    )
    resp = portal_views.portal_home(req)
    html = resp.content.decode()
    assert "Nahbald" in html and "Fernweit" not in html
    assert "data-radius-select" in html and "≤ 5 km" in html
    assert 'name="lat"' in html  # точка едет в hidden формы фильтров
    log = SearchQueryLog.objects.order_by("-pk").first()
    assert log is not None
    assert "lat" not in log.filters_key and "lng" not in log.filters_key
    assert "umkreis=5" in log.filters_key


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_latlng_without_sort_is_naehe_and_explicit_sort_paginates():
    portal = _portal()
    _listing(latitude=51.25, longitude=7.2, title={"de": "Fern"})
    near = _listing(latitude=51.172, longitude=7.084, title={"de": "Nah"})
    AggregatorListing.objects.filter(pk=near.pk).update(
        created_at=timezone.now() - timedelta(days=2)
    )
    resp = portal_views.portal_home(_req("/", {"lat": "51.1716", "lng": "7.0836"}, portal))
    assert _order(resp, "Nah", "Fern") == ["Nah", "Fern"]  # по дистанции
    resp = portal_views.portal_home(
        _req("/", {"lat": "51.1716", "lng": "7.0836", "sort": "neu"}, portal)
    )
    assert _order(resp, "Nah", "Fern") == ["Fern", "Nah"]  # по новизне, с пагинацией


def test_featured_still_separate_under_all_sorts():
    now = timezone.now()
    featured = _listing(featured_until=now + timedelta(days=1), ends_at=now + timedelta(days=9))
    organic = _listing(ends_at=now + timedelta(hours=1))
    pool = views.listings_for(city=CITY)
    for sort in ("", "neu", "endet", "offen"):
        out = search.execute(
            pool, "", search.SearchFilters(sort=sort), surface="portal", track=False
        )
        promoted, rest = views.split_featured(out.qs, first_page=True)
        assert [c.pk for c in promoted] == [featured.pk]
        assert featured.pk not in [c.pk for c in rest]
        assert organic.pk in [c.pk for c in rest]


@override_settings(ROOT_URLCONF="config.urls_public")
def test_entdecken_sort_select_and_endet():
    now = timezone.now()
    _listing(ends_at=now + timedelta(hours=1), title={"de": "Baldzuende"})
    _listing(title={"de": "Dauerhaft"})
    resp = views.discover_index(_req("/entdecken/", {"city": CITY, "sort": "endet"}))
    html = resp.content.decode()
    assert "data-sort-select" in html
    assert _order(resp, "Baldzuende", "Dauerhaft") == ["Baldzuende", "Dauerhaft"]
