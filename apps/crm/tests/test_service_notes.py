"""KA-12 E6.4b: заметки мастера о процедуре («карточка окрашивания»).

Пишутся с карточки записи, видны на следующем визите клиента (сначала по той же
услуге), удаляет автор или owner/admin, не смешиваются с заметкой клиента
`Booking.note`, попадают в выгрузку DSGVO без сотрудника и удаляются с клиентом."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import services, views
from apps.booking.tests.test_services import _resource, _service
from apps.crm.models import CustomerNote
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urls(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _user(email):
    return get_user_model().objects.create_user(email, email, "pw")


def _req(user, data=None, method="post"):
    r = getattr(RequestFactory(), method)("/", data or {})
    r.user = user
    SessionMiddleware(lambda x: None).process_request(r)
    r._messages = FallbackStorage(r)
    r.tenant = TenantFactory.build(business_type="friseur")
    return r


def _booking(svc=None, days=2, email="k@t.de"):
    start = timezone.now() + timedelta(days=days)
    return services.book(
        _resource(),
        start=start,
        end=start + timedelta(hours=1),
        name="K",
        email=email,
        service=svc or _service(),
        note="Bitte Parkplatz",
    )


def _post(user, booking, **data):
    return views.booking_action.__wrapped__.__wrapped__(_req(user, data), booking.pk)


def test_note_created_with_context_and_shown_next_visit(monkeypatch):
    svc = _service()
    first = _booking(svc)
    staff = _user("lea@t.de")
    _post(staff, first, action="service_note", text="Farbe 7.1 + 6 % Oxid, 30 Min")
    note = CustomerNote.objects.get()
    assert (note.kind, note.booking_id, note.service_id, note.author_id) == (
        "service",
        first.pk,
        svc.pk,
        staff.pk,
    )
    nxt = _booking(svc, days=40)
    assert [n.pk for n in views._service_notes_for(nxt)] == [note.pk]
    body = views.booking_detail.__wrapped__(_req(staff, method="get"), nxt.pk).content.decode()
    assert "Farbe 7.1" in body and "Beim letzten Besuch" in body


def test_other_service_note_is_fallback():
    a, b = _service(), _service()
    first = _booking(a)
    _post(_user("x@t.de"), first, action="service_note", text="Balayage")
    assert len(views._service_notes_for(_booking(b, days=30))) == 1


def test_empty_and_too_long_rejected():
    b = _booking()
    u = _user("y@t.de")
    _post(u, b, action="service_note", text="   ")
    _post(u, b, action="service_note", text="x" * (CustomerNote.MAX_TEXT + 1))
    assert not CustomerNote.objects.exists()


def test_delete_by_author_or_owner_only(monkeypatch):
    b = _booking()
    author, other = _user("a@t.de"), _user("o@t.de")
    _post(author, b, action="service_note", text="Notiz")
    note = CustomerNote.objects.get()
    monkeypatch.setattr(views, "_can_edit_policy", lambda user: False)
    with pytest.raises(PermissionDenied):
        _post(other, b, action="service_note_delete", note=str(note.pk))
    monkeypatch.setattr(views, "_can_edit_policy", lambda user: True)
    _post(other, b, action="service_note_delete", note=str(note.pk))
    assert not CustomerNote.objects.exists()


def test_cannot_delete_note_of_other_customer():
    mine = _booking(email="m@t.de")
    theirs = _booking(email="t@t.de")
    u = _user("z@t.de")
    _post(u, theirs, action="service_note", text="fremd")
    note = CustomerNote.objects.get()
    with pytest.raises(Http404):
        _post(u, mine, action="service_note_delete", note=str(note.pk))


def test_xss_escaped_and_not_in_customer_note():
    b = _booking()
    u = _user("q@t.de")
    _post(u, b, action="service_note", text="<script>alert(1)</script>")
    body = views.booking_detail.__wrapped__(_req(u, method="get"), b.pk).content.decode()
    assert "<script>alert(1)</script>" not in body and "&lt;script&gt;" in body
    b.refresh_from_db()
    assert b.note == "Bitte Parkplatz"


def test_dsgvo_export_skips_author_and_erasure_deletes():
    from apps.crm import dsgvo

    b = _booking()
    _post(_user("w@t.de"), b, action="service_note", text="Rezeptur")
    row = dsgvo._row(CustomerNote.objects.get())
    assert "author" not in row and row["kind"] == "service"
    assert dsgvo.ERASURE_POLICY["crm.CustomerNote"][0] == "delete"


def test_customer360_service_history(monkeypatch):
    from apps.crm import customer360

    b = _booking()
    _post(_user("v@t.de"), b, action="service_note", text="Strähnen")
    monkeypatch.setattr(customer360, "_active", lambda t, key: True)
    keys = {s["key"] for s in customer360.sections(None, b.customer)}
    assert "service_history" in keys
