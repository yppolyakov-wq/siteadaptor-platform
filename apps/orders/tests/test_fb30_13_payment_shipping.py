"""FB-30.13: зависимость «оплата ↔ доставка» задаётся в способе доставки."""

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import QueryDict
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.core import payment_methods as pm
from apps.orders import delivery_choice, public_views, shipping_admin
from apps.orders.models import Order, ShippingMethod
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
ADDR = {"street": "Hauptstr. 1", "plz": "42651", "city": "Solingen"}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    kw.setdefault("vorkasse_enabled", True)
    kw.setdefault("bank_iban", "DE89370400440532013000")
    kw.setdefault("bank_holder", "Laden")
    return TenantFactory.build(**kw)


def _checkout(tenant, data):
    product = ProductFactory(base_price=Decimal("10.00"))
    request = RequestFactory().post("/warenkorb/bestellen/", {"name": "K", **data})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.session["cart"] = {str(product.pk): 1}
    request.tenant = tenant
    return public_views.checkout(request), request


def test_incompatible_pair_is_refused_and_no_order_is_made():
    dhl = ShippingMethod.objects.create(kind="carrier", carrier="dhl", payment_methods=["vorkasse"])
    resp, request = _checkout(_tenant(), {"fulfillment": str(dhl.pk), "payment": "on_site", **ADDR})
    assert resp.status_code == 302 and not Order.objects.exists()
    assert [str(m) for m in get_messages(request)] == [str(pm.PAIR_REFUSED)]


def test_compatible_pair_and_empty_payment_take_the_first_allowed():
    dhl = ShippingMethod.objects.create(kind="carrier", carrier="dhl", payment_methods=["vorkasse"])
    _checkout(_tenant(), {"fulfillment": str(dhl.pk), **ADDR})
    assert Order.objects.get().payment_method == Order.METHOD_VORKASSE


def test_pickup_without_rule_keeps_every_method():
    ShippingMethod.objects.create(kind="carrier", carrier="dhl", payment_methods=["vorkasse"])
    pick = ShippingMethod.objects.create(kind="pickup")
    _checkout(_tenant(), {"fulfillment": str(pick.pk), "payment": "on_site"})
    assert Order.objects.get().payment_method == Order.METHOD_ON_SITE


def test_shipping_option_without_a_usable_payment_is_not_offered():
    pick = ShippingMethod.objects.create(kind="pickup")
    dhl = ShippingMethod.objects.create(kind="carrier", carrier="dhl", payment_methods=["stripe"])
    keys = [o["key"] for o in delivery_choice.context(_tenant(), 1000)["shipping_options"]]
    assert keys == [str(pick.pk)], "Stripe не подключён — DHL нечем оплатить, его не видно"
    assert str(dhl.pk) not in keys


def test_options_carry_their_rule_for_the_picker():
    ShippingMethod.objects.create(kind="pickup")
    ShippingMethod.objects.create(kind="carrier", carrier="dhl", payment_methods=["vorkasse"])
    pays = [o["pays"] for o in delivery_choice.context(_tenant(), 1000)["shipping_options"]]
    assert pays == ["", "vorkasse"]


def _post(**data):
    q = QueryDict(mutable=True)
    for k, v in data.items():
        q.setlist(k, v if isinstance(v, list) else [v])
    return q


def test_form_saves_known_codes_all_means_no_rule_none_is_an_error():
    parsed = shipping_admin.parse(
        _post(sec_payments="1", payment_methods=["vorkasse", "x"]), "courier"
    )
    assert parsed.values["payment_methods"] == ["vorkasse"]
    parsed = shipping_admin.parse(
        _post(sec_payments="1", payment_methods=list(pm.METHODS)), "courier"
    )
    assert parsed.values["payment_methods"] == []
    parsed = shipping_admin.parse(_post(sec_payments="1"), "courier")
    assert parsed.errors
    parsed = shipping_admin.parse(_post(payment_methods=["vorkasse"]), "courier")
    assert "payment_methods" not in parsed.values, "без сентинела поле не трогается (W0)"


def test_cart_shows_a_single_payment_method_as_a_line():
    product = ProductFactory(base_price=Decimal("10.00"))
    request = RequestFactory().get("/warenkorb/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.session["cart"] = {str(product.pk): 1}
    request.tenant = TenantFactory.build(disabled_modules=[])
    body = public_views.cart_view(request).content.decode()
    assert "data-pay-single" in body and 'name="payment"' not in body


def test_offer_without_payment_takes_the_first_method_allowed_by_its_shipping():
    from importlib import import_module

    from django.conf import settings as dj_settings

    from apps.inbox.services import start_conversation
    from apps.orders import offers

    dhl = ShippingMethod.objects.create(kind="carrier", carrier="dhl", payment_methods=["vorkasse"])
    conv = start_conversation(subject="F", body="Hi", email="k@test.de", name="K")
    offer = offers.send_offer(conv, lines=[{"title": "X", "unit_price": "45.00", "qty": 1}])
    data = {"action": "accept", "name": "K", "email": "k@t.de", "fulfillment": str(dhl.pk), **ADDR}
    request = RequestFactory().post("/o/x/", data)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = _tenant()
    public_views.offer_page(request, token=offer.token)
    assert Order.objects.get().payment_method == Order.METHOD_VORKASSE


def test_forged_hidden_shipping_method_is_refused_at_checkout():
    """Способ «только Stripe» без подключённого Stripe витрина прячет; подставленный ключ —
    отказ, а не заказ с другой оплатой."""
    dhl = ShippingMethod.objects.create(kind="carrier", carrier="dhl", payment_methods=["stripe"])
    resp, request = _checkout(_tenant(), {"fulfillment": str(dhl.pk), **ADDR})
    assert not Order.objects.exists()
    assert [str(m) for m in get_messages(request)] == [str(pm.PAIR_REFUSED)]


def test_all_ticked_keeps_on_site_even_with_the_old_switch_off():
    tenant = _tenant(site_config={"payment_on_site": {"delivery": False}})
    values = {"payment_methods": []}
    shipping_admin.keep_legacy_rule(tenant, "courier", values)
    assert values["payment_methods"] == list(pm.METHODS)
    method = SimpleNamespace(kind="courier", payment_methods=values["payment_methods"])
    assert pm.ON_SITE in pm.allowed_with(method, tenant)
    pickup = {"payment_methods": []}
    shipping_admin.keep_legacy_rule(tenant, "pickup", pickup)
    assert pickup["payment_methods"] == []


def test_form_redisplay_keeps_the_owners_ticks():
    from apps.orders import shipping_views

    post = _post(sec_payments="1", payment_methods=["vorkasse", "invoice"])
    rows = shipping_views._pay_rows(_tenant(), None, "courier", post)
    assert {r["code"] for r in rows if r["checked"]} == {"vorkasse", "invoice"}
    rows = shipping_views._pay_rows(_tenant(), None, "courier", _post(sec_payments="1"))
    assert not any(r["checked"] for r in rows), "пустой выбор не подменяется сохранённым"
