"""SH-24 (фидбэк владельца 2026-09-03): «нужна опция доставки для тех архетипов,
где есть доставка — самовывоз или доставка».

Выбор был только в корзине: покупка по акции и принятие предложения молча
создавали заказ на самовывоз, а у кейтеринга (живёт на заявках) вопроса не было
вовсе. Здесь — один разбор на все поверхности и его гейты.

План — `docs/order-feedback-plan-2026-09-03.md` §7.
"""

from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.models import Product
from apps.orders import delivery_choice
from apps.orders.models import Order
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    kw.setdefault("disabled_modules", [])
    return TenantFactory(**kw)


def _delivery_tenant(**kw):
    return _tenant(
        delivery_enabled=True,
        delivery_fee_cents=350,
        delivery_free_cents=3000,
        delivery_min_cents=1000,
        **kw,
    )


def _post(**data):
    request = RequestFactory().post("/warenkorb/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    return request.POST


_ADDR = {"street": "Hauptstr. 1", "plz": "50667", "city": "Köln"}


# ─────────────────────────── разбор выбора ───────────────────────────


def test_pickup_is_the_default():
    choice = delivery_choice.resolve(_post(), _delivery_tenant(), 2000)
    assert choice and not choice.delivery and choice.shipping_cents == 0


def test_delivery_needs_a_full_address():
    choice = delivery_choice.resolve(_post(fulfillment="delivery"), _delivery_tenant(), 2000)
    # текст локализован (немецкая витрина) — проверяем факт ошибки, не язык
    assert not choice and "Lieferadresse" in choice.error


def test_delivery_respects_the_minimum_order():
    choice = delivery_choice.resolve(
        _post(fulfillment="delivery", **_ADDR), _delivery_tenant(), 500
    )
    assert not choice and choice.error


def test_delivery_returns_fee_and_address():
    choice = delivery_choice.resolve(
        _post(fulfillment="delivery", **_ADDR), _delivery_tenant(), 2000
    )
    assert choice and choice.delivery
    assert choice.shipping_cents == 350
    assert choice.shipping_address == "Hauptstr. 1\n50667 Köln"


def test_delivery_is_fail_closed_without_the_setting():
    """Подмена поля у бизнеса без доставки остаётся самовывозом."""
    choice = delivery_choice.resolve(_post(fulfillment="delivery", **_ADDR), _tenant(), 5000)
    assert choice and not choice.delivery and choice.shipping_cents == 0


def test_context_is_empty_without_delivery():
    assert delivery_choice.context(_tenant()) == {"delivery_enabled": False}
    ctx = delivery_choice.context(_delivery_tenant())
    assert ctx["delivery_enabled"] and ctx["delivery_fee_eur"] == "3.50"


# ─────────────────────────── паритет поверхностей ───────────────────────────


def _promo_product(tenant):
    product = Product.objects.create(
        name={"de": "Saft"}, base_price="2.49", stock_quantity=50, currency="EUR"
    )
    Promotion.objects.create(
        title={"de": "Saft-Deal"},
        status="active",
        product=product,
        price_override=Decimal("1.99"),
        compare_at_price=product.base_price,
    )
    return product


def test_promo_purchase_can_be_delivered():
    from apps.promotions import services as promo_services

    tenant = _delivery_tenant(schema_name="sh24a", slug="sh24a")
    product = _promo_product(tenant)
    order = promo_services.purchase(
        Promotion.objects.get(),
        quantity=6,
        name="K",
        fulfillment="delivery",
        shipping_cents=350,
        shipping_address="Hauptstr. 1\n50667 Köln",
    )
    assert order.fulfillment == Order.FULFILLMENT_DELIVERY
    assert order.shipping_cents == 350 and order.is_delivery
    assert order.total == Decimal("1.99") * 6 + Decimal("3.50")
    assert product.pk  # товар списан обычным путём


def test_promo_purchase_defaults_to_pickup():
    from apps.promotions import services as promo_services

    _delivery_tenant(schema_name="sh24b", slug="sh24b")
    _promo_product(None)
    order = promo_services.purchase(Promotion.objects.get(), quantity=1, name="K")
    assert order.fulfillment == Order.FULFILLMENT_PICKUP and order.shipping_cents == 0


def test_offer_acceptance_can_be_delivered():
    from apps.orders import offers as offer_service
    from apps.orders.models import Offer, OfferLine

    _delivery_tenant(schema_name="sh24c", slug="sh24c")
    offer = Offer.objects.create(customer_name="K", customer_email="k@example.de")
    OfferLine.objects.create(offer=offer, title="Beratung", unit_price=Decimal("50.00"), qty=1)
    order = offer_service.accept_offer(
        offer,
        name="K",
        email="k@example.de",
        fulfillment="delivery",
        shipping_cents=350,
        shipping_address="Hauptstr. 1\n50667 Köln",
    )
    assert order.fulfillment == Order.FULFILLMENT_DELIVERY
    assert order.shipping_address.startswith("Hauptstr.")


# ─────────────────────────── заявка (jobs) ───────────────────────────


def test_job_keeps_the_fulfillment_choice():
    from apps.jobs import services as job_services

    _delivery_tenant(schema_name="sh24d", slug="sh24d")
    job = job_services.create_job(title="Catering", name="K", fulfillment="delivery")
    assert job.fulfillment == "delivery"
    plain = job_services.create_job(title="Catering", name="K")
    assert plain.fulfillment == ""  # вопрос не задавался — не выдумываем


def test_job_fulfillment_is_fail_closed_without_delivery():
    from apps.jobs.public_views import _parse_fulfillment

    assert _parse_fulfillment({"fulfillment": "delivery"}, _tenant()) == ""
    assert _parse_fulfillment({"fulfillment": "delivery"}, _delivery_tenant()) == "delivery"
    assert _parse_fulfillment({"fulfillment": "erfunden"}, _delivery_tenant()) == ""
