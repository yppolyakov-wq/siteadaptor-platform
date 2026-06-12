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
    assert "Empfohlen" in body
    assert body.index("Beworben") < body.index("Gewöhnlich")  # закреплён сверху


def test_expired_featured_is_ordinary():
    _listing(featured_hours=-1, title={"de": "Abgelaufen"})
    body = views.city_listing(RequestFactory().get("/entdecken/Hilden/"), "Hilden")
    body = body.content.decode()
    assert "Abgelaufen" in body  # в обычной ленте
    assert "Empfohlen" not in body  # без бейджа


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
    assert "Empfohlen" in body
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
