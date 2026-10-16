"""В2 (план v2-v4-conditions-condition-plan-2026-10-16): условие цены акции.

«2. Pizza −50 %» не должна превращаться в «цену одной пиццы × 0,5» — ни на витрине,
ни в корзине (деньги), ни в каталоге города. Замки написаны ДО кода."""

from decimal import Decimal

import pytest
from django.test import RequestFactory
from django.utils import timezone, translation

from apps.core import price_conditions as pc
from apps.promotions import price_layer, response
from apps.promotions.forms import PromotionForm
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

PIZZA = {"kind": "nth", "n": 2, "pay": None, "note": {}}


def _product(price="9.00"):
    from apps.catalog.models import Product

    return Product.objects.create(name={"de": "Pizza Verdure"}, base_price=Decimal(price))


def _promo(product=None, cond=PIZZA, **kw):
    kw.setdefault("status", "active")
    kw.setdefault("starts_at", timezone.now())
    kw.setdefault("title", {"de": "Pizza-Abend: zweite Pizza −50 %"})
    kw.setdefault("discount_percent", 50)
    meta = {"price_condition": cond} if cond else {}
    return Promotion.objects.create(product=product, metadata=meta, **kw)


# --- модуль ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "x",
        {"kind": "bogus", "n": 2},
        {"kind": "nth"},
        {"kind": "nth", "n": 1},
        {"kind": "nth", "n": 11},
        {"kind": "x_for_y", "n": 2, "pay": 2},
        {"kind": "x_for_y", "n": 2},
        {"kind": "other", "note": {}},
        {"kind": "min_qty", "n": "drei"},
    ],
)
def test_normalize_rejects_garbage(raw):
    assert pc.normalize(raw) is None


def test_normalize_is_stable():
    raw = {"kind": "x_for_y", "n": "3", "pay": "2", "note": {"de": "  ", "en": " Mix "}}
    assert pc.normalize(raw) == {"kind": "x_for_y", "n": 3, "pay": 2, "note": {"en": "Mix"}}


@pytest.mark.parametrize(
    "cond, pct, de, ru",
    [
        ({"kind": "nth", "n": 2}, 50, "2. Stück −50 %", "2-я штука −50 %"),
        ({"kind": "x_for_y", "n": 2, "pay": 1}, None, "2 für 1", "2 по цене 1"),
        ({"kind": "min_qty", "n": 3}, 20, "ab 3 Stück −20 %", "от 3 шт. −20 %"),
        (
            {"kind": "other", "note": {"de": "beim Kauf einer Brille"}},
            50,
            "beim Kauf einer Brille",
            None,
        ),
    ],
)
def test_labels_render_all_kinds(cond, pct, de, ru):
    assert pc.label(cond, pct, "de") == de
    if ru:
        out = pc.label(cond, pct, "ru")
        assert out == ru and "%%" not in out


# --- деньги: условная акция не удешевляет штуку ---------------------------------


def test_conditional_promo_keeps_unit_price():
    product = _product()
    promo = _promo(product)
    assert promo.price_condition["kind"] == "nth"
    assert promo.new_price == Decimal("9.00")
    assert promo.lowers_price is False
    assert promo.has_discount is False
    assert promo.discount_percent_display is None
    assert price_layer.product_promo_map([product.pk]) == {}
    assert price_layer.promo_line_price(promo, product) == Decimal("9.00")


def test_free_conditional_promo_has_no_percent_badge():
    promo = _promo(None, cond={"kind": "min_qty", "n": 3})
    assert promo.discount_percent_display is None
    assert promo.price_condition_label  # подпись есть


def test_mystery_beats_condition():
    promo = _promo(_product(), discount_style="mystery")
    assert promo.price_condition is None


def test_conditional_promo_never_resolves_to_buy():
    tenant = TenantFactory.build(business_type="restaurant")
    tenant.is_module_active = lambda key: True
    promo = _promo(_product())
    assert response.response_for(promo, tenant) != response.BUY
    promo.metadata = {**promo.metadata, "response": "buy"}
    assert response.response_for(promo, tenant) != response.BUY


def test_kaufen_rejects_conditional_promo():
    from apps.orders.models import Order
    from apps.promotions import public_views

    promo = _promo(_product())
    req = RequestFactory().post(
        f"/p/{promo.pk}/kaufen/", {"name": "A", "email": "a@b.de", "quantity": 2}
    )
    req.tenant = TenantFactory.build(business_type="restaurant")
    resp = public_views.promotion_purchase(req, pk=promo.pk)
    assert resp.status_code == 302
    assert not Order.objects.exists()


def test_service_promo_skips_conditional():
    from apps.booking.models import Service

    service = Service.objects.create(name="Haarschnitt", price_cents=3000)
    promo = _promo(None, service=service)
    assert promo not in price_layer.service_promos(service)
    assert price_layer.promo_for_service(service, timezone.now(), promos=[promo]) is None


# --- витрина --------------------------------------------------------------------


def test_storefront_badge_shows_condition_not_unit_price():
    from django.template.loader import render_to_string

    promo = _promo(_product())
    with translation.override("de"):
        html = render_to_string(
            "storefront/_discount_display.html", {"promo": promo, "part": "badge", "size": "sm"}
        )
    assert "data-price-condition" in html and "2. Stück −50 %" in html
    assert "−50 %</span>" not in html.replace("2. Stück −50 %</span>", "")


def test_conditions_list_has_price_condition_first():
    from apps.promotions import rules_text

    promo = _promo(_product())
    with translation.override("de"):
        rows = rules_text.conditions_for(promo)
    assert rows[0]["text"] == "Preis gilt nur: 2. Stück −50 %"


def test_flyer_prints_unit_price_and_condition():
    from apps.promotions import flyer

    promo = _promo(_product())
    with translation.override("de"):
        lines = flyer.price_lines(promo)
    assert "9,00" in lines["main"] and "4,50" not in lines["main"]
    assert lines["badge"] == "2. Stück −50 %"


# --- форма владельца --------------------------------------------------------------


def _form_data(**extra):
    return {
        "title_de": "Pizza-Abend",
        "promo_type": "discount",
        "max_per_customer": 1,
        "reservation_ttl_hours": 24,
        **extra,
    }


def test_form_roundtrip_and_sentinel_w0():
    tenant = TenantFactory(schema_name="public", slug="v2f", business_type="restaurant")
    data = _form_data(
        price_condition_present="1",
        price_condition_kind="nth",
        price_condition_n="2",
        discount_percent="50",
    )
    form = PromotionForm(data, tenant=tenant)
    assert form.is_valid(), form.errors
    promo = form.save()
    assert promo.metadata["price_condition"] == {"kind": "nth", "n": 2, "pay": None, "note": {}}

    # чужой POST без сентинела условие не стирает
    form = PromotionForm(_form_data(discount_percent="50"), instance=promo, tenant=tenant)
    assert form.is_valid(), form.errors
    assert form.save().metadata["price_condition"]["kind"] == "nth"

    # снятие условия — с сентинелом
    form = PromotionForm(_form_data(price_condition_present="1"), instance=promo, tenant=tenant)
    assert form.is_valid(), form.errors
    assert "price_condition" not in form.save().metadata


def test_form_rejects_fixed_price_and_missing_percent():
    tenant = TenantFactory(schema_name="public", slug="v2g", business_type="restaurant")
    form = PromotionForm(
        _form_data(
            price_condition_present="1",
            price_condition_kind="nth",
            price_condition_n="2",
            price_override="4.50",
        ),
        tenant=tenant,
    )
    assert not form.is_valid()
    assert "price_override" in form.errors and "discount_percent" in form.errors


def test_form_rejects_incomplete_condition():
    tenant = TenantFactory(schema_name="public", slug="v2h", business_type="restaurant")
    form = PromotionForm(
        _form_data(
            price_condition_present="1", price_condition_kind="x_for_y", price_condition_n="2"
        ),
        tenant=tenant,
    )
    assert not form.is_valid()
    assert "price_condition_kind" in form.errors
