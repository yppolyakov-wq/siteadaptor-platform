"""PH-12f: события демо из краткого кортежа начинаются в круглый час, а не во время засева
(на проде «Bastelnachmittag» стоял на 08:52 — минуты запуска сидера)."""

import pytest
from django.utils import timezone

from apps.tenants import demo_kits
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_tuple_events_start_on_the_hour(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(schema_name="public", slug="spielkiste")
    assert demo_kits.apply_kit(tenant, "spielkiste")
    from apps.events.models import Event

    event = Event.objects.get(title="Bastelnachmittag für Kinder")
    local = timezone.localtime(event.starts_at)
    assert (local.hour, local.minute, local.second) == (10, 0, 0)
    assert event.price_cents == 800  # «8» в кортеже — цена, не час
