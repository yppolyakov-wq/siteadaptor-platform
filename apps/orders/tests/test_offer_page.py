"""LS-3: публичная страница предложения /o/<token>/ — accept/decline/оплата.

Страница сама служит подтверждением (без гейта модуля orders — Sofort-Angebot
работает у любого архетипа): Vorkasse-реквизиты и Stripe success/cancel живут
на ней; ссылка на /bestellung/ — только при активном модуле orders.
"""

from datetime import timedelta
from decimal import Decimal
from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory
from django.utils import timezone

from apps.catalog.tests.factories import ProductFactory
from apps.inbox.services import start_conversation
from apps.orders import offers, public_views
from apps.orders.models import Offer, Order
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, tenant=None):
    request = getattr(RequestFactory(), method)("/o/x/", data or {})
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    from django.contrib.messages.middleware import MessageMiddleware

    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant if tenant is not None else TenantFactory.build(name="Laden")
    return request


def _offer(**kw):
    conv = start_conversation(subject="Frage", body="Hi", email="kunde@test.de", name="Kim")
    lines = kw.pop("lines", [{"title": "Sonderanfertigung", "unit_price": "45.00", "qty": 1}])
    return offers.send_offer(conv, lines=lines, **kw)


def test_offer_page_renders_open_state_with_accept_form():
    offer = _offer(note="Gerne bis Freitag.")
    html = public_views.offer_page(_req(), token=offer.token).content.decode()
    assert "Sonderanfertigung" in html and "45,00" in html  # DE-локаль: запятая
    assert 'name="action" value="accept"' in html
    assert 'name="action" value="decline"' in html
    assert "Gerne bis Freitag." in html
    assert 'value="kunde@test.de"' in html  # префилл из снимка треда


def test_offer_page_accept_creates_order_and_shows_confirmation():
    product = ProductFactory(base_price=Decimal("10.00"), stock_quantity=5)
    offer = _offer(
        lines=[
            {
                "kind": "product",
                "ref_id": str(product.pk),
                "title": "Torte",
                "unit_price": "8.50",
                "qty": 2,
            }
        ]
    )
    resp = public_views.offer_page(
        _req("post", {"action": "accept", "name": "Kim", "email": "kunde@test.de"}),
        token=offer.token,
    )
    assert resp.status_code == 302 and f"/o/{offer.token}/" in resp["Location"]
    offer.refresh_from_db()
    assert offer.status == Offer.STATUS_ACCEPTED
    order = offer.order
    assert order.payment_method == Order.METHOD_ON_SITE  # единственный способ — дефолт
    product.refresh_from_db()
    assert product.stock_quantity == 3
    # Страница после принятия — подтверждение (без модуля orders ссылки нет).
    tenant = TenantFactory.build(name="Laden", disabled_modules=["orders"])
    html = public_views.offer_page(_req(tenant=tenant), token=offer.token).content.decode()
    assert "angenommen" in html and order.reference_code in html
    assert "/bestellung/" not in html  # модуль выключен → без ссылки на заказ


def test_offer_page_vorkasse_shows_requisites():
    tenant = TenantFactory.build(
        name="Laden", vorkasse_enabled=True, bank_iban="DE02120300000000202051"
    )
    offer = _offer()
    resp = public_views.offer_page(
        _req(
            "post",
            {"action": "accept", "name": "K", "email": "k@t.de", "payment": "vorkasse"},
            tenant=tenant,
        ),
        token=offer.token,
    )
    assert resp.status_code == 302
    offer.refresh_from_db()
    assert offer.order.payment_method == Order.METHOD_VORKASSE
    html = public_views.offer_page(_req(tenant=tenant), token=offer.token).content.decode()
    assert "DE02120300000000202051" in html
    assert offer.order.reference_code in html  # Verwendungszweck


def test_offer_page_decline():
    offer = _offer()
    public_views.offer_page(_req("post", {"action": "decline"}), token=offer.token)
    offer.refresh_from_db()
    assert offer.status == Offer.STATUS_DECLINED
    html = public_views.offer_page(_req(), token=offer.token).content.decode()
    assert "abgelehnt" in html and 'value="accept"' not in html


def test_offer_page_expired_hides_forms():
    offer = _offer(valid_until=timezone.localdate() - timedelta(days=1))
    html = public_views.offer_page(_req(), token=offer.token).content.decode()
    assert "abgelaufen" in html.lower()
    assert 'value="accept"' not in html
    # POST на истёкшее — статус не меняется
    public_views.offer_page(_req("post", {"action": "accept", "name": "K"}), token=offer.token)
    offer.refresh_from_db()
    assert offer.status == Offer.STATUS_OPEN and offer.order is None


def test_customer_thread_shows_offer_card():
    from apps.inbox import public_views as inbox_public

    offer = _offer()
    conv = offer.conversation
    request = _req(tenant=TenantFactory.build(name="Laden"))
    html = inbox_public.thread(request, token=conv.public_token).content.decode()
    assert "Persönliches Angebot" in html
    assert f"/o/{offer.token}/" in html
