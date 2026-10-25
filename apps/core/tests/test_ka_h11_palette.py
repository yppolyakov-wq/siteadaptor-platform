"""KA-H11 (аудит KA-9 №2): палитра Ctrl+K не показывает e-mail и телефон клиента
сотрудникам — только владельцу. E6.7g: без права «Kontaktdaten sehen» клиента не
найти и ПО контакту (иначе e-mail/телефон угадываются подбором) — только по имени."""

from uuid import uuid4

import pytest

from apps.core import palette_search as ps
from apps.core.modules import default_disabled_for
from apps.crm.models import Customer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant():
    off = [m for m in default_disabled_for("friseur") if m != "crm"]
    return TenantFactory(
        slug=f"h11-{uuid4().hex[:6]}", business_type="friseur", disabled_modules=off
    )


def _customer_items(owner, q):
    sections = {s["key"]: s for s in ps.search(_tenant(), q, owner=owner)}
    return sections.get("customers", {}).get("items", [])


def test_staff_sees_masked_email():
    Customer.objects.create(name="Frau Kunz", email="kunz@beispiel.de")
    item = _customer_items(False, "kunz")[0]
    assert "kunz@beispiel.de" not in item["sub"]
    assert item["sub"].endswith("@beispiel.de")


def test_staff_does_not_find_by_email():
    """Переписано осознанно (E6.7g): раньше поиск по e-mail работал у всех."""
    Customer.objects.create(name="Herr Lenz", email="lenz@beispiel.de")
    assert _customer_items(False, "lenz@beispiel") == []
    assert _customer_items(True, "lenz@beispiel")[0]["label"] == "Herr Lenz"


def test_staff_does_not_find_by_phone():
    Customer.objects.create(name="", email="", phone="0151 2345678")
    assert _customer_items(False, "2345678") == []


def test_nameless_customer_label_is_masked_for_staff():
    Customer.objects.create(name="Ohne", email="ohnename@beispiel.de")
    Customer.objects.filter(email="ohnename@beispiel.de").update(name="")
    item = _customer_items(True, "ohnename")[0]
    assert "ohnename" in item["label"]  # владелец видит; сотрудник клиента без имени не найдёт


def test_owner_sees_full_contact():
    Customer.objects.create(name="Frau Kunz", email="kunz2@beispiel.de")
    assert _customer_items(True, "kunz2")[0]["sub"] == "kunz2@beispiel.de"


def test_view_passes_role(monkeypatch):
    from django.contrib.auth import get_user_model
    from django.test import RequestFactory

    from apps.core import views

    seen = {}
    monkeypatch.setattr(
        ps, "search", lambda t, q, owner=None, perms=None: seen.setdefault("owner", owner) or []
    )
    request = RequestFactory().get("/dashboard/palette/suche/", {"q": "ab"})
    request.user = get_user_model().objects.create_user(f"u-{uuid4().hex[:6]}", password="pw")
    request.tenant = TenantFactory.build()
    views.palette_search(request)
    assert seen["owner"] is False  # без Membership владельца — маска


def test_deal_row_masks_nameless_customer_email(monkeypatch):
    from apps.core import sales_page

    t = _tenant()
    nameless = Customer.objects.create(name="", email="geheim@beispiel.de")
    deal = type(
        "Tx",
        (),
        {"title": "Termin", "reference_code": "B-1", "customer": nameless, "manage_url": "/x/"},
    )()
    monkeypatch.setattr(sales_page, "visible_kinds", lambda tenant: ["booking"])
    from apps.core import transactions

    monkeypatch.setattr(
        transactions, "_managed_queryset", lambda kind, q, contact_search=True: [object()]
    )
    monkeypatch.setattr(transactions, "transaction_for", lambda kind, obj: deal)
    row = ps._deals(t, "geheim", owner=False)[0]
    assert "geheim@" not in row["sub"] and "@beispiel.de" in row["sub"]
    assert "geheim@beispiel.de" in ps._deals(t, "geheim", owner=True)[0]["sub"]
