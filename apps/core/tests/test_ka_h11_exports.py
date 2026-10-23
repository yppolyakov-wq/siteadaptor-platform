"""KA-H11 (аудит KA-9 №1, №3): выгрузки с персональными данными — только владельцу,
и каждая выгрузка пишет запись в журнал (кто, что, сколько строк).

До фикса любой сотрудник выгружал CSV клиентов, участников события, гостей
отеля и журнал выручки с именами клиентов; журнал выгрузок не вёлся вовсе."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.core.models import Membership
from apps.crm import views as crm_views
from apps.events import views as event_views
from apps.events.models import Event
from apps.finance import views as finance_views
from apps.inventory import views as inventory_views
from apps.promotions.models import Customer
from apps.stays import views as stay_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(role, path="/dashboard/x.csv", data=None):
    request = RequestFactory().get(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(f"x-{o}", f"x-{o}@t.de", "pw12345678")
    Membership.objects.create(user=user, role=role)
    request.user = user
    request.tenant = TenantFactory.build(disabled_modules=[])
    return request


def _event():
    return Event.objects.create(
        title="WS", starts_at=timezone.now() + timedelta(days=5), status=Event.STATUS_PUBLISHED
    )


def _crm(request):
    return crm_views.customer_export_csv(request)


def _roster(request):
    return event_views.roster_csv(request, pk=_event().pk)


def _stays(request):
    return stay_views.reports_export_csv(request)


def _journal(request):
    return finance_views.journal_export_csv(request)


def _datev(request):
    return finance_views.journal_export_datev(request)


def _expenses(request):
    return finance_views.expenses_export_datev(request)


EXPORTS = {
    "crm": _crm,
    "roster": _roster,
    "stays": _stays,
    "finance_csv": _journal,
    "finance_datev": _datev,
    "expenses_datev": _expenses,
}


@pytest.mark.parametrize("name", list(EXPORTS))
@pytest.mark.parametrize("role", [Membership.ROLE_STAFF, Membership.ROLE_ADMIN])
def test_staff_cannot_export(name, role):
    response = EXPORTS[name](_req(role))
    assert response.status_code == 403
    assert not AuditEvent.objects.filter(action=f"export.{name}").exists()


@pytest.mark.parametrize("name", list(EXPORTS))
def test_owner_export_is_audited(name):
    response = EXPORTS[name](_req(Membership.ROLE_OWNER))
    assert response.status_code == 200
    assert "csv" in response["Content-Type"]
    events = AuditEvent.objects.filter(action=f"export.{name}")
    assert events.count() == 1
    assert "rows" in events.get().context


def test_crm_export_audit_counts_rows():
    Customer.objects.create(name="A", email="a@t.de")
    Customer.objects.create(name="B", email="b@t.de")
    crm_views.customer_export_csv(_req(Membership.ROLE_OWNER))
    event = AuditEvent.objects.get(action="export.crm")
    assert event.context["rows"] == Customer.objects.count()
    assert "a@t.de" not in str(event.context)  # в журнале — только счётчики


def test_inventory_csv_stays_open_for_staff():
    request = _req(Membership.ROLE_STAFF, "/dashboard/stock/", {"export": "csv"})
    assert inventory_views.stock(request).status_code == 200


def test_crm_list_hides_export_button_for_staff():
    body = crm_views.customer_list(_req(Membership.ROLE_STAFF, "/crm/")).content.decode()
    assert 'href="/crm/export.csv' not in body
    body = crm_views.customer_list(_req(Membership.ROLE_OWNER, "/crm/")).content.decode()
    assert 'href="/crm/export.csv' in body


def test_middleware_blocks_staff_on_export_prefixes():
    from apps.core.middleware import CabinetOwnerAccessMiddleware as mw

    for path in (
        "/crm/export.csv",
        "/dashboard/stays/berichte/export.csv",
        "/dashboard/finance/export.csv",
        "/dashboard/finance/datev.csv",
        "/dashboard/finance/ausgaben/datev.csv",
    ):
        assert path.startswith(mw._OWNER_ONLY), path
