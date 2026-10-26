"""KA-12 PR-1 (WR-9): акция на категорию (с подкатегориями) и на весь магазин —
одна цена на карточке, в корзине и в заказе («показано = списано»)."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Category, Product, ProductVariant
from apps.orders import services as order_services
from apps.promotions import price_layer
from apps.promotions.forms import PromotionForm
from apps.promotions.models import Promotion

pytestmark = pytest.mark.django_db

D = Decimal


def _scope(pct=20, **kw):
    kw.setdefault("status", "active")
    kw.setdefault("starts_at", timezone.now())
    return Promotion.objects.create(title={"de": "Brot-Woche"}, discount_percent=pct, **kw)


def _tree():
    brot = Category.objects.create(name={"de": "Brot"}, slug="brot")
    voll = Category.objects.create(name={"de": "Vollkorn"}, slug="vollkorn", parent=brot)
    kuchen = Category.objects.create(name={"de": "Kuchen"}, slug="kuchen")
    a = Product.objects.create(name={"de": "Bauernbrot"}, base_price=D("5.00"), category=brot)
    b = Product.objects.create(name={"de": "Dinkel"}, base_price=D("6.00"), category=voll)
    c = Product.objects.create(name={"de": "Torte"}, base_price=D("20.00"), category=kuchen)
    return brot, a, b, c


def test_category_promo_applies_to_subcategories_only():
    brot, a, b, c = _tree()
    promo = _scope(category=brot)
    pmap = price_layer.product_promo_map([a.pk, b.pk, c.pk])
    assert set(pmap) == {a.pk, b.pk}
    assert pmap[a.pk].new_price == D("4.00") and pmap[b.pk].new_price == D("4.80")
    assert pmap[a.pk].pk == promo.pk
    promo.refresh_from_db()
    assert promo.product_id is None  # оригинал не тронут копией


def test_whole_shop_promo_and_best_price_wins():
    _brot, a, _b, c = _tree()
    _scope(pct=10, whole_shop=True)
    own = Promotion.objects.create(
        title={"de": "Torte"},
        product=c,
        status="active",
        starts_at=timezone.now(),
        price_override=D("15.00"),
    )
    pmap = price_layer.product_promo_map([a.pk, c.pk])
    assert pmap[a.pk].new_price == D("4.50")
    assert pmap[c.pk].pk == own.pk  # 15,00 < 18,00 — без суммирования


def test_order_charges_scope_price_and_claims_limit():
    brot, a, _b, _c = _tree()
    promo = _scope(category=brot, available_quantity=5)
    order = order_services.create_order(items=[(a, 2)], name="K")
    assert order.total == D("8.00")
    item = order.items.get()
    assert item.promotion_id == promo.pk and item.list_price == D("5.00")
    promo.refresh_from_db()
    assert promo.available_quantity == 3


def test_variant_with_own_price_keeps_full_price():
    brot, a, _b, _c = _tree()
    _scope(category=brot)
    v = ProductVariant.objects.create(product=a, label="groß", price=D("7.00"))
    order = order_services.create_order(items=[(a, v, 1)], name="K")
    assert order.total == D("7.00")


def test_virtual_copy_cannot_be_saved():
    brot, a, _b, _c = _tree()
    _scope(category=brot)
    clone = price_layer.product_promo_map([a.pk])[a.pk]
    with pytest.raises(RuntimeError):
        clone.save()


def test_form_scope_requires_percent_only():
    brot, *_ = _tree()
    base = {
        "title_de": "X",
        "promo_type": "discount",
        "starts_at": "2030-01-01T10:00",
        "ends_at": "2030-01-08T10:00",
        "discount_style": "",
        "recurrence": "",
    }
    form = PromotionForm(data={**base, "category": brot.pk, "price_override": "3"})
    assert not form.is_valid()
    assert "discount_percent" in form.errors and "price_override" in form.errors
    form = PromotionForm(
        data={**base, "category": brot.pk, "whole_shop": "on", "discount_percent": 10}
    )
    assert not form.is_valid()


def test_scope_response_is_show_not_buy():
    from apps.promotions import response

    brot, *_ = _tree()
    promo = _scope(category=brot)
    assert response.response_for(promo, None) == response.SHOW
