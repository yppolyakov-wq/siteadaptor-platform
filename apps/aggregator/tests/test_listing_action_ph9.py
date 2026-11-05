"""PH-9: снимок отклика акции и остатка лимита в листинге портала."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.template import Context, Template
from django.utils import timezone

from apps.aggregator import portal_cards, tasks
from apps.aggregator.models import AggregatorListing
from apps.aggregator.tests.test_v2_v4_listing import _product, _tenant
from apps.promotions.models import Promotion

pytestmark = pytest.mark.django_db


def _promo(**kw):
    kw.setdefault("status", "active")
    kw.setdefault("starts_at", timezone.now())
    kw.setdefault("ends_at", timezone.now() + timedelta(days=2))
    kw.setdefault("title", {"de": "Coupon-Aktion"})
    kw.setdefault("discount_percent", 20)
    return Promotion.objects.create(**kw)


def test_snapshot_carries_owner_response_and_remaining():
    _tenant()
    promo = _promo(product=_product(), available_quantity=3, metadata={"response": "coupon"})
    assert tasks.sync_listing("public", str(promo.id)) == "upserted"
    row = AggregatorListing.objects.get(promo_uuid=promo.id)
    assert row.action == "coupon" and row.remaining == 3
    assert str(portal_cards.card_action(row)) == "Coupon holen"


def test_no_limit_means_no_remaining_and_kind_fallback():
    _tenant()
    promo = _promo(product=_product(), metadata={"response": "reserve"})
    tasks.sync_listing("public", str(promo.id))
    row = AggregatorListing.objects.get(promo_uuid=promo.id)
    assert row.remaining is None and str(portal_cards.card_action(row)) == "Zurücklegen"
    product = SimpleNamespace(action="", listing_kind="product")
    assert str(portal_cards.card_action(product)) == "Ansehen"


def test_card_shows_few_left_only_when_small():
    tpl = Template("{% load portal_brand %}{{ l|few_left|default:'-' }}")
    assert tpl.render(Context({"l": SimpleNamespace(remaining=3)})) == "3"
    assert tpl.render(Context({"l": SimpleNamespace(remaining=50)})) == "-"
    assert tpl.render(Context({"l": SimpleNamespace(remaining=None)})) == "-"
