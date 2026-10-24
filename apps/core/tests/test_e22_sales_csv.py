"""KA-12 E2.2: CSV продаж — только владелец, те же фильтры, защита от формул,
запись в журнал выгрузок без персональных данных."""

import csv
import io
from decimal import Decimal

import pytest
from django.test import RequestFactory

from apps.core import views
from apps.core.tests.test_kanban import _make_order

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(params, role="owner"):
    import uuid

    from django.contrib.auth import get_user_model

    from apps.core.models import Membership
    from apps.tenants.tests.factories import TenantFactory

    user = get_user_model().objects.create_user(username=f"u-{uuid.uuid4().hex[:8]}")
    if role:
        Membership.objects.create(user=user, role=role)
    req = RequestFactory().get("/dashboard/verkaeufe/export.csv", params)
    req.user = user
    req.tenant = TenantFactory.build(schema_name="public")
    return req


def _rows(resp):
    text = resp.content.decode("utf-8").lstrip("﻿")
    return list(csv.reader(io.StringIO(text)))


def test_owner_gets_csv_with_header_and_rows():
    order = _make_order(name="Erika", email="erika@test.de")
    resp = views.sales_export_csv(_req({"tab": "order"}))
    assert resp.status_code == 200 and resp["Content-Type"].startswith("text/csv")
    rows = _rows(resp)
    assert rows[0][0] == "Code"
    assert any(r[0] == order.reference_code and r[5] == "erika@test.de" for r in rows[1:])


def test_staff_is_forbidden():
    _make_order()
    resp = views.sales_export_csv(_req({"tab": "order"}, role="staff"))
    assert resp.status_code == 403


def test_owner_only_prefix_registered():
    from apps.core import roles

    assert roles.required_role_for_path("/dashboard/verkaeufe/export.csv") == roles.ROLE_OWNER_ONLY


def test_filters_apply_like_the_list():
    keep = _make_order(name="Anna")
    other = _make_order(name="Berta")
    from apps.orders.state_machine import OrderSM

    OrderSM().apply(other, "confirmed")
    rows = _rows(views.sales_export_csv(_req({"tab": "order", "status": "new"})))
    codes = {r[0] for r in rows[1:]}
    assert keep.reference_code in codes and other.reference_code not in codes


def test_formula_injection_is_neutralised_but_numbers_are_not():
    _make_order(name='=HYPERLINK("http://x")')
    rows = _rows(views.sales_export_csv(_req({"tab": "order"})))
    row = rows[1]
    assert row[4].startswith("'=")
    assert Decimal(row[9]) > 0  # сумма — число, без апострофа


def test_export_is_audited_without_personal_data():
    from apps.audit.models import AuditEvent

    _make_order(email="geheim@test.de")
    views.sales_export_csv(_req({"tab": "order", "q": "geheim@test.de"}))
    ev = AuditEvent.objects.filter(action="export.sales_order").latest("created_at")
    assert ev.context["rows"] == 1
    assert "geheim" not in str(ev.context)


@pytest.mark.parametrize("tab", ["", "kunden", "reservation", "<x>"])
def test_unknown_tab_is_404(tab):
    from django.http import Http404

    with pytest.raises(Http404):
        views.sales_export_csv(_req({"tab": tab}))


def test_every_export_kind_builds(monkeypatch):
    """Каждый вид выгружается без ошибки (пустой файл = только заголовок)."""
    from apps.core import sales_export

    monkeypatch.setattr(
        "apps.tenants.models.Tenant.is_module_active", lambda self, key: True, raising=False
    )
    for kind in sales_export.EXPORT_KINDS:
        rows = _rows(views.sales_export_csv(_req({"tab": kind})))
        assert rows[0][0] == "Code"
