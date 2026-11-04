"""FLT-4b: строка фильтров списка кабинета (apps.core.list_filters + core/_list_filter_bar.html).

План — docs/flt4-cabinet-filters-plan-2026-11-04.md §1, §3.
"""

import re
from decimal import Decimal

import pytest
from django.test import RequestFactory

from apps.core import list_filters as lfm
from apps.finance import views as finance_views
from apps.finance.models import Invoice
from apps.finance.tests.test_invoices import _req

pytestmark = pytest.mark.django_db

FIELDS = (
    ("art", "Art", (("invoice", "Rechnung"), ("credit", "Gutschrift"))),
    ("von", "Von", ()),
)


def _build(query, keep=("tab", "view"), **kw):
    request = RequestFactory().get("/x/?" + query)
    fields = [
        lfm.Field("art", "Art", options=FIELDS[0][2], value=request.GET.get("art", "")),
        lfm.Field("von", "Von", kind="date", value=request.GET.get("von", "")),
    ]
    return lfm.build(request, fields, search_value=request.GET.get("q", ""), keep=keep, **kw)


def test_pill_removes_only_its_key_and_the_page_number():
    lf = _build("tab=a&art=credit&von=2026-10-01&q=Brot&sort=betrag&seite=4&drawer=/x/")
    pills = {p.label: p.url for p in lf.pills}
    art = pills["Art: Gutschrift"]
    assert "art=" not in art and "seite" not in art and "drawer" not in art
    assert "von=2026-10-01" in art and "q=Brot" in art and "sort=betrag" in art
    assert "q=" not in pills["„Brot“"] and "art=credit" in pills["„Brot“"]
    assert lf.active_count == 2  # поиск — не «фильтр шторки»


def test_drawer_carries_everything_it_does_not_edit():
    """W0: «Anzeigen» в шторке не теряет поиск, сортировку, вкладку и вид."""
    lf = _build("tab=a&view=liste&art=credit&q=Brot&q=Mehl&sort=betrag&seite=2")
    sent = lf.drawer_hidden
    assert ("tab", "a") in sent and ("view", "liste") in sent and ("sort", "betrag") in sent
    assert ("q", "Brot") in sent and ("q", "Mehl") in sent
    assert not any(k in ("art", "von", "seite") for k, _ in sent)
    assert not any(k == "q" for k, _ in lf.search_hidden)
    assert not any(k == "sort" for k, _ in lf.sort_hidden)


def test_reset_keeps_only_tab_and_view():
    assert _build("tab=a&view=liste&art=credit&q=x").reset_url == "?tab=a&view=liste"
    assert _build("art=credit", keep=()).reset_url == "?"


def test_junk_value_label_falls_back_and_bad_date_does_not_crash():
    request = RequestFactory().get("/x/")
    assert lfm.Field("a", "A", options=(("1", "Eins"),), value="9").value_label == "9"
    assert lfm.Field("d", "D", kind="date", value="nope").value_label == "nope"
    assert lfm.build(request, []).reset_url == "?"


# --- пилот «Rechnungen» -------------------------------------------------------------------


@pytest.fixture
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _inv(**kw):
    kw.setdefault("lines", [{"text": "Brot", "qty": 1, "unit_price": "1.00"}])
    kw.setdefault("gross", Decimal("10.00"))
    return Invoice.objects.create(**kw)


def _bar(html):
    i = html.index("data-list-filters")
    return html[i : html.index("</dialog>", i)]


def test_invoices_use_the_filter_bar_without_autosubmit(_tenant_urlconf):
    _inv(status=Invoice.STATUS_PAID, number=1, recipient="Erste Firma")
    html = finance_views.invoices(
        _req(data={"status": "paid", "art": "invoice", "q": "1", "sort": "betrag"})
    ).content.decode()
    bar = _bar(html)
    assert 'id="flt-drawer"' in bar and "onchange" not in bar
    drawer = bar[bar.index("data-lf-drawer") :]
    sent = re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', drawer)
    assert ("status", "paid") in sent and ("q", "1") in sent  # W0
    assert not any(k == "art" for k, _ in sent)
    assert "1 Treffer" in bar and "data-flt-pill" in bar
    assert "data-invoice-chip" in html  # статус — чипами со счётчиками, как раньше


# --- Verkäufe › Liste (FLT-4c) ------------------------------------------------------------


def _sales(kind, query):
    from apps.core.models import Membership
    from apps.core.tests.test_staff_walk import _open, _tenant, _user

    tenant = _tenant(kind)
    return _open("/dashboard/verkaeufe/" + query, tenant, _user(Membership.ROLE_OWNER))


def _drawer_hidden(html):
    bar = _bar(html)
    drawer = bar[bar.index("data-lf-drawer") :]
    return re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', drawer)


def test_order_list_bar_keeps_tab_view_and_counter_filter():
    html = _sales("bakery", "?tab=order&view=liste&zahlung=offen&q=Brot").content.decode()
    bar = _bar(html)
    assert "onchange" not in bar and 'name="status"' in bar and 'name="versand"' in bar
    sent = _drawer_hidden(html)
    assert ("tab", "order") in sent and ("view", "liste") in sent
    assert ("zahlung", "offen") in sent and ("q", "Brot") in sent  # W0
    assert "data-flt-pill" in bar  # фильтр счётчика виден и снимаем


def test_generic_list_bar_forces_tab_and_view_when_url_has_none():
    """Список открыт со вкладкой по умолчанию — поиск/шторка всё равно остаются в нём."""
    resp = _sales("hotel", "?view=liste")
    html = resp.content.decode()
    bar = _bar(html)
    assert 'name="status"' in bar and "onchange" not in bar
    sent = dict(_drawer_hidden(html))
    assert sent.get("view") == "liste" and sent.get("tab")


# --- Sortiment, Reservierungen (FLT-4d) ---------------------------------------------------


def test_sortiment_bar_has_status_in_drawer_and_keeps_kind():
    from apps.core.models import Membership
    from apps.core.tests.test_staff_walk import _open, _tenant, _user

    html = _open(
        "/dashboard/angebote/?art=product&status=1", _tenant("shop"), _user(Membership.ROLE_OWNER)
    ).content.decode()
    bar = _bar(html)
    assert 'name="status"' in bar and "onchange" not in bar
    assert ("art", "product") in _drawer_hidden(html)


def test_reservation_bar_without_search_and_junk_promotion_is_ignored():
    from apps.core.models import Membership
    from apps.core.tests.test_staff_walk import _open, _tenant, _user

    resp = _open(
        "/promotions/reservations/?promotion=not-a-uuid&status=offen",
        _tenant("bakery"),
        _user(Membership.ROLE_OWNER),
    )
    assert resp.status_code == 200
    bar = _bar(resp.content.decode())
    assert 'role="search"' not in bar and 'name="promotion"' in bar and "onchange" not in bar
