"""PH-4: первый экран — цифры, «Deal des Tages» (органика, UWG §5a), быстрые чипы."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.aggregator import portal_home_blocks as home
from apps.aggregator.models import AggregatorListing
from apps.aggregator.tests.test_portal_discover import _html, _listing, _portal

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]

IMG = {"url": "https://x.test/a.jpg"}


def _deal(title, pct, **kw):
    return _listing(
        "promotion",
        title,
        city_category="restaurants",
        discount_percent=pct,
        new_price=5,
        image=IMG,
        **kw,
    )


def test_featured_never_becomes_deal_of_day():
    _deal("Bezahlt", 90, featured_until=timezone.now() + timedelta(days=1))
    organic = _deal("Organisch", 20)
    deal = home.deal_of_day(AggregatorListing.objects.all())
    assert deal.pk == organic.pk


def test_ending_today_beats_bigger_discount():
    _deal("Groß", 60, ends_at=timezone.now() + timedelta(days=3))
    # Не «+30 мин»: в 23:46 по Берлину это уже завтра (флак CI 2026-11-07).
    now = timezone.localtime()
    end_of_day = now.replace(hour=23, minute=59, second=0, microsecond=0)
    ends = min(now + timedelta(minutes=30), max(end_of_day, now + timedelta(seconds=30)))
    today = _deal("Heute", 20, ends_at=ends)
    deal = home.deal_of_day(AggregatorListing.objects.all())
    assert deal.pk == today.pk and "heute" in str(deal.deal_reason)


def test_deal_requires_photo_known_price_and_no_condition():
    _listing("promotion", "Ohne Foto", discount_percent=50, new_price=5)
    _deal("Bedingung", 50, price_condition={"kind": "nth"})
    _deal("Mystery", 50, is_surprise=True)
    assert home.deal_of_day(AggregatorListing.objects.all()) is None


def test_hero_on_home_deal_not_repeated_and_no_csrf():
    portal = _portal()
    d = _deal("Pizza-Deal", 40)
    for i in range(3):
        _listing("product", f"Ware {i}", city_category="brot-backwaren")
    body = _html(portal)
    assert "data-deal-of-day" in body and "Deal des Tages" in body
    assert body.count(d.title["de"]) == 1 or body.count(f">{d.title['de']}<") == 1
    assert "Was gibt&#x27;s heute in Solingen?" in body or "Was gibt's heute in Solingen?" in body
    assert "data-portal-search" in body and "csrfmiddlewaretoken" not in body
