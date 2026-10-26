"""KA-12 GA-1 (Gastro): правило онлайн-брони столов — сразу / Gruppenanfrage /
«bitte anrufen»; Gruppenanfrage не подтверждается оплатой; запись со стойки шлёт
гостю «bestätigt»."""

import uuid
from datetime import datetime, time, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import public_views, table_rules
from apps.booking.models import AvailabilityRule, Booking, Resource
from apps.notifications.models import Notification
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

DAY = timezone.localdate() + timedelta(days=7)
RULE = {"booking": {"tables": {"instant_max": 4, "online_max": 10}}}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _table(rtype=Resource.TYPE_TABLE):
    resource = Resource.objects.create(
        name=f"Tische {uuid.uuid4().hex[:6]}", capacity=40, counts_party_size=True, type=rtype
    )
    AvailabilityRule.objects.create(
        resource=resource,
        weekday=DAY.weekday(),
        start_time=time(17, 0),
        end_time=time(22, 0),
        slot_minutes=60,
    )
    return resource


def _tenant(cfg=None):
    return TenantFactory.build(
        business_type="restaurant", site_config=dict(RULE if cfg is None else cfg)
    )


def _post(resource, party, tenant=None, email=None):
    tz = timezone.get_current_timezone()
    start = datetime.combine(DAY, time(18, 0), tzinfo=tz)
    data = {
        "start": start.isoformat(),
        "end": (start + timedelta(hours=1)).isoformat(),
        "name": "Gast",
        "email": email or f"{uuid.uuid4().hex[:6]}@example.com",
        "party_size": str(party),
    }
    request = RequestFactory().post(f"/termin/{resource.pk}/buchen/", data)
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant or _tenant()
    return public_views.termin_book(request, pk=resource.pk), data["email"]


# --- конфиг -------------------------------------------------------------------


def test_normalize_keeps_both_rules_and_clamps():
    raw = {
        "no_show_deposit": {"after": 2, "days": 365},
        "tables": {"instant_max": "99", "online_max": "8"},
    }
    out = siteconfig.normalize_booking(raw)
    assert out["no_show_deposit"]["after"] == 2
    assert out["tables"] == {"instant_max": 8, "online_max": 8}  # instant ≤ online
    assert siteconfig.normalize_booking({"tables": {"online_max": "x"}})["tables"] == {
        "instant_max": 0,
        "online_max": 50,
    }
    assert siteconfig.normalize_booking({}) == {}


def test_decide_boundaries():
    table = Resource(type=Resource.TYPE_TABLE)
    tenant = _tenant()
    assert table_rules.decide(tenant, table, 4) == table_rules.INSTANT
    assert table_rules.decide(tenant, table, 5) == table_rules.REQUEST
    assert table_rules.decide(tenant, table, 10) == table_rules.REQUEST
    assert table_rules.decide(tenant, table, 11) == table_rules.CALL
    assert table_rules.decide(tenant, Resource(type=Resource.TYPE_STAFF), 11) is None
    assert table_rules.decide(_tenant({}), table, 30) is None


# --- витрина ------------------------------------------------------------------


def test_small_party_confirmed_instantly_with_confirmed_mail():
    resource = _table()
    response, email = _post(resource, 2)
    booking = Booking.objects.get(customer__email=email)
    assert response.status_code == 302 and booking.status == "confirmed"
    assert not booking.is_large_party
    assert Notification.objects.filter(recipient=email, type="booking_confirmed").exists()


def test_large_party_is_request():
    resource = _table()
    _response, email = _post(resource, 8)
    booking = Booking.objects.get(customer__email=email)
    assert booking.status == "pending" and booking.is_large_party
    assert Notification.objects.filter(recipient=email, type="booking_created").exists()


def test_too_large_party_gets_no_booking():
    resource = _table()
    response, email = _post(resource, 11)
    assert response.status_code == 302
    assert not Booking.objects.filter(customer__email=email).exists()


def test_without_rule_everything_stays_pending():
    resource = _table()
    _response, email = _post(resource, 2, tenant=_tenant({}))
    booking = Booking.objects.get(customer__email=email)
    assert booking.status == "pending" and not booking.is_large_party


def test_paid_deposit_does_not_confirm_group_request():
    from django.db import connection

    from apps.booking import payments

    resource = _table()
    _response, email = _post(resource, 8)
    booking = Booking.objects.get(customer__email=email)
    assert payments.mark_deposit_paid(
        tenant_schema=connection.schema_name, booking_id=str(booking.id), payment_intent="pi_x"
    )
    booking.refresh_from_db()
    assert booking.status == "pending"


def test_money_contract_respects_group_request():
    from apps.core import money_contract

    booking = Booking(is_large_party=True, resource=Resource(require_manual_confirm=False))
    assert money_contract._needs_manual_confirm("booking", booking)
    plain = Booking(is_large_party=False, resource=Resource(require_manual_confirm=False))
    assert not money_contract._needs_manual_confirm("booking", plain)


def test_slot_page_limits_party_field():
    resource = _table()
    request = RequestFactory().get(f"/termin/{resource.pk}/", {"tag": DAY.isoformat()})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = _tenant()
    tz = timezone.get_current_timezone()
    start = datetime.combine(DAY, time(18, 0), tzinfo=tz)
    request.GET = request.GET.copy()
    request.GET["slot"] = start.isoformat()
    body = public_views.termin_slots(request, pk=resource.pk).content.decode()
    assert 'max="10"' in body and "data-table-rule" in body


# --- кабинет ------------------------------------------------------------------


def _cab(data):
    request = RequestFactory().post("/dashboard/booking/tische/regeln/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"o-{uuid.uuid4().hex[:8]}", password="pw1234567"
    )
    return request


def test_rule_save_keeps_other_booking_rules(monkeypatch):
    from apps.booking import views

    monkeypatch.setattr(views, "_can_edit_policy", lambda user: True)

    tenant = TenantFactory(
        site_config={"booking": {"no_show_deposit": {"after": 2, "days": 365}}, "theme": "x"},
        auto_create_schema=False,
    )
    request = _cab({"enabled": "1", "instant_max": "4", "online_max": "12"})
    request.tenant = tenant
    views.table_rules_save(request)
    tenant.refresh_from_db()
    assert tenant.site_config["booking"]["tables"] == {"instant_max": 4, "online_max": 12}
    assert tenant.site_config["booking"]["no_show_deposit"]["after"] == 2
    assert tenant.site_config["theme"] == "x"
    request = _cab({"instant_max": "4", "online_max": "12"})  # выключено
    request.tenant = tenant
    views.table_rules_save(request)
    tenant.refresh_from_db()
    assert "tables" not in tenant.site_config["booking"]


def test_manual_confirm_flag_read_only_in_table_rules():
    """Замок: «подтверждает только владелец» у записи читается в одной точке."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    hits = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if "/tests/" in rel or "/migrations/" in rel or rel.startswith(("stays/", "events/")):
            continue
        text = path.read_text(encoding="utf-8")
        if "resource.require_manual_confirm" in text and not rel.startswith("booking/views"):
            hits.append(rel)
    assert hits == []


def test_staff_without_policy_right_cannot_change_rule(monkeypatch):
    from django.core.exceptions import PermissionDenied

    from apps.booking import views

    monkeypatch.setattr(views, "_can_edit_policy", lambda user: False)
    request = _cab({"enabled": "1", "instant_max": "50", "online_max": "50"})
    request.tenant = _tenant()
    with pytest.raises(PermissionDenied):
        views.table_rules_save(request)


def test_manual_confirm_table_is_never_instant():
    resource = _table()
    Resource.objects.filter(pk=resource.pk).update(require_manual_confirm=True)
    resource.refresh_from_db()
    _response, email = _post(resource, 2)
    assert Booking.objects.get(customer__email=email).status == "pending"


def test_owner_mail_for_confirmed_booking_does_not_ask_to_confirm(monkeypatch):
    owner_tenant = TenantFactory.build(owner_email="chef@example.com")
    monkeypatch.setattr("apps.booking.notifications._tenant", lambda schema: owner_tenant)
    resource = _table()
    _response, _email = _post(resource, 2)
    mail = Notification.objects.get(recipient="chef@example.com", type="booking_created_owner")
    assert "bereits bestätigt" in mail.subject + mail.payload.get("body", "")
