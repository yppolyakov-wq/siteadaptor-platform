"""C1 — утренний дайджест владельцу: сбор метрик, гейты (пустой день/час/opt-out),
дедуп по дате, содержимое письма."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core import digest, tasks
from apps.notifications.models import Notification
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(**kw):
    kw.setdefault("owner_email", "chef@test.de")
    return TenantFactory(**kw)  # схема/slug — уникальные из фабрики


def _seed_activity():
    from apps.booking.models import Booking, Resource
    from apps.finance.models import RevenueEntry
    from apps.orders.models import Order
    from apps.promotions.models import Customer

    RevenueEntry.objects.create(
        date=timezone.localdate() - timedelta(days=1), amount=Decimal("123.45")
    )
    customer = Customer.objects.create(name="K", email="k@test.de")
    resource = Resource.objects.create(name="Stuhl 1")
    start = timezone.localtime().replace(hour=23, minute=59)
    Booking.objects.create(
        resource=resource, customer=customer, start=start, end=start + timedelta(hours=1)
    )
    Order.objects.create(customer=customer, total=Decimal("5.00"))


def test_collect_digest_metrics_and_empty_day():
    tenant = _tenant()
    assert digest.collect_digest(tenant) is None  # пустой день → не шлём
    _seed_activity()
    data = digest.collect_digest(tenant)
    assert data["revenue_yesterday"] == Decimal("123.45")
    assert data["bookings_today"] == 1 and data["bookings_pending"] == 1
    assert data["orders_new"] == 1


def test_send_digest_email_content_and_dedupe():
    tenant = _tenant()
    _seed_activity()
    assert tasks.send_digest_for_tenant(tenant, force_hour=True) is True
    n = Notification.objects.get(type="owner_digest")
    assert n.recipient == "chef@test.de"
    assert "Tagesüberblick" in n.subject
    body = n.payload["body"]
    assert "123,45" in body or "123.45" in body
    assert "1 Termin(e)" in body
    assert "1 neue Bestellung(en)" in body
    # дедуп: второй прогон в тот же день письмо не плодит
    assert tasks.send_digest_for_tenant(tenant, force_hour=True) is False
    assert Notification.objects.filter(type="owner_digest").count() == 1


def test_digest_gates_optout_hour_and_no_email():
    _seed_activity()
    off = _tenant(owner_digest_enabled=False)
    assert tasks.send_digest_for_tenant(off, force_hour=True) is False
    no_mail = _tenant(owner_email="")
    assert tasks.send_digest_for_tenant(no_mail, force_hour=True) is False
    # гейт часа: вне DIGEST_HOUR без force не шлём (тест стабилен в любой час —
    # подменяем DIGEST_HOUR на «не текущий» локальный час)
    tenant = _tenant()
    real_hour = timezone.localtime().hour
    old = digest.DIGEST_HOUR
    digest.DIGEST_HOUR = (real_hour + 3) % 24
    try:
        assert tasks.send_digest_for_tenant(tenant) is False
    finally:
        digest.DIGEST_HOUR = old
