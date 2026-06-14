"""TG3+: события брони и Übernachtung дублируются в Telegram при привязке."""

from datetime import date, datetime, time, timedelta

import pytest
from django.utils import timezone

from apps.booking.models import Booking, Resource
from apps.notifications.models import Notification
from apps.promotions.models import Customer
from apps.stays.models import StayBooking, StayUnit
from apps.telegram.models import TelegramBot, TelegramLink

pytestmark = pytest.mark.django_db


def _linked_customer(email="k@test.de", chat="555"):
    TelegramBot.objects.create(token="t", bot_username="Bot", is_active=True)
    customer = Customer.objects.create(name="K", email=email)
    TelegramLink.objects.create(customer=customer, link_token="tok", chat_id=chat)
    return customer


def test_booking_event_pings_telegram():
    from apps.booking.notifications import enqueue_booking_email

    customer = _linked_customer()
    resource = Resource.objects.create(name="Tisch", capacity=1)
    start = timezone.make_aware(datetime.combine(date.today() + timedelta(days=1), time(10, 0)))
    booking = Booking.objects.create(
        customer=customer,
        resource=resource,
        start=start,
        end=start + timedelta(hours=1),
        reference_code="T-AAAAAA",
    )
    enqueue_booking_email(booking, "confirmed")
    n = Notification.objects.get(dedupe_key=f"booking:{booking.id}:confirmed:tg")
    assert n.channel == Notification.TELEGRAM and n.recipient == "555"


def test_stay_event_pings_telegram():
    from apps.stays.notifications import enqueue_stay_email

    customer = _linked_customer(email="s@test.de")
    unit = StayUnit.objects.create(name="Zimmer", quantity=1, price_cents=9000)
    arrival = date.today() + timedelta(days=3)
    booking = StayBooking.objects.create(
        customer=customer,
        unit=unit,
        arrival=arrival,
        departure=arrival + timedelta(days=2),
        reference_code="S-AAAAAA",
    )
    enqueue_stay_email(booking, "confirmed")
    n = Notification.objects.get(dedupe_key=f"stay:{booking.id}:confirmed:tg")
    assert n.channel == Notification.TELEGRAM and n.recipient == "555"
