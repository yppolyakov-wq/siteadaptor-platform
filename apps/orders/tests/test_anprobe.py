"""M3 Boutique (Click&Reserve): Anprobe-резерв = Order с TTL, свои письма,
beat-экспайр, витринная форма (план m3-click-reserve-plan-2026-07-30)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.catalog.models import Product, ProductVariant
from apps.orders.anprobe import create_anprobe
from apps.orders.models import Order
from apps.orders.tasks import expire_due_anprobe
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _product(stock=5):
    return Product.objects.create(
        name={"de": "Kleid"}, base_price=Decimal("45.00"), stock_quantity=stock
    )


def test_create_anprobe_reserves_stock_and_marks_order():
    p = _product(stock=5)
    order = create_anprobe(product=p, name="Mia", email="mia@example.de")
    p.refresh_from_db()
    assert p.stock_quantity == 4  # anti-oversell: вещь снята с остатка
    assert order.is_anprobe and order.source_channel == "anprobe"
    assert order.payment_method == "on_site" and order.fulfillment == "pickup"


def test_anprobe_variant_scoped_stock():
    p = _product(stock=None)
    v = ProductVariant.objects.create(product=p, label="M", stock_quantity=2)
    create_anprobe(product=p, variant=v, name="Mia", email="mia@example.de")
    v.refresh_from_db()
    assert v.stock_quantity == 1


def test_anprobe_created_email_is_unverbindlich():
    """Письмо created ремапится на unverbindlich-текст (KEIN Kaufvertrag) —
    юр-риск №1 из разведки: обычное письмо говорит языком договора."""
    from apps.notifications.models import Notification

    p = _product()
    order = create_anprobe(product=p, name="Mia", email="mia@example.de")
    n = Notification.objects.filter(recipient="mia@example.de").order_by("-created_at").first()
    assert n is not None
    body = (n.payload or {}).get("body", "")
    assert "unverbindliche Reservierung" in body
    assert "KEIN Kaufvertrag" in body
    assert order.reference_code in n.subject


def test_expire_due_anprobe_cancels_and_restores_stock():
    p = _product(stock=5)
    order = create_anprobe(product=p, name="Mia", email="mia@example.de")
    p.refresh_from_db()
    assert p.stock_quantity == 4
    Order.objects.filter(pk=order.pk).update(reserve_expires_at=timezone.now() - timedelta(hours=1))
    assert expire_due_anprobe() == 1
    order.refresh_from_db()
    p.refresh_from_db()
    assert order.status == "cancelled"
    assert p.stock_quantity == 5  # restore — штатный путь cancelled
    assert expire_due_anprobe() == 0  # идемпотентно


def test_public_view_creates_reservation_with_gate():
    from apps.promotions.public_views import product_anprobe_reserve

    p = _product(stock=3)
    tenant = TenantFactory.build(business_type="clothing", site_config={"anprobe": True})

    def _post(t):
        request = RequestFactory().post(
            f"/sortiment/{p.pk}/anprobe/", {"name": "Mia", "email": "mia@example.de"}
        )
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        request.tenant = t
        return product_anprobe_reserve(request, pk=p.pk)

    resp = _post(tenant)
    assert resp.status_code == 302
    assert Order.objects.filter(source_channel="anprobe").count() == 1
    # без site_config.anprobe — гейт: заказ не создаётся
    off = TenantFactory.build(business_type="clothing", site_config={})
    _post(off)
    assert Order.objects.filter(source_channel="anprobe").count() == 1


def test_detail_shows_anprobe_form_only_when_enabled():
    from apps.promotions.public_views import product_detail

    p = _product(stock=3)

    def _body(cfg):
        request = RequestFactory().get(f"/sortiment/{p.pk}/")
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        request.tenant = TenantFactory.build(business_type="clothing", site_config=cfg)
        return product_detail(request, pk=p.pk).content.decode()

    on = _body({"anprobe": True})
    assert "In der Anprobe zurücklegen" in on and f"/sortiment/{p.pk}/anprobe/" in on
    off = _body({})
    assert "In der Anprobe zurücklegen" not in off


def test_owner_is_notified_about_anprobe_reservation(monkeypatch):
    """Ревью M3 (HIGH): ремап глушил owner-ветку — владелец не узнавал о
    резерве, хотя клиенту обещано «legen wir zurück». Своё owner-письмо."""
    from apps.notifications.models import Notification
    from apps.orders import notifications as notif

    monkeypatch.setattr(notif, "_owner_email", lambda tenant: "chef@example.de")
    p = _product()
    create_anprobe(product=p, name="Mia", email="mia@example.de")
    owner = Notification.objects.filter(recipient="chef@example.de").first()
    assert owner is not None
    body = (owner.payload or {}).get("body", "")
    assert "Anprobe-Reservierung" in body
    assert "Click-&-Collect" not in body  # не язык договора купли-продажи


def test_expire_skips_paid_or_advanced_orders():
    """Ревью M3 (HIGH): гонка — оплаченный/выданный резерв не должен отменяться
    beat'ом (лок + повторная проверка под ним)."""
    p = _product(stock=5)
    paid = create_anprobe(product=p, name="Mia", email="mia@example.de")
    Order.objects.filter(pk=paid.pk).update(
        reserve_expires_at=timezone.now() - timedelta(hours=1), payment_state="paid"
    )
    advanced = create_anprobe(product=p, name="Ben", email="ben@example.de")
    Order.objects.filter(pk=advanced.pk).update(
        reserve_expires_at=timezone.now() - timedelta(hours=1), status="ready"
    )
    assert expire_due_anprobe() == 0
    paid.refresh_from_db()
    advanced.refresh_from_db()
    assert paid.status != "cancelled" and advanced.status == "ready"
