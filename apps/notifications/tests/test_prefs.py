"""UD4-2: резолвер каналов уведомлений — дефолты, per-событие, owner, матрица."""

import pytest

from apps.notifications import prefs
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(cfg=None, disabled=None):
    t = TenantFactory.build(business_type="restaurant", disabled_modules=disabled or [])
    if cfg is not None:
        t.site_config = {"notify": cfg}
    return t


def test_unconfigured_defaults_to_all_channels_on():
    t = _tenant()
    assert prefs.channel_enabled(t, "customer", "order", "ready", "email") is True
    assert prefs.channel_enabled(t, "customer", "order", "ready", "telegram") is True
    assert prefs.channel_enabled(t, "owner", "", "", "email") is True
    assert prefs.channel_enabled(t, "owner", "", "", "telegram") is True


def test_per_event_channel_toggle_respected():
    t = _tenant({"customer": {"order:ready": {"email": True, "telegram": False}}})
    assert prefs.channel_enabled(t, "customer", "order", "ready", "email") is True
    assert prefs.channel_enabled(t, "customer", "order", "ready", "telegram") is False
    # неуказанное событие — дефолт on
    assert prefs.channel_enabled(t, "customer", "order", "confirmed", "telegram") is True


def test_owner_channel_toggle_respected():
    t = _tenant({"owner": {"email": True, "telegram": False}})
    assert prefs.channel_enabled(t, "owner", "", "", "email") is True
    assert prefs.channel_enabled(t, "owner", "", "", "telegram") is False


def test_customer_matrix_lists_only_active_modules():
    t = _tenant(disabled=["events", "jobs"])
    domains = [g["domain"] for g in prefs.customer_matrix(t)]
    assert "order" in domains
    assert "ticket" not in domains  # events отключён
    assert "job" not in domains


def test_customer_matrix_reflects_saved_state():
    t = _tenant({"customer": {"order:ready": {"email": False, "telegram": True}}})
    order_group = next(g for g in prefs.customer_matrix(t) if g["domain"] == "order")
    ready = next(r for r in order_group["rows"] if r["event"] == "ready")
    assert ready["email"] is False and ready["telegram"] is True
