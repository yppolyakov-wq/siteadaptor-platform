"""CO-2b: блок «Rechnungsempfänger» на карточке сделки — видно и правится, кому
выставляется счёт (Privat/Firma, фирма, USt-IdNr, связь со справочником).
План — docs/co2-v2-company-billing-plan-2026-10-21.md.
"""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.core import views as core_views
from apps.core.tests.test_deal_card_shell import _cards, _stay, _tenant, _User
from apps.crm.models import Company
from apps.stays.models import StayBooking

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _post(kind, pk, data, method="post"):
    rf = RequestFactory()
    req = rf.post("/", data) if method == "post" else rf.get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = _tenant("hotel")
    return core_views.deal_billing_edit(req, kind, pk)


def test_billing_block_on_cards_with_buyer_type():
    for kind, html in _cards():
        if kind in ("order", "stay", "booking", "job"):
            assert 'data-deal-block="billing"' in html, kind


def test_without_presence_sentinel_nothing_changes():
    stay = _stay()
    _post("stay", stay.pk, {"customer_type": "company", "billing_company": "X"})
    stay.refresh_from_db()
    assert stay.customer_type != "company" and stay.billing_company == ""


def test_edit_saves_company_and_garbage_type_is_private():
    stay = _stay()
    _post(
        "stay",
        stay.pk,
        {
            "billing_present": "1",
            "customer_type": "company",
            "billing_company": "Muster GmbH",
            "billing_vat_id": "DE123456789",
        },
    )
    stay.refresh_from_db()
    assert (stay.customer_type, stay.billing_company, stay.billing_vat_id) == (
        "company",
        "Muster GmbH",
        "DE123456789",
    )
    _post("stay", stay.pk, {"billing_present": "1", "customer_type": "evil"})
    stay.refresh_from_db()
    assert stay.customer_type == "private"


def test_pick_from_directory_copies_and_links():
    company = Company.objects.create(name="Müller GmbH", vat_id="DE111")
    stay = _stay()
    _post("stay", stay.pk, {"billing_present": "1", "company": str(company.pk)})
    stay.refresh_from_db()
    stay.customer.refresh_from_db()
    assert stay.customer_type == "company" and stay.billing_company == "Müller GmbH"
    assert stay.billing_vat_id == "DE111" and stay.customer.company_id == company.pk


def test_take_into_directory_creates_one_company():
    stay = _stay()
    StayBooking.objects.filter(pk=stay.pk).update(
        customer_type="company", billing_company="Neu GmbH", billing_vat_id="DE777"
    )
    for _ in range(2):
        _post("stay", stay.pk, {"action": "to_directory"})
    assert Company.objects.filter(name="Neu GmbH").count() == 1
    stay.customer.refresh_from_db()
    assert stay.customer.company.name == "Neu GmbH"


def test_unknown_kind_and_missing_deal_404():
    stay = _stay()
    with pytest.raises(Http404):
        _post("promotion", stay.pk, {"billing_present": "1"})
    import uuid

    with pytest.raises(Http404):
        _post("stay", uuid.uuid4(), {"billing_present": "1"})


def test_next_rejects_foreign_host():
    stay = _stay()
    resp = _post("stay", stay.pk, {"billing_present": "1", "next": "//evil.example/"})
    assert not resp["Location"].startswith("//")


def test_get_not_allowed():
    stay = _stay()
    assert _post("stay", stay.pk, {}, method="get").status_code == 405
