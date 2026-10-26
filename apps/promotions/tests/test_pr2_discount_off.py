"""KA-12 PR-2: «−X € pro Stück» — третий вид выгоды, и для товара, и для области."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Category, Product
from apps.orders import services as order_services
from apps.promotions import price_layer
from apps.promotions.forms import PromotionForm
from apps.promotions.models import Promotion

pytestmark = pytest.mark.django_db

D = Decimal


def _promo(**kw):
    kw.setdefault("status", "active")
    kw.setdefault("starts_at", timezone.now())
    return Promotion.objects.create(title={"de": "Aktion"}, **kw)


def test_off_on_product_card_cart_and_order():
    p = Product.objects.create(name={"de": "Brot"}, base_price=D("4.50"))
    _promo(product=p, discount_off=D("1.00"))
    card = price_layer.attach_promos([p])[0]
    assert card.promo_price == D("3.50") and card.promo_badge == "−1,00 €"
    order = order_services.create_order(items=[(p, 3)], name="K")
    assert order.total == D("10.50")


def test_off_for_whole_category_and_never_below_zero():
    brot = Category.objects.create(name={"de": "Brot"}, slug="brot-x")
    a = Product.objects.create(name={"de": "A"}, base_price=D("3.00"), category=brot)
    b = Product.objects.create(name={"de": "B"}, base_price=D("0.80"), category=brot)
    _promo(category=brot, discount_off=D("1.00"))
    pmap = price_layer.product_promo_map([a.pk, b.pk])
    assert pmap[a.pk].new_price == D("2.00")
    assert pmap[b.pk].new_price == D("0.00")


def test_form_allows_only_one_kind_of_saving():
    base = {
        "title_de": "X",
        "promo_type": "discount",
        "starts_at": "2030-01-01T10:00",
        "ends_at": "2030-01-08T10:00",
        "discount_style": "",
        "recurrence": "",
    }
    form = PromotionForm(data={**base, "discount_percent": 10, "discount_off": "1,00"})
    assert not form.is_valid() and "discount_off" in form.errors
    form = PromotionForm(data={**base, "discount_off": "0"})
    assert not form.is_valid() and "discount_off" in form.errors
