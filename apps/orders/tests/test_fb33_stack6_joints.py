"""FB-33 стопка 6: стык C5 (вкладка «Felder» корзины в окне блока) × M2i-7 (онлайн-оплата
без e-mail в форме, адрес — из вебхука Stripe).

Путь владельца и гостя целиком: в окне блока (хост `cart`, строка `form`, вкладка `felder`)
e-mail «Nicht fragen» → «Speichern» → на `/warenkorb/` поля e-mail нет → заказ с онлайн-оплатой
уходит в Stripe без адреса → `checkout.session.completed` (`paid`) с `customer_details.email`
записывает адрес клиенту, письма «created» и «confirmed» — по разу. Подсказка «Bestätigung an
die E-Mail aus der Zahlung» видна во вкладке, когда онлайн-оплата у бизнеса доступна.
"""

import pytest
from django.db import connection
from django.utils import translation

from apps.catalog.tests.factories import ProductFactory
from apps.core import form_spec
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m2i34_c5_window import (
    EMAIL_HINT_ID,
    STRIPE_HINT,
    WINDOW,
    _edit,
    _part,
    _saved,
)
from apps.orders import public_views
from apps.orders.models import Order
from apps.orders.tests.test_fb33_m2i7_payer_email import ACCOUNT, PAYER, _hook, _mails
from apps.orders.tests.test_fb33_m2i34_checkout import _cart, _checkout_form
from apps.orders.tests.test_payment_methods import _configure, _pub_req
from apps.promotions.models import Customer
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(settings):
    """Магазин текущей схемы с онлайн-оплатой: окно, витрина и вебхук — один бизнес."""
    _configure(settings)
    return TenantFactory(
        schema_name=connection.schema_name,
        business_type="online_shop",
        disabled_modules=[],
        site_config={},
        orders_prepay=True,
        payments_enabled=True,
        stripe_connect_id=ACCOUNT,
    )


def test_window_shows_the_payment_email_hint_when_online_payment_is_available(shop):
    part = _part(Browser(shop).get(WINDOW))
    assert STRIPE_HINT in part and f'aria-describedby="{EMAIL_HINT_ID}"' in part


def test_email_off_in_window_then_online_order_gets_the_payer_email(shop, settings, monkeypatch):
    # 1. окно блока: e-mail «Nicht fragen» → «Speichern»
    b = Browser(shop)
    resp, _msgs = _edit(b, mode_email="off")
    assert resp.status_code == 302
    resp, msgs = b.post(seite="cart", op="save")
    assert resp.status_code == 302 and msgs
    assert form_spec.mode_of(siteconfig.normalize(_saved(shop)), "checkout", "email") == "off"

    # 2. витрина /warenkorb/: поля e-mail нет
    settings.ROOT_URLCONF = "config.urls_tenant"
    shop.refresh_from_db()
    with translation.override("de"):
        form = _checkout_form(_cart(shop))
    assert 'name="email"' not in form and 'name="name"' in form

    # 3. оформление с онлайн-оплатой: заказ без адреса уходит в Stripe
    seen = []
    monkeypatch.setattr(
        public_views.order_payments,
        "order_checkout_url",
        lambda o, t, **kw: seen.append(o.pk) or "https://stripe/x",
    )
    product = ProductFactory()
    request = _pub_req(
        {"name": "Kunde", "payment": Order.METHOD_STRIPE},
        tenant=shop,
        session={"cart": {str(product.pk): 1}},
    )
    resp = public_views.checkout(request)
    order = Order.objects.get()
    assert resp.url == "https://stripe/x" and seen == [order.pk]
    assert order.payment_method == Order.METHOD_STRIPE
    assert Customer.objects.get(pk=order.customer_id).email == ""
    assert not _mails(order, "created").exists()

    # 4. вебхук paid с адресом плательщика: адрес — клиенту, письма — по разу (и при повторе)
    _hook(order)
    _hook(order)
    assert Customer.objects.get(pk=order.customer_id).email == PAYER
    assert order.payment_state == Order.PAYMENT_PAID and order.status == Order.STATUS_CONFIRMED
    for event in ("created", "confirmed"):
        assert [m.recipient for m in _mails(order, event)] == [PAYER], event
