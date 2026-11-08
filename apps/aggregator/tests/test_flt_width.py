"""FLT-1a: ширина портала — листинги 1536 px (4 колонки карточек на xl), чтение и формы 1024 px.

Макет «Filter & Breite» утверждён владельцем 2026-11-04: на экране 1920 портал занимал 1024 px,
по краям — пустые поля по ~450 px.
"""

import re
import uuid

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings

from apps.aggregator import portal_views, views
from apps.aggregator.models import AggregatorListing, AggregatorPortal

pytestmark = pytest.mark.django_db
_HOST = "solingen.siteadaptor.de"


@pytest.fixture(autouse=True)
def _clear():
    cache.clear()
    yield
    cache.clear()


def _listing():
    return AggregatorListing.objects.create(
        tenant_schema="t1",
        tenant_slug="brot",
        business_name="Brot & Co",
        business_type="bakery",
        city="Solingen",
        promo_uuid=uuid.uuid4(),
        title={"de": "Brotkorb"},
        detail_url="https://brot.siteadaptor.de/p/1/",
        is_active=True,
    )


def _main(html):
    return re.search(r"<main [^>]*>", html).group(0)


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_results_page_is_wide_with_four_column_cards():
    portal = AggregatorPortal.objects.create(
        host=_HOST, kind="city", city="Solingen", title={"de": "Solingen"}, is_active=True
    )
    _listing()
    req = RequestFactory().get("/", HTTP_HOST=_HOST)
    req.portal = portal
    html = portal_views.portal_home(req).content.decode()
    main = _main(html)
    assert "max-w-screen-2xl" in main and "data-wide" in main
    # 2026-11-05: 4 колонки уже с lg (ряд = 4 карточки)
    assert "lg:group-data-[wide]:grid-cols-4" in html
    assert html.count("max-w-screen-2xl") >= 2  # main, подвал
    assert "max-w-[1392px]" in html  # PH-11a: шапка по макету K1


@override_settings(ROOT_URLCONF="config.urls_public")
def test_offer_page_stays_readable_width():
    row = _listing()
    req = RequestFactory().get(f"/entdecken/angebot/{row.pk}/")
    req.portal = None
    main = _main(views.offer_page(req, row.pk).content.decode())
    assert "max-w-5xl" in main and "data-wide" not in main
