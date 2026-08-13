"""MEN-9: «корзина = запрос на просчёт» (решение владельца для кейтеринга).

Корзина и чекаут работают, но заказ — НЕОБЯЗЫВАЮЩИЙ запрос: оплаты нет,
§312j-кнопка («Zahlungspflichtig bestellen») заменяется на «Unverbindlich
anfragen», письмо и подтверждение говорят языком заявки, а не купли-продажи.
Обычные тенанты не задеты (замки паритета).
"""

import uuid
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.orders import public_views
from apps.orders.models import Order
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="post", data=None, session=None, tenant=None):
    request = getattr(RequestFactory(), method)("/warenkorb/", data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.5"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if session:
        request.session.update(session)
    request.tenant = tenant if tenant is not None else TenantFactory.build()
    return request


def _quote_tenant(**kw):
    return TenantFactory.build(site_config={"quote_cart": True}, **kw)


def _filled_cart(tenant):
    product = ProductFactory(base_price=Decimal("24.00"), name={"de": "Buffet"})
    add = _req(data={"product": str(product.pk), "qty": "20"}, tenant=tenant)
    public_views.cart_add(add)
    return add.session["cart"]


def test_quote_cart_replaces_312j_button():
    """§312j требует называть платёжную обязанность — но её ЗДЕСЬ НЕТ, значит
    «Zahlungspflichtig bestellen» было бы ложью."""
    tenant = _quote_tenant()
    cart = _filled_cart(tenant)
    body = public_views.cart_view(
        _req(method="get", session={"cart": cart}, tenant=tenant)
    ).content.decode()
    assert "Unverbindlich anfragen" in body
    assert "Zahlungspflichtig bestellen" not in body
    assert "keine Zahlungspflicht" in body


def test_normal_tenant_keeps_312j_button():
    """Паритет: у обычного магазина кнопка та же (замок E-2/§312j не тронут)."""
    tenant = TenantFactory.build()
    cart = _filled_cart(tenant)
    body = public_views.cart_view(
        _req(method="get", session={"cart": cart}, tenant=tenant)
    ).content.decode()
    assert "Zahlungspflichtig bestellen" in body
    assert "Unverbindlich anfragen" not in body


def test_quote_checkout_creates_unbound_request_order():
    tenant = _quote_tenant()
    cart = _filled_cart(tenant)
    public_views.checkout(
        _req(
            data={"name": "Anna Sommer", "email": "a@test.de"},
            session={"cart": cart},
            tenant=tenant,
        )
    )
    order = Order.objects.get()
    assert order.is_quote is True and order.source_channel == "quote"
    assert order.payment_method == Order.METHOD_ON_SITE  # оплаты нет
    assert order.payment_state == "unpaid"
    assert order.total == Decimal("480.00")  # 24,00 × 20 — просчёт считается как обычно


def test_quote_order_email_uses_request_wording():
    """Письмо клиенту — «Anfrage», без языка Kaufvertrag (ремап как у Anprobe)."""
    from apps.orders import notifications

    tenant = _quote_tenant()
    cart = _filled_cart(tenant)
    public_views.checkout(
        _req(data={"name": "Anna", "email": "a@test.de"}, session={"cart": cart}, tenant=tenant)
    )
    order = Order.objects.get()
    assert notifications._CUSTOMER_TEMPLATES["quote_created"] == "order_quote_created"

    from django.template.loader import render_to_string

    body = render_to_string(
        "emails/order_quote_created.txt", {"order": order, "items": order.items.all()}
    )
    assert "unverbindliche Anfrage" in body and "KEIN Kaufvertrag" in body
    assert "Zahlungspflichtig" not in body


def test_quote_confirmation_page_speaks_request_language():
    tenant = _quote_tenant()
    cart = _filled_cart(tenant)
    public_views.checkout(
        _req(data={"name": "Anna", "email": "a@test.de"}, session={"cart": cart}, tenant=tenant)
    )
    order = Order.objects.get()
    body = public_views.order_confirmation(
        _req(method="get", tenant=tenant), code=order.reference_code
    ).content.decode()
    assert "Ihre Anfrage ist da" in body
    assert "Thank you! Your order is in." not in body


def test_quote_cart_hides_payment_picker():
    """Выбирать нечего: в режиме просчёта пикер способов оплаты не рендерим."""
    tenant = _quote_tenant(vorkasse_enabled=True, bank_iban="DE02120300000000202051")
    cart = _filled_cart(tenant)
    ctx_body = public_views.cart_view(
        _req(method="get", session={"cart": cart}, tenant=tenant)
    ).content.decode()
    assert 'name="payment"' not in ctx_body


def test_quote_cart_key_is_presence_minimal():
    """golden: ключа нет, пока режим выключен."""
    from apps.tenants import siteconfig

    assert "quote_cart" not in siteconfig.normalize({})
    assert siteconfig.normalize({"quote_cart": True})["quote_cart"] is True
