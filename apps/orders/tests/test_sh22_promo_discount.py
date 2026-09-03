"""SH-22 (фидбэк владельца 2026-09-03): «при заказе товара со скидкой просто
стоит цена со скидкой — должна быть прописана скидка на товар в заказе, и
учесть, если их несколько».

Снимок листовой цены (`OrderItem.list_price`) + акция + её название дают:
строку выгоды в составе, отдельные строки «Rabatt · Aktion „…“» в итогах (по
одной на кампанию) и структурные минус-строки в счёте (решение владельца Р-7).

План — `docs/order-feedback-plan-2026-09-03.md` §5.
"""

from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.models import Product
from apps.orders import editing
from apps.orders import services as order_services
from apps.orders.totals import order_totals
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _product(name="Saft", price="2.49", stock=30):
    return Product.objects.create(name={"de": name}, base_price=price, stock_quantity=stock)


def _promo(product, new="1.99", title="Sommer-Deal", limit=None):
    return Promotion.objects.create(
        title={"de": title},
        status="active",
        product=product,
        price_override=Decimal(new),
        compare_at_price=product.base_price,
        available_quantity=limit,
    )


def _req(path="/", tenant=None):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    return request


# ─────────────────────────── снимок ───────────────────────────


def test_order_line_keeps_list_price_and_campaign():
    product = _product()
    promo = _promo(product)
    order = order_services.create_order(items=[(product, 2)], name="K")
    item = order.items.get()
    assert item.unit_price == Decimal("1.99")
    assert item.list_price == Decimal("2.49")
    assert item.promotion_id == promo.pk
    assert item.promo_label == "Sommer-Deal"
    assert item.discount_per_unit == Decimal("0.50")
    assert item.discount_total == Decimal("1.00")
    assert item.list_total == Decimal("4.98")


def test_renamed_or_removed_campaign_keeps_the_snapshot():
    """Доктрина снимков: документ печатает то, что видел клиент.

    Переименование кампании и её удаление (у акций soft-delete, поэтому FK
    остаётся) не переписывают уже проданную строку."""
    product = _product()
    promo = _promo(product)
    order = order_services.create_order(items=[(product, 1)], name="K")
    Promotion.objects.filter(pk=promo.pk).update(title={"de": "Anderer Name"})
    item = order.items.get()
    assert item.promo_name == "Sommer-Deal"
    promo.delete()  # soft-delete: акция скрыта, снимок строки цел
    item.refresh_from_db()
    assert item.promo_name == "Sommer-Deal"
    assert item.discount_per_unit == Decimal("0.50")


def test_legacy_line_without_snapshot_shows_no_discount():
    product = _product()
    order = order_services.create_order(items=[(product, 1)], name="K")
    item = order.items.get()
    assert item.list_price is None
    assert item.discount_per_unit == Decimal("0") and item.list_total == Decimal("2.49")


# ─────────────────────────── итоги ───────────────────────────


def test_totals_split_promo_rows_per_campaign():
    """Несколько акций в заказе — несколько строк скидки."""
    saft = _product()
    brot = _product(name="Brot", price="3.20")
    _promo(saft)
    _promo(brot, new="1.70", title="Brot-Deal")
    order = order_services.create_order(items=[(saft, 2), (brot, 1)], name="K")
    totals = order_totals(order)
    labels = [r["label"] for r in totals["promo_rows"]]
    assert labels == ["Brot-Deal", "Sommer-Deal"]  # по убыванию суммы
    assert [r["amount"] for r in totals["promo_rows"]] == [Decimal("1.50"), Decimal("1.00")]
    assert totals["list_items"] == Decimal("8.18")  # 2×2,49 + 3,20
    assert totals["items"] == Decimal("5.68")


def test_totals_invariant_list_minus_promos_equals_gross():
    saft = _product()
    _promo(saft)
    order = order_services.create_order(items=[(saft, 3)], name="K")
    editing.set_discount(order, cents=100)
    totals = order_totals(order)
    expected = (
        totals["list_items"] - totals["promo_discount"] - totals["discount"] + totals["shipping"]
    )
    assert expected == totals["gross"] == order.total


def test_qty_change_scales_the_discount():
    product = _product()
    _promo(product)
    order = order_services.create_order(items=[(product, 4)], name="K")
    item = order.items.get()
    editing.set_item_qty(order, item.pk, 2)
    item.refresh_from_db()
    assert item.discount_total == Decimal("1.00")
    assert order_totals(order)["promo_rows"][0]["amount"] == Decimal("1.00")


# ─────────────────────────── показ ───────────────────────────


def test_cabinet_card_shows_promo_row_and_struck_price():
    from apps.orders import views

    tenant = TenantFactory(schema_name="public", slug="sh22", name="SH22", disabled_modules=[])
    product = _product()
    _promo(product)
    order = order_services.create_order(items=[(product, 2)], name="K")
    request = _req(f"/dashboard/orders/{order.pk}/", tenant)
    request.user = type("U", (), {"is_authenticated": True, "is_active": True})()
    body = views.order_detail(request, order.pk).content.decode()
    assert "data-promo-row" in body
    assert "Sommer-Deal" in body
    assert "2,49" in body and "1,99" in body  # зачёркнутая листовая и уплаченная


def test_promo_checkout_line_is_the_product_not_the_campaign():
    """Страница акции: в составе — товар, название акции идёт снимком."""
    from apps.promotions import services as promo_services

    product = _product()
    promo = _promo(promo_target := product)
    order = promo_services.purchase(promo, quantity=1, name="K")
    item = order.items.get()
    assert item.title_snapshot == str(promo_target)
    assert item.list_price == promo.old_price
    assert item.promo_label == "Sommer-Deal"


def test_cabinet_add_item_applies_the_active_promo_and_moves_the_limit():
    """Р-8: «Position hinzufügen» продаёт по акции и двигает её лимит."""
    product = _product()
    promo = _promo(product, limit=10)
    order = order_services.create_order(items=[(product, 1)], name="K")
    promo.refresh_from_db()
    assert promo.available_quantity == 9
    editing.add_item(order, product=product, qty=2)
    promo.refresh_from_db()
    assert promo.available_quantity == 7
    added = order.items.order_by("-created_at").first()
    assert added.unit_price == Decimal("1.99") and added.list_price == Decimal("2.49")
    assert any(m.get("promo") for m in added.modifiers)


def test_cabinet_add_item_keeps_an_explicit_price():
    product = _product()
    promo = _promo(product, limit=5)
    order = order_services.create_order(items=[(product, 1)], name="K")
    editing.add_item(order, product=product, qty=1, unit_price=Decimal("2.00"))
    promo.refresh_from_db()
    assert promo.available_quantity == 4  # первый заказ, добавление лимит не трогает
    added = order.items.order_by("-created_at").first()
    assert added.unit_price == Decimal("2.00") and added.list_price is None


# ─────────────────────────── счёт (Р-7) ───────────────────────────


def test_invoice_has_structural_minus_line_without_changing_the_money():
    """Р-7: позиция по листовой цене + минус-строка той же ставкой.

    Деньги счёта обязаны совпасть с прежним (описательным) вариантом: минус-
    строка считается как разница уже посчитанных нетто, а не отдельным делением
    — иначе два независимых округления уводили бы счёт на цент.
    """
    from apps.finance.services import invoice_from_order

    product = _product()
    _promo(product)
    order = order_services.create_order(items=[(product, 2)], name="K")
    invoice = invoice_from_order(order)
    texts = [line["text"] for line in invoice.lines]
    assert any("Rabatt" in t and "Sommer-Deal" in t for t in texts)
    assert texts.index("Saft") + 1 == next(  # минус-строка идёт СРАЗУ за позицией
        i for i, t in enumerate(texts) if "Rabatt" in t
    )

    # эталон: тот же заказ без снимка акции (одна строка по уплаченной цене)
    plain = _product(name="Saft2", price="1.99")
    plain_order = order_services.create_order(items=[(plain, 2)], name="K")
    plain_invoice = invoice_from_order(plain_order)
    assert invoice.net == plain_invoice.net
    assert invoice.vat_amount == plain_invoice.vat_amount
    assert invoice.gross == plain_invoice.gross
