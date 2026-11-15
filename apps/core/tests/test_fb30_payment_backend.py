"""FB-30.12a: способы оплаты — подписи «Vor Ort» по виду сделки и подвиду (наличные / карта),
выключение «Vor Ort» для доставки. Решения владельца 2026-11-15: «оплату на месте» можно
выключить только для заказов с доставкой и только когда остаётся другой способ для частного
лица; ноль способов на чекауте — никогда. Подписи в `choices` миграций не трогаются."""

import itertools
from types import SimpleNamespace

import pytest

from apps.core import payment_methods as pm
from apps.tenants import siteconfig


def _tenant(on_site=None, **flags):
    base = {
        "payments_enabled": False,
        "stripe_connect_id": "",
        "orders_prepay": False,
        "vorkasse_enabled": False,
        "bank_iban": "",
        "invoice_b2b_enabled": False,
        "site_config": {"payment_on_site": on_site} if on_site is not None else {},
    }
    base.update(flags)
    return SimpleNamespace(**base)


def test_without_new_arguments_nothing_changes():
    """Снимок: прежние вызовы дают прежний список при любых флагах."""
    for vk, iban, inv in itertools.product((False, True), ("", "DE89"), (False, True)):
        t = _tenant(vorkasse_enabled=vk, bank_iban=iban, invoice_b2b_enabled=inv,
                    on_site={"delivery": False})  # fmt: skip
        for kind in pm.KINDS:
            for ct in (pm.PRIVATE, pm.COMPANY):
                methods = pm.available(t, kind, customer_type=ct)
                assert methods[-1] == pm.ON_SITE, (kind, ct)


def test_on_site_off_for_delivery_only_when_another_method_remains():
    off = {"delivery": False}
    alone = _tenant(on_site=off)
    assert pm.available(alone, "order", fulfillment="delivery") == [pm.ON_SITE], "ноль — никогда"
    vk = _tenant(on_site=off, vorkasse_enabled=True, bank_iban="DE89")
    assert pm.available(vk, "order", fulfillment="delivery") == [pm.VORKASSE]
    assert pm.ON_SITE in pm.available(vk, "order", fulfillment="pickup")
    assert pm.ON_SITE in pm.available(vk, "booking", fulfillment="delivery")
    # счёт частному лицу не положен — он не спасает от нуля способов
    inv = _tenant(on_site=off, invoice_b2b_enabled=True)
    assert pm.available(inv, "order", fulfillment="delivery") == [pm.ON_SITE]


def test_on_site_stays_for_delivery_by_default():
    vk = _tenant(vorkasse_enabled=True, bank_iban="DE89")
    assert pm.ON_SITE in pm.available(vk, "order", fulfillment="delivery")


def test_labels_follow_the_deal_kind_and_the_sub_kind():
    assert "Abholung" not in str(pm.label(pm.ON_SITE, "booking"))
    assert pm.label(pm.ON_SITE) == pm.METHOD_LABELS[pm.ON_SITE]
    assert str(pm.label(pm.ON_SITE, "order", fulfillment="delivery")) == "Zahlung bei Lieferung"
    assert str(pm.label(pm.ON_SITE, "stay")) == "Zahlung bei Anreise"
    card = _tenant(on_site={"kind": "card"})
    assert str(pm.label(pm.ON_SITE, "booking", tenant=card)) == "Zahlung vor Ort (Karte)"
    both = _tenant(on_site={"kind": "both"})
    assert "bar oder Karte" in str(pm.label(pm.ON_SITE, "order", tenant=both))
    assert str(pm.label(pm.VORKASSE, "stay")) == str(pm.METHOD_LABELS[pm.VORKASSE])


def test_migration_choices_keep_their_text():
    """Подпись в `choices` записана в миграциях пяти приложений — менять её нельзя."""
    assert str(pm.METHOD_LABELS[pm.ON_SITE]) == "Barzahlung bei Abholung"


def test_payment_on_site_survives_normalize():
    cfg = siteconfig.normalize({"payment_on_site": {"kind": "card", "delivery": False, "x": 1}})
    assert cfg["payment_on_site"] == {"kind": "card", "delivery": False}
    assert "payment_on_site" not in siteconfig.normalize({"payment_on_site": "junk"})
    cfg = siteconfig.normalize({"payment_on_site": {"kind": "gold"}})
    assert cfg["payment_on_site"] == {"kind": "", "delivery": True}


# ─────────────────────── чекаут корзины ───────────────────────


@pytest.fixture
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _checkout(tenant, payment, fulfillment):
    import uuid
    from decimal import Decimal

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.catalog.tests.factories import ProductFactory
    from apps.orders import public_views

    product = ProductFactory(base_price=Decimal("20.00"))
    data = {"name": "Kunde", "email": "k@test.de", "payment": payment}
    data.update(fulfillment=fulfillment, street="Hauptstr. 1", plz="50667", city="Köln")
    request = RequestFactory().post("/warenkorb/bestellen/", data)
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.session.update({"cart": {str(product.pk): 1}})
    request.tenant = tenant
    return public_views.checkout(request), request


def _shop(**over):
    from apps.tenants.tests.factories import TenantFactory

    over.setdefault("disabled_modules", [])
    return TenantFactory(
        delivery_enabled=True,
        delivery_fee_cents=0,
        delivery_min_cents=0,
        vorkasse_enabled=True,
        bank_holder="Laden",
        bank_iban="DE89370400440532013000",
        bank_bic="COBADEFFXXX",
        **over,
    )


@pytest.mark.django_db
def test_checkout_refuses_on_site_for_delivery_when_switched_off(_urlconf):
    from django.contrib.messages import get_messages

    from apps.orders.models import Order

    tenant = _shop(site_config={"payment_on_site": {"kind": "", "delivery": False}})
    resp, request = _checkout(tenant, "on_site", "delivery")
    assert resp.status_code == 302 and resp.url.endswith("/warenkorb/")
    assert not Order.objects.exists(), "заказ не создаётся, способ молча не подменяется"
    assert [str(m) for m in get_messages(request)] == [str(pm.ON_SITE_REFUSED)]


@pytest.mark.django_db
def test_checkout_keeps_on_site_for_pickup_and_by_default(_urlconf):
    from apps.orders.models import Order

    off = _shop(site_config={"payment_on_site": {"delivery": False}})
    _checkout(off, "on_site", "pickup")
    assert Order.objects.get().payment_method == Order.METHOD_ON_SITE
    Order.objects.all().delete()
    _checkout(_shop(), "on_site", "delivery")
    assert Order.objects.get().payment_method == Order.METHOD_ON_SITE


@pytest.mark.django_db
def test_picker_shows_the_label_for_the_deal_kind():
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory.build(
        vorkasse_enabled=True, bank_iban="DE89", site_config={"payment_on_site": {"kind": "both"}}
    )
    labels = {m["code"]: str(m["label"]) for m in pm.picker_context(t, "stay")["payment_methods"]}
    assert labels[pm.ON_SITE] == "Zahlung bei Anreise (bar oder Karte)"


@pytest.mark.django_db
def test_offer_acceptance_refuses_on_site_for_delivery(_urlconf):
    from importlib import import_module

    from django.conf import settings as dj_settings
    from django.contrib.messages.middleware import MessageMiddleware
    from django.test import RequestFactory

    from apps.inbox.services import start_conversation
    from apps.orders import offers, public_views
    from apps.orders.models import Order

    conv = start_conversation(subject="Frage", body="Hi", email="kunde@test.de", name="Kim")
    offer = offers.send_offer(
        conv, lines=[{"title": "Sonderanfertigung", "unit_price": "45.00", "qty": 1}]
    )
    tenant = _shop(site_config={"payment_on_site": {"delivery": False}})
    data = {"action": "accept", "name": "K", "email": "k@t.de", "payment": "on_site"}
    data.update(fulfillment="delivery", street="Hauptstr. 1", plz="50667", city="Köln")
    request = RequestFactory().post("/o/x/", data)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    from django.contrib.messages import get_messages

    resp = public_views.offer_page(request, token=offer.token)
    assert resp.status_code == 302
    assert not Order.objects.exists()
    assert [str(m) for m in get_messages(request)] == [str(pm.ON_SITE_REFUSED)]


@pytest.mark.django_db
def test_quote_cart_still_takes_delivery_requests(_urlconf):
    """Корзина-запрос (MEN-9) не платит вовсе — отказ «vor Ort» к ней не относится."""
    from apps.orders.models import Order

    tenant = _shop(site_config={"quote_cart": True, "payment_on_site": {"delivery": False}})
    _checkout(tenant, "", "delivery")
    assert Order.objects.get().payment_method == Order.METHOD_ON_SITE


def test_picker_marks_on_site_to_hide_for_delivery_only_when_switched_off():
    vk = {"vorkasse_enabled": True, "bank_iban": "DE89"}
    off = _tenant(on_site={"delivery": False}, **vk)
    rows = {r["code"]: r["no_delivery"] for r in pm.picker_rows(off, pm.available(off))}
    assert rows == {pm.VORKASSE: False, pm.ON_SITE: True}
    on = _tenant(**vk)
    assert not any(r["no_delivery"] for r in pm.picker_rows(on, pm.available(on)))
    alone = _tenant(on_site={"delivery": False})
    assert not any(r["no_delivery"] for r in pm.picker_rows(alone, pm.available(alone)))
    assert not any(
        r["no_delivery"] for r in pm.picker_rows(off, pm.available(off, "booking"), "booking")
    )
