"""Track D / D4c: экспорт журнала — обычный CSV и DATEV-Buchungsstapel."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.finance import views
from apps.finance.exports import datev_csv, plain_csv
from apps.finance.services import record_revenue

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _entries():
    record_revenue(
        source="manual", amount=Decimal("11.90"), date=date(2026, 6, 3), note="Theke Brötchen"
    )
    record_revenue(
        source="order",
        source_ref="o1",
        amount=Decimal("21.40"),
        vat_rate=Decimal("7.00"),
        date=date(2026, 6, 5),
        note="O-ABC123",
    )
    record_revenue(
        source="manual", amount=Decimal("5.00"), vat_rate=Decimal("0.00"), date=date(2026, 6, 7)
    )
    record_revenue(source="manual", amount=Decimal("99.00"), date=date(2026, 5, 1))  # вне периода


def _req(path):
    request = RequestFactory().get(path, {"von": "2026-06-01", "bis": "2026-06-30"})
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(username=f"o-{owner}", password="pw")
    return request


def test_plain_csv_respects_period():
    _entries()
    response = views.journal_export_csv(_req("/dashboard/finance/export.csv"))
    body = response.content.decode("utf-8-sig")
    assert body.splitlines()[0].startswith("date,source,note")
    assert "Theke Brötchen" in body and "O-ABC123" in body
    assert "99.00" not in body  # вне периода
    assert 'filename="umsatz_2026-06-01_2026-06-30.csv"' in response["Content-Disposition"]


def test_datev_csv_format_and_accounts():
    _entries()
    response = views.journal_export_datev(_req("/dashboard/finance/datev.csv"))
    assert "windows-1252" in response["Content-Type"]
    body = response.content.decode("cp1252")
    lines = body.splitlines()
    assert lines[0].startswith("Umsatz;Soll/Haben-Kennzeichen;WKZ Umsatz;Konto;Gegenkonto")
    # десятичная запятая, Kasse 1000, счёт по ставке, Belegdatum TTMM
    assert "11,90;S;EUR;1000;8400;0306" in lines[1]
    assert "21,40;S;EUR;1000;8300;0505" in lines[2]
    assert "5,00;S;EUR;1000;8195;0706" in lines[3]
    assert len(lines) == 4  # запись вне периода не попала


def test_export_helpers_handle_empty():
    assert plain_csv([]).splitlines()[0].startswith("date,")
    assert datev_csv([]).splitlines()[0].startswith("Umsatz;")
