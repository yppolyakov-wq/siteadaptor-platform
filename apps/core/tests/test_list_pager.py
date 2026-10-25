"""KA-P4a: списки кабинета не обрезаются молча — страницы по 50 и «1–50 von N».

План docs/ka-p4-pagination-plan-2026-10-23.md.
"""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.template import Context, Template
from django.test import RequestFactory

from apps.core import pagination, permissions, transactions, views
from apps.orders.models import Order
from apps.promotions.models import Customer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _orders(n, **kw):
    customer = Customer.objects.create(name="Kunde")
    return Order.objects.bulk_create(
        [
            Order(customer=customer, reference_code=f"O-{uuid.uuid4().hex[:10]}", **kw)
            for _ in range(n)
        ]
    )


def _req(path="/dashboard/verkaeufe/", data=None, **tenant_kw):
    request = RequestFactory().get(path, data or {})
    request.user = get_user_model().objects.create_user(
        username=f"p-{uuid.uuid4().hex[:10]}", password="pw12345678"
    )
    request.session = {}
    request._messages = FallbackStorage(request)
    tenant_kw.setdefault("disabled_modules", [])
    request.tenant = TenantFactory.build(**tenant_kw)
    return request


# --- ядро --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n", "raw", "page", "start", "end", "pages"),
    [
        (0, None, 1, 0, 0, 1),
        (1, None, 1, 1, 1, 1),
        (50, None, 1, 1, 50, 1),
        (51, "2", 2, 51, 51, 2),
        (120, "abc", 1, 1, 50, 3),
        (120, "-3", 1, 1, 50, 3),
        (120, "999", 3, 101, 120, 3),
    ],
)
def test_paginate_queryset_counts(n, raw, page, start, end, pages):
    _orders(n)
    p = pagination.paginate_queryset(Order.objects.all(), page_raw=raw)
    assert (p.page, p.start, p.end, p.pages, p.total) == (page, start, end, pages, n)


def test_equal_sort_keys_never_repeat_rows_between_pages():
    """bulk_create даёт заказы с одной меткой времени — без pk-ключа строки прыгали бы."""
    _orders(120)
    seen = []
    for n in (1, 2, 3):
        seen += [o.pk for o in pagination.paginate_queryset(Order.objects.all(), page_raw=n).items]
    assert len(seen) == len(set(seen)) == 120


def _pager(page, query):
    request = RequestFactory().get("/dashboard/verkaeufe/", query)
    tpl = Template("{% load cabinet %}{% list_pager page %}")
    return tpl.render(Context({"page": page, "request": request}))


def test_pager_carries_filters_and_drops_fragment_params():
    _orders(120)
    page = pagination.paginate_queryset(Order.objects.all(), page_raw="2")
    html = _pager(
        page, {"tab": "order", "view": "liste", "status": "ready", "q": '"><x', "box": "1"}
    )
    assert "51–100 von 120" in html
    assert "tab=order" in html and "status=ready" in html and "seite=3" in html
    assert "box=1" not in html
    assert "<x" not in html  # экранирование
    # «Zurück» на первую страницу — без ?seite
    assert 'href="/dashboard/verkaeufe/?tab=order' in html


def test_single_page_shows_only_the_count():
    _orders(3)
    html = _pager(pagination.paginate_queryset(Order.objects.all()), {})
    assert "3 Einträge" in html and 'rel="next"' not in html


# --- списки ------------------------------------------------------------------------


def test_order_list_reaches_the_201st_order():
    _orders(201)
    oldest = Order.objects.order_by("created_at", "pk").first()
    req = _req(data={"tab": "order", "view": "liste", "seite": "5"})
    from apps.core import sales_page

    ctx = sales_page.body_context(req, "order", "liste")
    assert ctx["page"].total == 201 and ctx["page"].start == 201
    assert [o.pk for o in ctx["orders"]] == [oldest.pk]


def test_order_list_count_follows_the_filter():
    _orders(60, status="ready")
    _orders(10)
    from apps.core import sales_page

    ctx = sales_page.body_context(
        _req(data={"tab": "order", "view": "liste", "status": "ready"}), "order", "liste"
    )
    assert ctx["page"].total == 60 and len(ctx["orders"]) == 50


def test_board_keeps_cards_for_every_column():
    """Раньше 50 на весь вид: свежие отменённые съедали лимит, и колонка «Neu»
    показывала счётчик без единой карточки."""
    _orders(5, status="new")
    _orders(60, status="cancelled")
    tenant = TenantFactory.build(disabled_modules=[])
    section = transactions.manage_sections_for(
        tenant, only="order", board_order=True, per_column=transactions.BOARD_COLUMN_LIMIT
    )[0]
    shown_new = [t for t in section["transactions"] if t.status == "new"]
    assert len(shown_new) == 5
    cancelled = next(c for c in section["columns"] if c["status"] == "cancelled")
    assert cancelled["count"] == 60 and cancelled["more"] == 40


def test_generic_list_section_is_paged():
    tenant = TenantFactory.build(disabled_modules=[])
    _orders(70)
    section = transactions.manage_sections_for(
        tenant, only="order", event_order=True, page_raw="2"
    )[0]
    assert section["page"].total == 70 and len(section["transactions"]) == 20


def test_sortiment_count_is_the_real_total(monkeypatch):
    from apps.catalog.models import Product
    from apps.core import sellable_manage

    monkeypatch.setattr("apps.inventory.views._threshold", lambda t: 0)
    Product.objects.bulk_create(
        [Product(name={"de": f"P{i}"}, base_price="1.00") for i in range(60)]
    )
    tenant = TenantFactory.build(disabled_modules=[])
    overview = sellable_manage.sellable_manage_sections_for(tenant, limit=50)
    product = next(s for s in overview if s["kind"] == "product")
    assert product["count"] == 60 and len(product["items"]) == 50
    paged = sellable_manage.sellable_manage_sections_for(tenant, kind_only="product", page_raw="2")
    assert [s["kind"] for s in paged] == ["product"] and len(paged[0]["items"]) == 10


def test_invoice_list_is_paged_and_bad_customer_id_does_not_crash():
    from decimal import Decimal

    from apps.finance import views as fviews
    from apps.finance.models import Invoice

    Invoice.objects.bulk_create(
        [
            Invoice(lines=[], net=Decimal("1"), vat_amount=Decimal("0"), gross=Decimal("1"))
            for _ in range(55)
        ]
    )
    req = _req(path="/dashboard/finance/rechnungen/", data={"seite": "2"})
    body = fviews.invoices(req).content.decode()
    assert "51–55 von 55" in body

    post = RequestFactory().post(
        "/dashboard/finance/rechnungen/",
        {"customer": "garbage", "line_text_1": "Brot", "line_qty_1": "1", "line_price_1": "2"},
    )
    post.user, post.session, post.tenant = req.user, {}, req.tenant
    post._messages = FallbackStorage(post)
    resp = fviews.invoices(post)
    assert resp.status_code == 302


def test_home_pager_points_to_the_sales_page():
    _orders(60)
    page = pagination.paginate_queryset(Order.objects.all())
    request = RequestFactory().get("/dashboard/")
    tpl = Template("{% load cabinet %}{% list_pager page base=base %}")
    html = tpl.render(
        Context(
            {
                "page": page,
                "request": request,
                "base": "/dashboard/verkaeufe/",
                "pager_params": {"tab": "order", "view": "liste"},
            }
        )
    )
    assert 'href="/dashboard/verkaeufe/?' in html and "tab=order" in html


def test_views_module_exposes_the_sortiment_limit():
    assert views.SORTIMENT_OVERVIEW_LIMIT == 50


# --- P4a-2 -------------------------------------------------------------------------


def test_inbox_list_is_paged():
    from apps.inbox import views as iviews
    from apps.inbox.models import Conversation

    Conversation.objects.bulk_create([Conversation(subject=f"S{i}") for i in range(55)])
    body = iviews.inbox_list(_req(path="/dashboard/inbox/", data={"seite": "2"})).content.decode()
    assert "51–55 von 55" in body


def test_journal_total_covers_the_whole_period_not_the_page():
    from decimal import Decimal

    from django.utils import timezone

    from apps.finance import views as fviews
    from apps.finance.models import RevenueEntry

    today = timezone.localdate()
    RevenueEntry.objects.bulk_create(
        [RevenueEntry(date=today, amount=Decimal("1.00"), source_ref=f"r{i}") for i in range(60)]
    )
    req = _req(
        path="/dashboard/finance/", data={"von": today.isoformat(), "bis": today.isoformat()}
    )
    body = fviews.journal(req).content.decode()
    assert "1–50 von 60" in body
    assert "60,00" in body or "60.00" in body


def test_payments_page_pages_and_counts_everything():
    from apps.core import payments_page

    _orders(55, payment_state="unpaid")
    tenant = TenantFactory.build(disabled_modules=[])
    assert payments_page.payment_count(tenant, "open") == 55
    page2 = payments_page.payment_rows(tenant, "open", limit=50, offset=50)
    assert len(page2) == 5
    assert payments_page.payment_summary(tenant)["open_count"] == 55


# --- P4b: выбор клиента в счёте ----------------------------------------------------


def _customers(n):
    return Customer.objects.bulk_create(
        [Customer(name=f"Kunde {i:04d}", email=f"k{i}@example.com") for i in range(n)]
    )


def test_201st_customer_is_found_and_invoiced():
    from apps.finance import views as fviews
    from apps.finance.models import Invoice

    _customers(210)
    last = Customer.objects.order_by("-name").first()  # «Kunde 0209» — за прежними 200
    body = fviews.invoices(
        _req(path="/dashboard/finance/rechnungen/", data={"kunde_q": "0209"})
    ).content.decode()
    assert f'value="{last.pk}"' in body

    req = _req(path="/dashboard/finance/rechnungen/")
    post = RequestFactory().post(
        "/dashboard/finance/rechnungen/",
        {"customer": str(last.pk), "line_text_1": "Brot", "line_qty_1": "1", "line_price_1": "2"},
    )
    post.user, post.session, post.tenant = req.user, {}, req.tenant
    post._messages = FallbackStorage(post)
    fviews.invoices(post)
    assert Invoice.objects.filter(customer=last).exists()


def test_customer_search_json_masks_contact_for_staff(monkeypatch):
    import json

    from apps.finance import views as fviews

    _customers(3)
    req = _req(path="/dashboard/finance/kunden-suche/", data={"q": "Kunde 0001"})
    # E6.7g: контакты видны staff по умолчанию — маскируем, когда право отозвано.
    monkeypatch.setattr(
        "apps.core.permissions.effective",
        lambda user: permissions.PRESETS["staff"] - {"kunden.kontakte"},
    )
    data = json.loads(fviews.customer_search(req).content)
    assert [i["label"] for i in data["items"]] == ["Kunde 0001"]
    assert "k1@example.com" not in data["items"][0]["sub"]
    short = _req(path="/dashboard/finance/kunden-suche/", data={"q": "K"})
    assert json.loads(fviews.customer_search(short).content)["items"] == []


def test_preselected_customer_is_always_in_the_list():
    from apps.finance import views as fviews

    _customers(60)
    oldest = Customer.objects.order_by("created_at", "pk").first()
    body = fviews.invoices(
        _req(path="/dashboard/finance/rechnungen/", data={"customer": str(oldest.pk)})
    ).content.decode()
    assert f'value="{oldest.pk}" selected' in body


def test_staff_sees_masked_contact_and_cannot_search_by_it(monkeypatch):
    from apps.finance import views as fviews

    Customer.objects.create(name="", email="anna@beispiel.de")
    # E6.7g: контакты видны staff по умолчанию — маскируем, когда право отозвано.
    monkeypatch.setattr(
        "apps.core.permissions.effective",
        lambda user: permissions.PRESETS["staff"] - {"kunden.kontakte"},
    )
    body = fviews.invoices(_req(path="/dashboard/finance/rechnungen/")).content.decode()
    assert "anna@beispiel.de" not in body and "•••@beispiel.de" in body
    hit = fviews.invoices(
        _req(path="/dashboard/finance/rechnungen/", data={"kunde_q": "anna@"})
    ).content.decode()
    assert "•••@beispiel.de" not in hit
