"""Track D / D3c: кабинет-календарь, перенос, ручное добавление, письма по
статусам и beat-напоминание (ровно одно на запись)."""

import uuid
from datetime import datetime, time, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import services, tasks, views
from apps.booking.models import Booking, Resource
from apps.booking.state_machine import BookingSM
from apps.notifications.models import Notification
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/dashboard/booking/", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _cal(req):
    """W10-6: booking:calendar — 302; тело Tagesplan характеризуем через
    вкладку booking единой страницы (тот же calendar_context)."""
    from apps.core import views as core_views
    from apps.tenants.tests.factories import TenantFactory

    get = req.GET.copy()
    get["tab"], get["view"] = "booking", "kalender"
    req.GET = get
    if getattr(req, "tenant", None) is None:  # тест мог выставить своего
        req.tenant = TenantFactory.build(
            business_type="hairdresser", disabled_modules=["events", "stays"]
        )
    return core_views.verkaeufe(req)


def _resource(**kwargs):
    return Resource.objects.create(name=f"Tisch {uuid.uuid4().hex[:6]}", **kwargs)


def _slot(days_ahead=7, hour=12):
    tz = timezone.get_current_timezone()
    day = timezone.localdate() + timedelta(days=days_ahead)
    start = datetime.combine(day, time(hour, 0), tzinfo=tz)
    return start, start + timedelta(hours=1)


def _booking(email="gast@test.de", **kwargs):
    resource = kwargs.pop("resource", None) or _resource()
    start, end = kwargs.pop("slot", None) or _slot()
    return services.book(resource, start=start, end=end, name="Gast", email=email, **kwargs)


# --- письма ----------------------------------------------------------------------


def test_book_and_transitions_enqueue_emails():
    booking = _booking()
    assert Notification.objects.filter(dedupe_key=f"booking:{booking.id}:created:customer").exists()
    booking = BookingSM().apply(booking, "confirmed")
    confirmed = Notification.objects.get(dedupe_key=f"booking:{booking.id}:confirmed:customer")
    assert "bestätigt" in confirmed.payload["body"].lower()


def test_reminder_sent_once_within_horizon():
    near_start = timezone.now() + timedelta(hours=2)  # в горизонте 24ч в любое время суток
    near = _booking(
        slot=(near_start, near_start + timedelta(hours=1)), email=f"a{uuid.uuid4().hex[:6]}@t.de"
    )
    far = _booking(slot=_slot(days_ahead=7), email=f"b{uuid.uuid4().hex[:6]}@t.de")
    # напоминание только подтверждённым
    BookingSM().apply(near, "confirmed")
    BookingSM().apply(far, "confirmed")

    now = timezone.now()
    assert tasks.send_due_reminders(now=now) == 1  # только near в горизонте 24ч
    near.refresh_from_db()
    assert near.reminder_sent_at is not None
    assert Notification.objects.filter(dedupe_key=f"booking:{near.id}:reminder:customer").exists()
    assert tasks.send_due_reminders(now=now) == 0  # второго напоминания нет


# --- кабинет ---------------------------------------------------------------------


def test_calendar_renders_day():
    booking = _booking()
    day = booking.start.date().isoformat()
    body = _cal(_req(data={"tag": day})).content.decode()
    assert booking.reference_code in body and booking.resource.name in body


def test_calendar_month_grid_counts_and_navigation():
    """Фидбэк 2026-08-04: месячная сетка над днём — счётчик броней на дате,
    листание месяцев (история доступна), клик по дню = ?tag= того же вида."""
    booking = _booking()
    local_day = timezone.localtime(booking.start).date()
    ctx = views.calendar_context(_req(data={"tag": local_day.isoformat()}))
    row = next(c for c in ctx["bcal_days"] if c["day"] == local_day)
    assert row["count"] == 1 and row["is_selected"]
    assert ctx["bcal_first"] == local_day.replace(day=1)
    # явный месяц из ?cal= — в том числе ПРОШЛЫЙ (кабинету нужна история)
    past = (local_day.replace(day=1) - timedelta(days=1)).replace(day=1)
    ctx2 = views.calendar_context(
        _req(data={"tag": local_day.isoformat(), "cal": past.strftime("%Y-%m")})
    )
    assert ctx2["bcal_first"] == past
    assert all(c["count"] == 0 for c in ctx2["bcal_days"])
    # рендер: ячейка дня — ссылка ?tag=<дата>
    body = _cal(_req(data={"tag": local_day.isoformat()})).content.decode()
    assert f'tag={local_day.isoformat()}"' in body


def test_booking_detail_card_and_manage_url():
    """Фидбэк 2026-08-05: клик по сделке услуги ведёт на КАРТОЧКУ брони
    (детали + действия), а не на общий календарь; действия возвращают на
    карточку (next=), доска/списки ссылаются туда же."""
    from apps.core.transactions import transaction_for

    booking = _booking()
    body = views.booking_detail(_req(), pk=booking.pk).content.decode()
    assert booking.reference_code in body
    assert booking.resource.name in body
    assert f"/dashboard/booking/termin/{booking.pk}/" in body  # next= формы действий
    assert transaction_for("booking", booking).manage_url == (
        f"/dashboard/booking/termin/{booking.pk}/"
    )
    # действие со страницы карточки возвращает на карточку (внутренний next)
    resp = views.booking_action(
        _req(
            "post",
            data={"action": "confirmed", "next": f"/dashboard/booking/termin/{booking.pk}/"},
        ),
        pk=booking.pk,
    )
    assert resp.status_code == 302 and resp.url.endswith(f"/termin/{booking.pk}/")
    booking.refresh_from_db()
    assert booking.status == "confirmed"
    # чужой/абсолютный next игнорируется (open-redirect guard)
    resp = views.booking_action(
        _req("post", data={"action": "cancelled", "next": "https://evil.example/x"}),
        pk=booking.pk,
    )
    assert resp.url.startswith("/dashboard/booking/")


def test_availability_range_block_and_reopen():
    """Фидбэк 2026-08-04: «зарезервировать даты решением владельца» — блок
    диапазона одной формой (идемпотентно), «wieder öffnen» снимает его."""
    from apps.booking.models import ClosedDate

    _resource()
    von = timezone.localdate() + timedelta(days=10)
    bis = von + timedelta(days=3)
    data = {"action": "range", "von": von.isoformat(), "bis": bis.isoformat(), "reason": "Urlaub"}
    resp = views.availability_calendar(_req("post", data=data))
    assert resp.status_code == 302
    assert ClosedDate.objects.filter(resource__isnull=True).count() == 4
    assert ClosedDate.objects.filter(date=von, reason="Urlaub").exists()
    # повторный блок того же диапазона дубликатов не плодит
    views.availability_calendar(_req("post", data=data))
    assert ClosedDate.objects.count() == 4
    # wieder öffnen — диапазон снят
    views.availability_calendar(_req("post", data={**data, "mode": "open"}))
    assert ClosedDate.objects.count() == 0


def test_action_confirm_and_move_conflict():
    resource = _resource()
    slot_a = _slot(days_ahead=7, hour=12)
    slot_b = _slot(days_ahead=7, hour=15)
    first = _booking(resource=resource, slot=slot_a, email="x1@t.de")
    second = _booking(resource=resource, slot=slot_b, email="x2@t.de")

    response = views.booking_action(_req("post", data={"action": "confirmed"}), pk=first.pk)
    assert response.status_code == 302
    first.refresh_from_db()
    assert first.status == "confirmed"

    # перенос second на время first — конфликт, время не меняется
    views.booking_action(
        _req("post", data={"action": "move", "start": slot_a[0].isoformat()}), pk=second.pk
    )
    second.refresh_from_db()
    assert second.start == slot_b[0]

    # перенос на свободное время — ок, длительность сохраняется
    free_start = slot_b[0] + timedelta(hours=3)
    views.booking_action(
        _req("post", data={"action": "move", "start": free_start.isoformat()}), pk=second.pk
    )
    second.refresh_from_db()
    assert second.start == free_start and second.end - second.start == timedelta(hours=1)


def test_manual_create_is_confirmed():
    resource = _resource()
    start, _end = _slot(days_ahead=3)
    response = views.booking_create(
        _req(
            "post",
            "/dashboard/booking/new/",
            {
                "resource": str(resource.pk),
                "start": start.isoformat(),
                "minutes": "90",
                "name": "Telefon-Gast",
            },
        )
    )
    assert response.status_code == 302
    booking = Booking.objects.get(resource=resource)
    assert booking.status == "confirmed"
    assert booking.end - booking.start == timedelta(minutes=90)
    assert booking.source_channel == "manual"


def test_resources_page_creates_resource_and_rule():
    response = views.resources(
        _req("post", "/dashboard/booking/ressourcen/", {"action": "resource", "name": "Saal"})
    )
    assert response.status_code == 302
    resource = Resource.objects.get(name="Saal")

    views.resources(
        _req(
            "post",
            "/dashboard/booking/ressourcen/",
            {
                "action": "rule",
                "resource": str(resource.pk),
                "weekday": "2",
                "start_time": "10:00",
                "end_time": "14:00",
                "slot_minutes": "60",
            },
        )
    )
    rule = resource.rules.get()
    assert rule.weekday == 2 and rule.slot_minutes == 60

    body = views.resources(_req(path="/dashboard/booking/ressourcen/")).content.decode()
    assert "Saal" in body and "10:00" in body


# --- P2.5b: депозит в кабинете ----------------------------------------------------


def test_cancel_paid_booking_refunds(monkeypatch):
    booking = _booking(email="paid@t.de")
    BookingSM().apply(booking, "confirmed")
    booking.payment_state = Booking.PAYMENT_PAID
    booking.stripe_payment_intent = "pi_x"
    booking.save(update_fields=["payment_state", "stripe_payment_intent"])
    captured = {}
    monkeypatch.setattr(views.connect, "refund", lambda **kw: captured.update(kw))
    request = _req("post", data={"action": "cancelled"})
    request.tenant = TenantFactory.build(stripe_connect_id="acct_1")
    views.booking_action(request, pk=booking.pk)
    booking.refresh_from_db()
    assert booking.status == "cancelled"
    assert booking.payment_state == Booking.PAYMENT_REFUNDED
    assert captured == {"connect_id": "acct_1", "payment_intent": "pi_x"}


def test_resource_settings_saves_deposit():
    resource = _resource()
    views.resources(
        _req(
            "post",
            "/dashboard/booking/ressourcen/",
            {
                "action": "resource_settings",
                "resource": str(resource.pk),
                "deposit_eur": "5,50",
                "require_manual_confirm": "on",
            },
        )
    )
    resource.refresh_from_db()
    assert resource.deposit_cents == 550
    assert resource.require_manual_confirm is True


def test_resource_profile_saves_title_bio_photo_and_removes():
    """A3: профиль мастера — должность, био, фото (загрузка + удаление)."""
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    def _png():
        buf = BytesIO()
        Image.new("RGB", (10, 10), "green").save(buf, "PNG")
        return SimpleUploadedFile("m.png", buf.getvalue(), content_type="image/png")

    resource = _resource(type=Resource.TYPE_STAFF)
    req = _req(
        "post",
        "/dashboard/booking/ressourcen/",
        {
            "action": "resource_profile",
            "resource": str(resource.pk),
            "title": "Stylistin",
            "bio": "10 Jahre Erfahrung.",
        },
    )
    req.FILES["photo"] = _png()
    views.resources(req)
    resource.refresh_from_db()
    assert resource.title == "Stylistin" and resource.bio == "10 Jahre Erfahrung."
    assert resource.photo_url  # фото сохранено
    # удаление фото
    views.resources(
        _req(
            "post",
            "/dashboard/booking/ressourcen/",
            {
                "action": "resource_profile",
                "resource": str(resource.pk),
                "title": "Stylistin",
                "bio": "10 Jahre Erfahrung.",
                "remove_photo": "1",
            },
        )
    )
    resource.refresh_from_db()
    assert not resource.photo_url
