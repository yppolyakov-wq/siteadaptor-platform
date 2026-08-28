"""SH группа B (фидбэк владельца 2026-08-20): правка заказа из кабинета.

Главный инвариант волны — склад и леджер обязаны сходиться после ЛЮБОЙ правки
(решение владельца: «править всегда, склад пересчитывается тем же движком»).
Поэтому почти каждый замок ниже проверяет не только число на экране, но и
`ledger_balance` (класс дефекта T1: счётчик разошёлся с леджером).
"""

from decimal import Decimal

import pytest

from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.inventory.services import ledger_balance
from apps.orders import editing, services
from apps.orders.state_machine import OrderSM

pytestmark = pytest.mark.django_db


def _order(stock=10, qty=3, price="5.00"):
    product = ProductFactory(base_price=Decimal(price), stock_quantity=stock)
    order = services.create_order(items=[(product, qty)], name="Kunde", email="k@t.de")
    product.refresh_from_db()
    return order, product


def test_increase_qty_takes_stock_and_keeps_ledger_in_sync():
    order, product = _order(stock=10, qty=3)
    item = order.items.get()
    editing.set_item_qty(order, item.pk, 5)
    product.refresh_from_db()
    order.refresh_from_db()
    assert product.stock_quantity == 5  # было 7 после создания, ушло ещё 2
    assert ledger_balance(product) == product.stock_quantity - 10  # −5 от старта
    assert order.total == Decimal("25.00")


def test_decrease_qty_returns_stock():
    order, product = _order(stock=10, qty=3)
    item = order.items.get()
    editing.set_item_qty(order, item.pk, 1)
    product.refresh_from_db()
    order.refresh_from_db()
    assert product.stock_quantity == 9
    assert ledger_balance(product) == -1
    assert order.total == Decimal("5.00")


def test_qty_zero_removes_the_line_and_returns_everything():
    order, product = _order(stock=10, qty=3)
    item = order.items.get()
    editing.set_item_qty(order, item.pk, 0)
    product.refresh_from_db()
    order.refresh_from_db()
    assert product.stock_quantity == 10 and ledger_balance(product) == 0
    assert order.items.count() == 0 and order.total == Decimal("0.00")


def test_increase_beyond_stock_is_rejected_and_changes_nothing():
    order, product = _order(stock=4, qty=3)
    item = order.items.get()
    with pytest.raises(services.OutOfStock):
        editing.set_item_qty(order, item.pk, 9)
    product.refresh_from_db()
    item.refresh_from_db()
    assert product.stock_quantity == 1 and item.qty == 3  # откат полный


def test_untracked_product_qty_change_touches_no_stock():
    product = ProductFactory(base_price=Decimal("5.00"), stock_quantity=None)
    order = services.create_order(items=[(product, 1)], name="K")
    editing.set_item_qty(order, order.items.get().pk, 4)
    product.refresh_from_db()
    order.refresh_from_db()
    assert product.stock_quantity is None and order.total == Decimal("20.00")


def test_add_item_from_catalog_reserves_stock():
    order, product = _order(stock=10, qty=1)
    other = ProductFactory(base_price=Decimal("2.50"), stock_quantity=6)
    editing.add_item(order, product=other, qty=2)
    other.refresh_from_db()
    order.refresh_from_db()
    assert other.stock_quantity == 4 and ledger_balance(other) == -2
    assert order.total == Decimal("10.00")  # 5.00 + 2×2.50


def test_add_variant_item_reserves_variant_stock():
    order, _product = _order(stock=10, qty=1)
    p = ProductFactory(base_price=Decimal("3.00"))
    v = ProductVariant.objects.create(product=p, label="M", stock_quantity=2, price=Decimal("4.00"))
    editing.add_item(order, product=p, variant=v, qty=2)
    v.refresh_from_db()
    assert v.stock_quantity == 0 and ledger_balance(p, v) == -2


def test_add_free_line_does_not_touch_stock():
    order, product = _order(stock=10, qty=1)
    editing.add_item(order, title="Lieferung Sonderfahrt", unit_price=Decimal("12.00"), qty=1)
    product.refresh_from_db()
    order.refresh_from_db()
    assert product.stock_quantity == 9  # только исходная позиция
    assert order.total == Decimal("17.00")
    assert order.items.filter(product__isnull=True).count() == 1


def test_closed_order_is_not_editable():
    """Отменённый заказ склад уже вернул — повторное движение задвоило бы его."""
    order, product = _order(stock=10, qty=2)
    OrderSM().apply(order, "cancelled")
    product.refresh_from_db()
    assert product.stock_quantity == 10
    assert not editing.is_editable(order)
    with pytest.raises(editing.OrderLocked):
        editing.set_item_qty(order, order.items.get().pk, 1)
    product.refresh_from_db()
    assert product.stock_quantity == 10  # ничего не сдвинулось


def test_discount_and_shipping_enter_the_total_once():
    order, _product = _order(stock=10, qty=2, price="10.00")
    editing.set_discount(order, cents=500, note="TREUE")
    editing.update_delivery(order, fulfillment="delivery", address="Weg 1", shipping_cents=390)
    order.refresh_from_db()
    assert order.total == Decimal("18.90")  # 20.00 − 5.00 + 3.90
    assert order.is_delivery and order.shipping_address == "Weg 1"


def test_pickup_order_ignores_shipping_in_total():
    order, _product = _order(stock=10, qty=1, price="10.00")
    editing.update_delivery(order, fulfillment="pickup", shipping_cents=500)
    order.refresh_from_db()
    assert order.total == Decimal("10.00")


def test_update_customer_edits_the_same_contact():
    order, _product = _order()
    pk = order.customer.pk
    editing.update_customer(order, name="Neue Frau", phone="+49 111")
    order.refresh_from_db()
    assert order.customer.pk == pk  # дубля в CRM не завели
    assert order.customer.name == "Neue Frau" and order.customer.phone == "+49 111"
    assert order.customer.email == "k@t.de"  # пустое поле не затирает прежнее


# --- SH-3/4: налоги и итоги ---------------------------------------------------
def test_vat_is_extracted_from_gross_price():
    """Цены брутто (PAngV) — НДС выделяется из итога, а не доначисляется."""
    from apps.orders.totals import order_totals

    product = ProductFactory(base_price=Decimal("11.90"), stock_quantity=5, vat_rate=Decimal("19"))
    order = services.create_order(items=[(product, 1)], name="K")
    t = order_totals(order)
    assert t["gross"] == Decimal("11.90")
    assert t["net"] == Decimal("10.00") and t["vat"] == Decimal("1.90")


def test_two_rates_give_two_rows():
    """SH-4: на одном чеке законно соседствуют 19 % и 7 % (напиток + еда)."""
    from apps.orders.totals import order_totals

    drink = ProductFactory(base_price=Decimal("11.90"), stock_quantity=5, vat_rate=Decimal("19"))
    food = ProductFactory(base_price=Decimal("10.70"), stock_quantity=5, vat_rate=Decimal("7"))
    order = services.create_order(items=[(drink, 1), (food, 1)], name="K")
    rows = {r["rate"]: r for r in order_totals(order)["rows"]}
    assert set(rows) == {Decimal("19"), Decimal("7")}
    assert rows[Decimal("19")]["vat"] == Decimal("1.90")
    assert rows[Decimal("7")]["vat"] == Decimal("0.70")


def test_item_keeps_the_rate_snapshot_when_catalog_changes():
    product = ProductFactory(base_price=Decimal("10.70"), stock_quantity=5, vat_rate=Decimal("7"))
    order = services.create_order(items=[(product, 1)], name="K")
    product.vat_rate = Decimal("19")
    product.save(update_fields=["vat_rate"])
    assert order.items.get().vat_rate == Decimal("7.00")  # документ не переписан


def test_small_business_has_no_vat_at_all():
    """§ 19 UStG: Kleinunternehmer не выделяет НДС — иначе счёт был бы неверным."""
    from apps.orders.totals import order_totals

    product = ProductFactory(base_price=Decimal("11.90"), stock_quantity=5, vat_rate=Decimal("19"))
    order = services.create_order(items=[(product, 1)], name="K")
    t = order_totals(order, small_business=True)
    assert t["vat"] == Decimal("0.00") and t["net"] == Decimal("11.90")


def test_discount_and_shipping_are_inside_the_vat_base():
    """Скидка уменьшает базу НДС, доставка её увеличивает — сумма строк = итог."""
    from apps.orders.totals import order_totals

    product = ProductFactory(base_price=Decimal("50.00"), stock_quantity=5, vat_rate=Decimal("19"))
    order = services.create_order(items=[(product, 1)], name="K")
    editing.set_discount(order, cents=1000)
    editing.update_delivery(order, fulfillment="delivery", shipping_cents=500)
    order.refresh_from_db()
    t = order_totals(order)
    assert order.total == Decimal("45.00")
    assert t["gross"] == order.total
    assert t["net"] + t["vat"] == order.total


# --- SH-8/9: внешний номер, плательщик, счёт ----------------------------------
def test_external_code_is_found_by_deal_search():
    """Владелец диктует по телефону номер из кассы, а не наш код."""
    from apps.core import transactions

    order, _product = _order()
    order.external_code = "KASSE-7788"
    order.save(update_fields=["external_code"])
    found = transactions._managed_queryset("order", q="KASSE-77")
    assert list(found) == [order]


def test_invoice_from_order_snapshots_net_lines():
    """Счёт считает от НЕТТО, цены заказа брутто — разложение делает один хелпер."""
    from apps.finance.services import invoice_from_order

    product = ProductFactory(base_price=Decimal("11.90"), stock_quantity=5, vat_rate=Decimal("19"))
    order = services.create_order(items=[(product, 2)], name="Firma Meier", email="f@t.de")
    order.billing_name = "Meier GmbH"
    order.billing_address = "Hauptstr. 1\n40210 Düsseldorf"
    order.save(update_fields=["billing_name", "billing_address"])

    invoice = invoice_from_order(order)
    assert invoice.status == "draft" and invoice.number is None  # нумерация — при выставлении
    assert invoice.lines[0]["unit_price"] == "10.00" and invoice.lines[0]["qty"] == 2
    assert invoice.gross == Decimal("23.80")
    assert "Meier GmbH" in invoice.recipient and "40210" in invoice.recipient
    assert order.reference_code in invoice.note


def test_invoice_from_order_without_billing_uses_the_customer():
    from apps.finance.services import invoice_from_order

    order, _product = _order(price="10.00", qty=1)
    invoice = invoice_from_order(order)
    assert str(order.customer) in invoice.recipient


# --- VF-3 (фидбэк 2026-08-24): счёт/ссылка на оплату с карточки заказа --------


def _post_action(order, action, tenant=None):
    import uuid as _uuid

    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.orders import views

    request = RequestFactory().post(f"/dashboard/orders/{order.pk}/edit/", {"action": action})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    suffix = _uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{suffix}", email=f"o-{suffix}@test.de", password="pw12345678"
    )
    if tenant is not None:
        request.tenant = tenant
    return views.order_edit(request, pk=order.pk)


def test_invoice_pdf_action_reuses_draft():
    """«📄 Rechnung als PDF»: черновик по заказу переиспользуется — повторный
    клик не плодит дубли в Finanzen; редирект сразу в PDF."""
    from apps.finance.models import Invoice

    order, _product = _order(price="10.00", qty=1)
    resp = _post_action(order, "invoice_pdf")
    assert resp.status_code == 302 and resp["Location"].endswith("/pdf/")
    resp2 = _post_action(order, "invoice_pdf")
    assert resp2["Location"] == resp["Location"]
    assert Invoice.objects.filter(note__contains=order.reference_code).count() == 1


def test_payment_link_sends_email_with_pay_url():
    """«🔗 Zahlungslink senden»: письмо с прямой /bezahlen/; повторная отправка
    не глотается дедупом (суффикс-время)."""
    from apps.notifications.models import Notification
    from apps.tenants.models import Domain
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="public", slug="paylink-t", payments_enabled=True)
    Domain.objects.create(domain="paylink.test", tenant=tenant, is_primary=True)
    order, _product = _order(price="10.00", qty=1)
    order.payment_method = "stripe"
    order.save(update_fields=["payment_method"])
    resp = _post_action(order, "payment_link", tenant=tenant)
    assert resp.status_code == 302
    note = Notification.objects.filter(type="order_payment_link").order_by("-created_at").first()
    assert note is not None
    assert (
        f"https://paylink.test/bestellung/{order.reference_code}/bezahlen/" in note.payload["body"]
    )


def test_payment_link_refused_without_stripe():
    """Гейт зеркалит публичный /bezahlen/: без Zahlart Stripe письма нет."""
    from apps.notifications.models import Notification
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build(name="Shop Y", payments_enabled=True)
    order, _product = _order(price="10.00", qty=1)  # payment_method пуст
    before = Notification.objects.filter(type="order_payment_link").count()
    resp = _post_action(order, "payment_link", tenant=tenant)
    assert resp.status_code == 302
    assert Notification.objects.filter(type="order_payment_link").count() == before


@pytest.mark.django_db(transaction=True)
def test_add_item_runs_in_a_transaction():
    """Прод-500 2026-08-28: добавление товара в заказ из кабинета падало
    `TransactionManagementError: select_for_update cannot be used outside of a
    transaction`.

    Причина — хелпер `_vat_kwargs`, вставленный МЕЖДУ `@transaction.atomic` и
    `add_item`: декоратор достался хелперу, а сама функция осталась без
    транзакции. Обычные тесты этого не видят — pytest-django оборачивает каждый
    тест в транзакцию и маскирует дефект, поэтому здесь `transaction=True`
    (как в проде: ATOMIC_REQUESTS не включён).
    """
    product = ProductFactory(base_price=Decimal("5.00"), stock_quantity=10)
    order = services.create_order(items=[(product, 1)], name="K", email="k@t.de")
    other = ProductFactory(base_price=Decimal("2.50"), stock_quantity=6)

    editing.add_item(order, product=other, qty=2)

    other.refresh_from_db()
    assert other.stock_quantity == 4  # остаток списан, страница не упала
