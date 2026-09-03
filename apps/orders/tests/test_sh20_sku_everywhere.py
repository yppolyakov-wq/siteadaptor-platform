"""SH-20 (фидбэк 2026-09-03): артикул рядом с товаром ВЕЗДЕ, где печатается позиция —
счёт (снимок JSON + экран + PDF), список продаж, KDS, письма, Offer (снимок + страница +
письма), пикер позиций. План — `docs/order-feedback-plan-2026-09-03.md` §3."""

from decimal import Decimal

import pytest
from django.template.loader import render_to_string

from apps.catalog.picker import _catalog_parts
from apps.catalog.tests.factories import ProductFactory
from apps.orders import offers, services
from apps.orders.models import Offer
from apps.orders.tests.test_offers import _conversation

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _order(sku="BR-001"):
    product = ProductFactory(
        base_price=Decimal("11.90"), stock_quantity=5, sku=sku, name={"de": "Brot"}
    )
    return services.create_order(items=[(product, 2)], name="Kunde", email="k@t.de")


def test_invoice_lines_carry_the_sku_and_screen_and_pdf_print_it():
    from apps.finance.pdf import build_invoice_pdf
    from apps.finance.services import invoice_from_order

    order = _order()
    invoice = invoice_from_order(order)
    assert invoice.lines[0]["sku"] == "BR-001"
    assert invoice.gross == Decimal("23.80")  # суммы байт-в-байт (compute_totals ключ игнорирует)
    body = render_to_string("finance/invoice_detail.html", {"invoice": invoice})
    assert "Art.-Nr." in body and "BR-001" in body
    from apps.tenants.tests.factories import TenantFactory

    assert build_invoice_pdf(invoice, TenantFactory.build())[:4] == b"%PDF"


def test_legacy_invoice_lines_without_sku_render_as_before():
    from apps.finance.models import Invoice

    inv = Invoice.objects.create(
        lines=[{"text": "Alt", "qty": 1, "unit_price": "10.00"}],
        vat_rate=Decimal("19"),
        net=Decimal("10"),
        vat_amount=Decimal("1.90"),
        gross=Decimal("11.90"),
    )
    body = render_to_string("finance/invoice_detail.html", {"invoice": inv})
    assert "Art.-Nr." not in body


def test_sales_rows_kds_and_emails_show_the_sku():
    order = _order()
    rows = render_to_string("orders/_order_rows.html", {"orders": [order]})
    assert "[BR-001]" in rows
    kds = render_to_string("orders/_kitchen_board.html", {"orders": [order]})
    assert "[BR-001]" in kds
    items = list(order.items.all())
    ctx = {"order": order, "items": items, "customer": order.customer}
    for tpl in ("order_anprobe_created", "order_anprobe_owner", "order_quote_created"):
        assert "BR-001" in render_to_string(f"emails/{tpl}.txt", ctx), tpl


def test_offer_snapshots_the_sku_and_prints_it_on_page_and_emails():
    product = ProductFactory(base_price=Decimal("24.00"), sku="TORTE-7", name={"de": "Schokotorte"})
    conv = _conversation()
    offer = offers.send_offer(
        conv,
        lines=[
            {
                "kind": "product",
                "ref_id": str(product.pk),
                "title": "Schokotorte",
                "unit_price": "24",
                "qty": 1,
            },
            {"title": "Lieferung", "unit_price": "5,50", "qty": 1},
            {
                "kind": "product",
                "ref_id": "7",
                "title": "Kaputt",
                "unit_price": "1",
                "qty": 1,
            },  # кривой ref
        ],
    )
    lines = list(offer.lines.all())
    assert lines[0].sku == "TORTE-7" and lines[1].sku == "" and lines[2].sku == ""
    body = render_to_string(
        "storefront/offer.html", {"offer": offer, "lines": lines, "business": "X"}
    )
    assert "TORTE-7" in body
    mail = render_to_string("emails/offer_sent.txt", {"offer": offer, "business": "X"})
    assert "TORTE-7" in mail
    # артикул — СНИМОК: переименование/смена артикула товара предложение не переписывает
    product.sku = "NEU-1"
    product.save(update_fields=["sku"])
    assert Offer.objects.get(pk=offer.pk).lines.first().sku == "TORTE-7"


def test_picker_carries_sku_in_label_but_title_stays_clean():
    product = ProductFactory(base_price=Decimal("3.00"), sku="BR-001", name={"de": "Brot"})
    part = next(p for p in _catalog_parts() if p["value"] == f"p:{product.pk}")
    assert part["sku"] == "BR-001" and "BR-001" in part["label"]
    assert part["title"] == "Brot"  # текст строки сметы/заказа — без артикула
