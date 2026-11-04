"""FLT-4a: списки кабинета не теряют своё состояние при поиске и листании.

План — docs/flt4-cabinet-filters-plan-2026-11-04.md §0 (дефекты 1–4).
"""

import re

import pytest
from django.template import Context, Template
from django.test import RequestFactory

from apps.core.models import Membership
from apps.core.tests.test_staff_walk import _open, _tenant, _user

pytestmark = pytest.mark.django_db


def _form(html, marker):
    i = html.index(marker)
    start = html.rindex("<form", 0, i)
    return html[start : html.index("</form>", i)]


def _hidden(fragment):
    return dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', fragment))


def test_customer_search_inside_sales_tab_stays_on_the_tab():
    """Вкладка «Kunden» продаж: поиск и «Mehr anzeigen» раньше уводили на другую вкладку."""
    tenant = _tenant("bakery")
    html = _open("/dashboard/verkaeufe/?tab=kunden", tenant, _user(Membership.ROLE_OWNER))
    html = html.content.decode()
    assert _hidden(_form(html, 'name="q"')).get("tab") == "kunden"


def test_customer_search_on_crm_screen_has_no_tab_field():
    tenant = _tenant("bakery")
    tenant.disabled_modules = [m for m in tenant.disabled_modules if m != "crm"]
    tenant.save(update_fields=["disabled_modules"])
    resp = _open("/crm/", tenant, _user(Membership.ROLE_OWNER))
    if resp.status_code != 200:
        pytest.skip("CRM у этого типа выключен")
    assert "tab" not in _hidden(_form(resp.content.decode(), 'name="q"'))


def test_sortiment_search_keeps_kind_and_explicit_view():
    tenant = _tenant("shop")
    html = _open(
        "/dashboard/angebote/?art=product&ansicht=liste", tenant, _user(Membership.ROLE_OWNER)
    ).content.decode()
    sent = _hidden(_form(html, 'name="q"'))
    assert sent.get("art") == "product" and sent.get("ansicht") == "liste"


def test_sortiment_search_ignores_junk_view_and_kind():
    tenant = _tenant("shop")
    html = _open(
        "/dashboard/angebote/?art=evil&ansicht=x", tenant, _user(Membership.ROLE_OWNER)
    ).content.decode()
    sent = _hidden(_form(html, 'name="q"'))
    assert "art" not in sent and "ansicht" not in sent


def test_order_search_keeps_counter_filter_from_home():
    tenant = _tenant("bakery")
    html = _open(
        "/dashboard/verkaeufe/?tab=order&view=liste&zahlung=offen",
        tenant,
        _user(Membership.ROLE_OWNER),
    ).content.decode()
    sent = _hidden(_form(html, "Suche: Code, Name, E-Mail"))
    assert sent.get("zahlung") == "offen" and sent.get("view") == "liste"
    assert "abholung" not in sent


def test_pager_and_chip_links_drop_open_drawer():
    request = RequestFactory().get("/dashboard/finance/rechnungen/?status=paid&drawer=/x/&seite=3")
    out = Template("{% load cabinet %}{% query_with 'art' 'invoice' %}").render(
        Context({"request": request})
    )
    assert "drawer" not in out and "seite" not in out and "status=paid" in out
