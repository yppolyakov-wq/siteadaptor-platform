import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import views
from apps.booking.models import AvailabilityRule, ClosedDate, Resource
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_repro_hf4():
    day = timezone.localdate() + timedelta(days=7)
    anna = Resource.objects.create(name="Anna", type="staff")
    AvailabilityRule.objects.create(
        resource=anna, weekday=day.weekday(), start_time="09:00", end_time="12:00", slot_minutes=30
    )
    ClosedDate.objects.create(date=day, reason="")
    url = "/dashboard/booking/verfuegbarkeit/"
    qs = f"year={day.year}&month={day.month}&resource={anna.pk}"
    request = RequestFactory().post(f"{url}?{qs}", {"date": day.isoformat()})
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build()
    tag = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{tag}", email=f"o-{tag}@t.de", password="pw12345678"
    )
    before = [(str(d), str(r)) for d, r in ClosedDate.objects.values_list("date", "resource_id")]
    resp = views.availability_calendar(request)
    after = [(str(d), str(r)) for d, r in ClosedDate.objects.values_list("date", "resource_id")]
    print("RESOURCE_PK", anna.pk)
    print("BEFORE", before)
    print("AFTER", after)
    print("MSGS", [str(m) for m in get_messages(request)])
    print("STATUS", resp.status_code, resp.get("Location", ""))
