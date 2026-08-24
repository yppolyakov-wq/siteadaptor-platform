"""R7-3 (фидбэк владельца 2026-08-24): доставка и оплаты — отдельные страницы.

- «Lieferungen»: заказы с доставкой, накладная (Lieferschein-PDF) и трек-номер
  на строке; статусы меняются ТЕМ ЖЕ приёмником (board-action), своих тропинок
  к FSM нет;
- «Zahlungen»: обзор денег сделок (кто заплатил / кто должен / чем платили) —
  слой ЧТЕНИЯ, модуль finance не требуется.
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import payments_page as pay
from apps.core import views as core_views
from apps.core.modules import default_disabled_for
from apps.orders import views as order_views
from apps.orders.models import Order
from apps.promotions.models import Customer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(business_type="shop", enable=("orders",)):
    off = [m for m in default_disabled_for(business_type) if m not in enable]
    return TenantFactory(
        slug=f"r73-{uuid4().hex[:6]}",
        name="R73",
        business_type=business_type,
        disabled_modules=off,
    )


def _req(path, tenant, data=None):
    request = RequestFactory().get(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    request.user = get_user_model().objects.create_user(
        username=f"r73-{uuid4().hex[:8]}",
        email=f"r73-{uuid4().hex[:8]}@t.de",
        password="pw12345678",
    )
    return request


def _order(is_delivery=True, status=Order.STATUS_NEW, payment_state="unpaid"):
    from decimal import Decimal

    from apps.orders.models import OrderItem

    c = Customer.objects.create(name="Anna Kundin", email=f"{uuid4().hex[:6]}@t.de")
    order = Order.objects.create(
        customer=c,
        reference_code=f"O-{uuid4().hex[:6].upper()}",
        fulfillment=Order.FULFILLMENT_DELIVERY if is_delivery else Order.FULFILLMENT_PICKUP,
        status=status,
        payment_state=payment_state,
        shipping_address="Musterweg 1\n40721 Hilden",
        total=Decimal("24.90"),  # снимок итога пишет create_order; здесь — фабрика
    )
    OrderItem.objects.create(
        order=order, qty=1, unit_price=Decimal("24.90"), title_snapshot="Brotbox"
    )
    return order


# --- Lieferungen --------------------------------------------------------------
def test_deliveries_page_lists_only_deliveries_with_note_link():
    t = _tenant()
    d = _order()
    _order(is_delivery=False)  # самовывоз в списке доставок делать нечего
    html = order_views.deliveries(_req("/dashboard/orders/lieferungen/", t)).content.decode()
    assert d.reference_code in html
    assert f"/dashboard/orders/{d.pk}/lieferschein.pdf" in html  # накладная со строки
    assert "Musterweg 1" in html  # адрес виден сразу, без захода в карточку


def test_deliveries_filter_hides_shipped_by_default():
    t = _tenant()
    shipped = _order(status=Order.STATUS_SHIPPED)
    open_one = _order()
    html = order_views.deliveries(_req("/dashboard/orders/lieferungen/", t)).content.decode()
    assert open_one.reference_code in html
    assert shipped.reference_code not in html  # вид «Offen» — работа на сегодня
    all_html = order_views.deliveries(
        _req("/dashboard/orders/lieferungen/", t, {"state": ""})
    ).content.decode()
    assert shipped.reference_code in all_html


def test_deliveries_status_change_goes_through_shared_action():
    """Своих тропинок к FSM нет: форма шлёт в общий board-action, поэтому
    письмо с Sendungsnummer уходит штатно (W10-5)."""
    t = _tenant()
    o = _order(status=Order.STATUS_READY)
    html = order_views.deliveries(_req("/dashboard/orders/lieferungen/", t)).content.decode()
    assert f"/dashboard/board/order/{o.pk}/action/" in html or "board-action" in html
    assert 'name="tracking_code"' in html


# --- Zahlungen ----------------------------------------------------------------
def test_payment_rows_split_open_and_paid():
    t = _tenant()
    unpaid = _order(payment_state="unpaid")
    paid = _order(payment_state="paid")
    codes_open = {r["code"] for r in pay.payment_rows(t, "open")}
    codes_paid = {r["code"] for r in pay.payment_rows(t, "paid")}
    assert unpaid.reference_code in codes_open and paid.reference_code not in codes_open
    assert paid.reference_code in codes_paid


def test_payment_rows_skip_cancelled_deals():
    """Отменённая сделка денег не ждёт — её долг закрыт FSM (приём ERP-2)."""
    t = _tenant()
    o = _order(status=Order.STATUS_CANCELLED, payment_state="unpaid")
    assert o.reference_code not in {r["code"] for r in pay.payment_rows(t, "open")}


def test_payments_page_renders_without_finance_module():
    """Оплаты — часть продаж: страница живёт и при выключенном finance
    (он выключен у всех типов по умолчанию)."""
    t = _tenant()
    assert not t.is_module_active("finance")
    o = _order()
    html = core_views.payments_page(_req("/dashboard/zahlungen/", t)).content.decode()
    assert o.reference_code in html
    assert "Zahlungen" in html


def test_payments_summary_counts_open_amount():
    t = _tenant()
    _order(payment_state="unpaid")
    _order(payment_state="unpaid")
    summary = pay.payment_summary(t)
    assert summary["open_count"] == 2
    assert summary["open_total"] > 0


# --- обе страницы в едином реестре навигации ----------------------------------
def test_both_pages_are_in_registry_and_menu():
    from apps.core import modules, nav_registry

    urls = {e["url_name"] for e in nav_registry.palette_entries()}
    assert {"orders:deliveries", "payments-page"} <= urls
    t = _tenant()
    sales = next(it for it in modules.sidebar_nav(t) if it["nav_key"] == "board")
    kids = {c["url_name"] for c in sales["children"]}
    assert {"orders:deliveries", "payments-page"} <= kids
