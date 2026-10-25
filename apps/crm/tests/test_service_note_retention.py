"""KA-12 E6.4d: заметки мастера к процедурам удаляются через 3 года после последней
записи клиента (решение владельца 2026-10-25). Заметка моложе срока не удаляется
никогда; обычные заметки (`kind=note`) не трогаем; будущая запись продлевает."""

from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from apps.booking.models import Booking
from apps.crm import tasks
from apps.crm.models import CustomerNote
from apps.crm.tests.test_service_notes import _booking

pytestmark = pytest.mark.django_db

DAYS = settings.SERVICE_NOTE_RETENTION_DAYS


def _note(booking, *, age_days, kind=CustomerNote.KIND_SERVICE):
    note = CustomerNote.objects.create(
        customer=booking.customer, booking=booking, text="Farbe 7.1", kind=kind
    )
    CustomerNote.objects.filter(pk=note.pk).update(
        created_at=timezone.now() - timedelta(days=age_days)
    )
    return note


def _visit_ago(booking, days):
    start = timezone.now() - timedelta(days=days)
    Booking.objects.filter(pk=booking.pk).update(start=start, end=start + timedelta(hours=1))


def test_retention_is_three_years():
    assert DAYS == 3 * 365


def test_deletes_after_last_visit_plus_three_years():
    b = _booking()
    _visit_ago(b, DAYS + 1)
    note = _note(b, age_days=DAYS + 1)
    assert tasks.purge_due_service_notes() == 1
    assert not CustomerNote.objects.filter(pk=note.pk).exists()


def test_recent_visit_keeps_old_note():
    b = _booking()
    _visit_ago(b, DAYS + 30)
    note = _note(b, age_days=DAYS + 30)
    later = _booking(email="k@t.de")  # тот же клиент, визит 2 года назад
    _visit_ago(later, 2 * 365)
    assert later.customer_id == b.customer_id
    assert tasks.purge_due_service_notes() == 0
    assert CustomerNote.objects.filter(pk=note.pk).exists()


def test_future_booking_keeps_note():
    b = _booking()
    _visit_ago(b, DAYS + 30)
    note = _note(b, age_days=DAYS + 30)
    _booking(days=10, email="k@t.de")
    assert tasks.purge_due_service_notes() == 0
    assert CustomerNote.objects.filter(pk=note.pk).exists()


def test_young_note_is_never_deleted_even_after_old_visit():
    b = _booking()
    _visit_ago(b, DAYS + 100)
    note = _note(b, age_days=30)
    assert tasks.purge_due_service_notes() == 0
    assert CustomerNote.objects.filter(pk=note.pk).exists()


def test_cancelled_and_no_show_visits_count_as_contact():
    b = _booking()
    _visit_ago(b, DAYS + 30)
    note = _note(b, age_days=DAYS + 30)
    other = _booking(email="k@t.de")
    _visit_ago(other, 100)
    Booking.objects.filter(pk=other.pk).update(status="no_show")
    assert tasks.purge_due_service_notes() == 0
    assert CustomerNote.objects.filter(pk=note.pk).exists()


def test_plain_notes_are_untouched():
    b = _booking()
    _visit_ago(b, DAYS + 100)
    note = _note(b, age_days=DAYS + 100, kind=CustomerNote.KIND_NOTE)
    assert tasks.purge_due_service_notes() == 0
    assert CustomerNote.objects.filter(pk=note.pk).exists()


def test_idempotent():
    b = _booking()
    _visit_ago(b, DAYS + 1)
    _note(b, age_days=DAYS + 1)
    assert tasks.purge_due_service_notes() == 1
    assert tasks.purge_due_service_notes() == 0


def test_several_batches(monkeypatch):
    monkeypatch.setattr(tasks, "BATCH", 2)
    for i in range(5):
        b = _booking(email=f"m{i}@t.de")
        _visit_ago(b, DAYS + 1)
        _note(b, age_days=DAYS + 1)
    assert tasks.purge_due_service_notes() == 5
    assert not CustomerNote.objects.filter(kind=CustomerNote.KIND_SERVICE).exists()


def test_customer_without_bookings():
    from apps.promotions.models import Customer

    c = Customer.objects.create(name="Ohne Termin", email="o@t.de")
    note = CustomerNote.objects.create(customer=c, text="alt", kind=CustomerNote.KIND_SERVICE)
    CustomerNote.objects.filter(pk=note.pk).update(
        created_at=timezone.now() - timedelta(days=DAYS + 1)
    )
    fresh = CustomerNote.objects.create(customer=c, text="neu", kind=CustomerNote.KIND_SERVICE)
    assert tasks.purge_due_service_notes() == 1
    assert list(CustomerNote.objects.values_list("pk", flat=True)) == [fresh.pk]


def test_no_n_plus_one(django_assert_max_num_queries):
    for i in range(20):
        b = _booking(email=f"k{i}@t.de")
        _visit_ago(b, DAYS + 1)
        _note(b, age_days=DAYS + 1)
    with django_assert_max_num_queries(6):
        assert tasks.purge_due_service_notes() == 20


def test_task_continues_after_broken_tenant(monkeypatch, caplog):
    from types import SimpleNamespace

    calls = []

    def fake(now=None):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return 2

    class _Mgr:
        def exclude(self, **kw):
            return [SimpleNamespace(schema_name="a"), SimpleNamespace(schema_name="b")]

    class _Ctx:
        def __init__(self, t):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(tasks, "get_tenant_model", lambda: SimpleNamespace(objects=_Mgr()))
    monkeypatch.setattr(tasks, "tenant_context", _Ctx)
    monkeypatch.setattr(tasks, "purge_due_service_notes", fake)
    result = tasks.purge_old_service_notes.run()
    assert result == {"deleted": 2}
    assert "purge_old_service_notes" in caplog.text


def test_beat_schedule_has_task():
    entry = settings.CELERY_BEAT_SCHEDULE["purge-old-service-notes"]
    assert entry["task"] == "apps.crm.tasks.purge_old_service_notes"


def test_privacy_paragraph_names_retention():
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build()
    assert tenant._privacy_treatment_paragraph() == ""
    b = _booking()
    _note(b, age_days=1)
    text = tenant._privacy_treatment_paragraph()
    assert "3 Jahre" in text and "letzten Termin" in text
