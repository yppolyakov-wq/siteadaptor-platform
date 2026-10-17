"""D2a-1: адаптер «акция → CheckInput» (план d2-ai-text-check §3.1)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.promotions import text_check as ptc
from apps.promotions.models import Promotion

pytestmark = pytest.mark.django_db


def test_unsaved_free_promotion_is_checked_without_db_writes():
    promo = Promotion(
        title={"de": "Gratis Kaffee – nur heute!"},
        description={"de": "Der beste Kaffee der Stadt"},
        price_override=Decimal("2.50"),
        ends_at=timezone.now() + timezone.timedelta(days=6),
    )
    found = ptc.for_promotion(promo, tenant=None)
    codes = {f.code for f in found}
    assert {"gratis_mit_preis", "dringlichkeit_heute", "alleinstellung"} <= codes
    assert Promotion.objects.count() == 0


def test_mystery_style_marks_input():
    promo = Promotion(title={"de": "Tüte für 3 €"}, discount_style="mystery")
    data = ptc.input_from_promotion(promo, tenant=None)
    assert data.mystery is True


def test_price_condition_note_is_checked_text():
    promo = Promotion(
        title={"de": "Brötchen"},
        metadata={"price_condition": {"kind": "other", "note": {"de": "Der beste Deal"}}},
    )
    data = ptc.input_from_promotion(promo, tenant=None)
    assert data.texts["condition_note"]["de"] == "Der beste Deal"


def test_food_flag_from_tenant_type():
    class T:
        business_type = "bakery"

    data = ptc.input_from_promotion(Promotion(title={"de": "x"}), tenant=T())
    assert data.is_food is True


def test_variant_product_does_not_claim_missing_grundpreis(monkeypatch):
    from apps.catalog.models import Product

    product = Product(name={"de": "Kaffee"}, base_price=Decimal("5"), unit="g")
    monkeypatch.setattr(Product, "has_variants", property(lambda self: True))
    promo = Promotion(title={"de": "Kaffee"}, product=product, price_override=Decimal("4"))
    data = ptc.input_from_promotion(promo, tenant=None)
    assert data.grundpreis_ok is None


def test_unhashable_allergens_do_not_raise():
    from apps.catalog.models import Product

    product = Product(name={"de": "Kuchen"}, base_price=Decimal("3"), allergens=[{"x": 1}])
    promo = Promotion(title={"de": "Kuchen"}, product=product)
    data = ptc.input_from_promotion(promo, tenant=None)
    assert data.allergens == frozenset()
