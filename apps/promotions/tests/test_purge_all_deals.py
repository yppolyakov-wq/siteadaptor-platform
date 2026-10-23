"""KA-H11 (аудит KA-9 №6): DSGVO-обезличивание не трогает клиента с живой сделкой.

До фикса активность считалась только по резервам и броням номеров: клиент со
старым резервом и действующим заказом/записью/заявкой/билетом обезличивался
посреди сделки. Набор кандидатов (есть резерв или бронь номера) НЕ расширяется."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.booking.models import Booking, Resource
from apps.events.models import Event, Ticket
from apps.finance.models import Invoice
from apps.jobs.models import Job
from apps.orders.models import Offer, Order
from apps.promotions.models import Customer, Reservation
from apps.promotions.services import cancel, reserve
from apps.promotions.tasks import purge_due_customers
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db

OLD = timedelta(days=400)


def _ref(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


def _old_customer():
    """Клиент со старым завершённым резервом — кандидат на обезличивание."""
    res = reserve(PromotionFactory(available_quantity=5), name="Anna", email="anna@t.de")
    cancel(res)
    Reservation.objects.filter(pk=res.pk).update(updated_at=timezone.now() - OLD)
    return Customer.objects.get(pk=res.customer_id)


def _age(model, obj):
    model.objects.filter(pk=obj.pk).update(updated_at=timezone.now() - OLD)


def _order(customer, status):
    return Order.objects.create(customer=customer, reference_code=_ref("O"), status=status)


def _booking(customer, status):
    start = timezone.now() - OLD
    return Booking.objects.create(
        resource=Resource.objects.create(name=_ref("R")),
        customer=customer,
        reference_code=_ref("T"),
        start=start,
        end=start + timedelta(hours=1),
        status=status,
    )


def _job(customer, status):
    return Job.objects.create(customer=customer, title="Bad", status=status)


def _ticket(customer, status):
    event = Event.objects.create(
        title="WS", starts_at=timezone.now() + timedelta(days=5), status=Event.STATUS_PUBLISHED
    )
    return Ticket.objects.create(
        event=event, customer=customer, reference_code=_ref("E"), status=status
    )


def _purged(customer):
    customer.refresh_from_db()
    return customer.email == ""


def test_old_reservation_and_done_order_is_purged():
    customer = _old_customer()
    _age(Order, _order(customer, "picked_up"))
    assert purge_due_customers() == 1
    assert _purged(customer)


def test_recent_order_keeps_customer():
    customer = _old_customer()
    _order(customer, "picked_up")  # свежая активность
    assert purge_due_customers() == 0
    assert not _purged(customer)


@pytest.mark.parametrize(
    "make,model,status",
    [
        (_order, Order, "ready"),
        (_order, Order, "new"),
        (_booking, Booking, "confirmed"),
        (_job, Job, "quoted"),
        (_ticket, Ticket, "pending"),
    ],
)
def test_open_deal_keeps_customer_even_when_old(make, model, status):
    customer = _old_customer()
    _age(model, make(customer, status))
    assert purge_due_customers() == 0
    assert not _purged(customer)


def test_open_offer_keeps_customer():
    customer = _old_customer()
    offer = Offer.objects.create(customer=customer, customer_email="anna@t.de")
    _age(Offer, offer)
    assert purge_due_customers() == 0


def test_issued_invoice_keeps_customer():
    customer = _old_customer()
    invoice = Invoice.objects.create(
        recipient="Anna", lines=[], gross=Decimal("10.00"), customer=customer, status="issued"
    )
    _age(Invoice, invoice)
    assert purge_due_customers() == 0


def test_customer_with_only_old_orders_is_not_a_candidate():
    """Замок «без расширения»: клиент без резерва/брони номера под purge не попадает."""
    customer = Customer.objects.create(name="Bert", email="bert@t.de")
    _age(Order, _order(customer, "picked_up"))
    assert purge_due_customers() == 0
    assert not _purged(customer)


def test_custom_active_order_status_keeps_customer(monkeypatch):
    from apps.core import status_registry
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(
        site_config={
            "status_defs": {
                "order": [{"code": "in_pack", "role": "active", "stage": "in_progress"}]
            }
        }
    )
    monkeypatch.setattr(status_registry, "_current_tenant", lambda: tenant)
    customer = _old_customer()
    _age(Order, _order(customer, "in_pack"))
    assert purge_due_customers() == 0
