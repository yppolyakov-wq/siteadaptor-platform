"""KA-12 E6.1: запрос клиента по DSGVO — выгрузка (Art. 15/20) и удаление (Art. 17)."""

import io
import json
import uuid
import zipfile
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.crm import dsgvo, views
from apps.crm.models import CustomerNote
from apps.promotions.models import Customer

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, owner=True):
    from apps.core.models import Membership

    request = getattr(RequestFactory(), method)("/crm/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    user = get_user_model().objects.create_user(
        username=f"u{uuid.uuid4().hex[:10]}", password="pw12345678"
    )
    Membership.objects.create(
        user=user, role=Membership.ROLE_OWNER if owner else Membership.ROLE_STAFF
    )
    request.user = user
    return request


def _customer(**kw):
    kw.setdefault("name", "Erika Muster")
    kw.setdefault("email", "erika@example.com")
    kw.setdefault("phone", "0170 1")
    return Customer.objects.create(**kw)


def _closed_order(customer):
    from apps.orders.models import Order

    return Order.objects.create(
        customer=customer,
        reference_code=f"O-{uuid.uuid4().hex[:6]}",
        status="picked_up",
        payment_state="paid",
        total=Decimal("12.00"),
        shipping_address="Musterweg 1",
        note="ohne Zwiebeln",
    )


def test_every_customer_relation_has_an_erasure_rule():
    """Замок покрытия: новая модель с FK на клиента обязана попасть в политику."""
    labels = {rel.related_model._meta.label for rel in Customer._meta.related_objects}
    assert labels - set(dsgvo.ERASURE_POLICY) == set()
    for label, (action, arg) in dsgvo.ERASURE_POLICY.items():
        if action == "clear":
            from django.apps import apps as django_apps

            model = django_apps.get_model(label)
            for name in arg:
                model._meta.get_field(name)  # опечатка в поле → FieldDoesNotExist


def test_staff_gets_403_on_all_three_screens():
    c = _customer()
    for view in (views.customer_dsgvo, views.customer_dsgvo_export):
        assert view(_req(owner=False), pk=c.pk).status_code == 403
    resp = views.customer_dsgvo_erase(_req("post", {"confirm": "LÖSCHEN"}, owner=False), pk=c.pk)
    assert resp.status_code == 403
    c.refresh_from_db()
    assert c.email == "erika@example.com"


def test_erase_requires_post_and_confirmation():
    c = _customer()
    assert views.customer_dsgvo_erase(_req("get"), pk=c.pk).status_code == 405
    views.customer_dsgvo_erase(_req("post", {"confirm": "ja"}), pk=c.pk)
    c.refresh_from_db()
    assert c.email == "erika@example.com"


def test_export_zip_contains_deals_and_masks_secrets():
    c = _customer()
    _closed_order(c)
    other = _customer(name="Fremd", email="fremd@example.com")
    _closed_order(other)
    CustomerNote.objects.create(customer=c, text="Stammkundin")
    resp = views.customer_dsgvo_export(_req(), pk=c.pk)
    assert resp.status_code == 200 and resp["Cache-Control"] == "no-store"
    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    data = json.loads(archive.read("daten.json"))
    assert data["customer"]["email"] == "erika@example.com"
    orders = data["data"]["orders.Order"]
    assert len(orders) == 1 and orders[0]["note"] == "ohne Zwiebeln"
    assert data["data"]["crm.CustomerNote"][0]["text"] == "Stammkundin"
    assert "fremd@example.com" not in archive.read("daten.json").decode()
    assert "README.txt" in archive.namelist()


def test_open_deal_blocks_erasure_and_changes_nothing():
    from apps.orders.models import Order

    c = _customer()
    Order.objects.create(customer=c, reference_code="O-OPEN01", status="confirmed")
    with pytest.raises(dsgvo.ErasureBlocked):
        dsgvo.erase_customer(c)
    c.refresh_from_db()
    assert c.email == "erika@example.com"
    body = views.customer_dsgvo(_req(), pk=c.pk).content.decode()
    assert "data-dsgvo-blocked" in body


def test_erase_anonymizes_and_keeps_money():
    from apps.finance.models import Invoice, RevenueEntry
    from apps.reviews.models import Review

    c = _customer(birthday="1980-05-01")
    order = _closed_order(c)
    CustomerNote.objects.create(customer=c, text="Stammkundin")
    invoice = Invoice.objects.create(
        customer=c,
        recipient="Erika Muster\nMusterweg 1",
        status="paid",
        net=Decimal("10.08"),
        vat_amount=Decimal("1.92"),
        gross=Decimal("12.00"),
    )
    RevenueEntry.objects.create(
        source="order", source_ref=str(order.pk), amount=Decimal("12"), customer=c
    )
    Review.objects.create(
        entity_kind="product",
        entity_id=str(uuid.uuid4()),
        rating=5,
        author_name="Erika",
        email="erika@example.com",
        comment="Super",
    )
    resp = views.customer_dsgvo_erase(_req("post", {"confirm": "löschen"}), pk=c.pk)
    assert resp.status_code == 302
    c.refresh_from_db()
    assert (c.name, c.email, c.phone, c.birthday) == ("—", "", "", None)
    order.refresh_from_db()
    assert order.note == "" and order.shipping_address == "" and order.total == Decimal("12.00")
    invoice.refresh_from_db()
    assert invoice.recipient == "Erika Muster\nMusterweg 1"  # GoBD: без изменений
    assert RevenueEntry.objects.filter(customer=c).count() == 1
    assert not CustomerNote.objects.filter(customer=c).exists()
    review = Review.objects.get()
    assert review.email == "" and review.author_name == "—" and review.rating == 5


def test_erase_is_idempotent_and_audited_without_pii():
    from apps.audit.models import AuditEvent

    c = _customer()
    dsgvo.erase_customer(c)
    dsgvo.erase_customer(c)  # повтор не падает
    views.customer_dsgvo_erase(_req("post", {"confirm": "LÖSCHEN"}), pk=c.pk)
    event = AuditEvent.objects.filter(action="dsgvo.erase").last()
    assert event is not None
    assert "erika" not in json.dumps(event.changes, default=str).lower()


def test_failure_rolls_back_everything(monkeypatch):
    c = _customer()
    CustomerNote.objects.create(customer=c, text="bleibt")

    def boom(*a, **k):
        raise RuntimeError("step failed")

    monkeypatch.setattr(dsgvo, "_anonymize_customer", boom)
    with pytest.raises(RuntimeError):
        dsgvo.erase_customer(c)
    assert CustomerNote.objects.filter(customer=c).exists()


def test_erase_clears_notification_content_and_billing_copies():
    """Ревью E6.1: лог писем и копии адресов на сделке тоже чистятся."""
    from apps.notifications.models import Notification

    c = _customer()
    order = _closed_order(c)
    order.billing_name = "Erika Muster"
    order.billing_address = "Musterweg 1"
    order.save(update_fields=["billing_name", "billing_address"])
    Notification.objects.create(
        type="order_ready",
        channel="email",
        recipient="erika@example.com",
        subject="Hallo Erika",
        payload={"name": "Erika"},
        dedupe_key="dsgvo-n1",
    )
    dsgvo.erase_customer(c)
    order.refresh_from_db()
    assert order.billing_name == "" and order.billing_address == ""
    note = Notification.objects.get(dedupe_key="dsgvo-n1")
    assert (note.recipient, note.subject, note.payload) == ("", "", {})
