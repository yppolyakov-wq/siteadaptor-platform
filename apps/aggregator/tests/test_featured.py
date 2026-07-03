"""P2.4a: featured-листинги — платное продвижение в выдаче порталов/агрегатора."""

import uuid
from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.aggregator import portal_views, tasks, views
from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _public_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_public"


def _listing(featured_hours=None, **kw):
    defaults = {
        "tenant_schema": "t1",
        "tenant_slug": "x",
        "business_name": "X",
        "business_type": "bakery",
        "city": "Hilden",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Brot -20%"},
        "detail_url": "https://x.siteadaptor.de/p/1/",
        "is_active": True,
    }
    if featured_hours is not None:
        defaults["featured_until"] = timezone.now() + timedelta(hours=featured_hours)
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def test_featured_pinned_on_top_with_badge():
    _listing(title={"de": "Gewöhnlich"})
    _listing(featured_hours=24, title={"de": "Beworben"})

    body = views.city_listing(RequestFactory().get("/entdecken/Hilden/"), "Hilden")
    body = body.content.decode()
    assert "Anzeige" in body  # UWG §5a: платное = «Anzeige»
    assert body.index("Beworben") < body.index("Gewöhnlich")  # закреплён сверху


def test_expired_featured_is_ordinary():
    _listing(featured_hours=-1, title={"de": "Abgelaufen"})
    body = views.city_listing(RequestFactory().get("/entdecken/Hilden/"), "Hilden")
    body = body.content.decode()
    assert "Abgelaufen" in body  # в обычной ленте
    # Перепин D2.1: голое «Anzeige» теперь всегда в статичном JS карты
    # (popupContent) — проверяем отсутствие БЕЙДЖА разметки, не литерала.
    assert "★ Anzeige</span>" not in body  # без бейджа на карточке


def test_featured_not_duplicated_in_feed():
    listing = _listing(featured_hours=24, title={"de": "EinmalBitte"})
    featured, rest = views.split_featured(views.listings_for(city="Hilden"), first_page=True)
    assert [obj.pk for obj in featured] == [listing.pk]
    assert listing.pk not in [obj.pk for obj in rest]  # из ленты исключён


def test_cursor_pages_skip_featured_block():
    featured = _listing(featured_hours=24, title={"de": "ObenFest"})
    for i in range(3):
        _listing(title={"de": f"Rest{i}"})
    first = views.city_listing(RequestFactory().get("/entdecken/Hilden/"), "Hilden")
    assert "ObenFest" in first.content.decode()

    _, rest = views.split_featured(views.listings_for(city="Hilden"), first_page=False)
    assert featured.pk not in [obj.pk for obj in rest]  # и не в ленте cursor-страниц


@pytest.fixture
def _portal_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_portal"


def test_portal_home_pins_featured(_portal_urlconf):
    portal = AggregatorPortal.objects.create(
        host="hilden.siteadaptor.de", kind="city", city="Hilden", title={"de": "Hilden"}
    )
    _listing(title={"de": "Gewöhnlich"})
    _listing(featured_hours=24, title={"de": "Beworben"})
    request = RequestFactory().get("/", HTTP_HOST=portal.host)
    request.portal = portal
    body = portal_views.portal_home(request).content.decode()
    assert "Anzeige" in body  # UWG §5a: платное = «Anzeige»
    assert body.index("Beworben") < body.index("Gewöhnlich")


def test_resync_keeps_featured_until():
    """sync_listing перезаписывает карточку, но не срок продвижения."""
    TenantFactory(schema_name="public", slug="x", name="X", city="Hilden")
    promo = Promotion.objects.create(status="active", title={"de": "A"})
    tasks.sync_listing("public", str(promo.id))

    listing = AggregatorListing.objects.get(promo_uuid=promo.id)
    until = timezone.now() + timedelta(days=7)
    listing.featured_until = until
    listing.save(update_fields=["featured_until"])

    tasks.sync_listing("public", str(promo.id))  # ресинк (правка акции)
    listing.refresh_from_db()
    assert listing.featured_until == until


# ---------------------------------------------------------------------------
# D2.1 + D2.3: Anzeige на карте, показы/клики featured
# ---------------------------------------------------------------------------


def test_map_points_carry_featured_flag_and_click_url():
    from apps.aggregator import geo

    plain = _listing(latitude=51.0, longitude=7.0)
    feat = _listing(featured_hours=24, latitude=51.2, longitude=7.1)
    pts = {p["featured"]: p for p in geo.map_points([plain, feat])}
    assert pts[False]["url"] == plain.detail_url
    assert pts[True]["url"] == f"/entdecken/klick/{feat.pk}/"  # клик через счётчик


def test_impressions_counted_on_first_page_only():
    feat = _listing(featured_hours=24)
    views.city_listing(RequestFactory().get("/entdecken/Hilden/"), "Hilden")
    feat.refresh_from_db()
    assert feat.featured_impressions == 1
    # не-первая страница featured-блок не рендерит → показы не растут
    views.split_featured(AggregatorListing.objects.all(), first_page=False)
    feat.refresh_from_db()
    assert feat.featured_impressions == 1


def test_featured_click_counts_and_redirects():
    feat = _listing(featured_hours=24)
    resp = views.featured_click(RequestFactory().get("/entdecken/klick/x/"), feat.pk)
    assert resp.status_code == 302 and resp["Location"] == feat.detail_url
    feat.refresh_from_db()
    assert feat.featured_clicks == 1


def test_click_after_expiry_redirects_without_count():
    stale = _listing(featured_hours=-1)
    resp = views.featured_click(RequestFactory().get("/entdecken/klick/x/"), stale.pk)
    assert resp.status_code == 302 and resp["Location"] == stale.detail_url
    stale.refresh_from_db()
    assert stale.featured_clicks == 0


def test_click_unknown_listing_is_safe():
    resp = views.featured_click(RequestFactory().get("/entdecken/klick/x/"), 999999)
    assert resp.status_code == 302 and resp["Location"] == "/"
