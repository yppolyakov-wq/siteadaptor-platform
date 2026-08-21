import pytest

from apps.tenants import demo_kits
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_stadtfuehrung_kit_seeds_end_to_end(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(schema_name="public", slug="stadtfuehrung")
    assert demo_kits.apply_kit(tenant, "stadtfuehrung")
    from apps.core.models import Extra
    from apps.events.models import Event, Tour

    assert Tour.objects.filter(is_published=True).count() == 3
    assert Event.objects.count() == 4
    # MX-2e: адресная опция с пулом на первом заезде
    opt = Extra.objects.get(label="Audio-Headset")
    assert opt.tracker == Extra.TRACKER_POOL and opt.pool_size == 15
    assert opt.entity_kind == "event" and opt.entity_id
    # заезды привязаны к турам (6c: свод в одну карточку сработает)
    assert Event.objects.filter(tour__isnull=False).count() == 4
    # anfrage-форма настроена (AF-1)
    cfg = (tenant.site_config or {}).get("anfrage") or {}
    assert "event_type" in (cfg.get("fields") or [])
