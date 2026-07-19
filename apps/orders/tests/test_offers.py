"""LS-3 «Sofort-Angebot»: Offer/OfferLine + accept→Order через custom_lines.

План — docs/ls3-sofort-angebot-plan-2026-07-19.md. Предложение из чата
конвертируется в обычный Order (цены заморожены); оплата/сток/канбан —
существующими правилами orders. jobs не затронут (паритет = файлы не менялись).
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.tests.factories import ProductFactory
from apps.core.fsm import IllegalTransition
from apps.inbox.services import start_conversation
from apps.notifications.models import Notification
from apps.orders import offers, services
from apps.orders.models import Offer, Order
from apps.orders.state_machine import OfferSM

pytestmark = pytest.mark.django_db


def _conversation(email="kunde@test.de"):
    return start_conversation(subject="Frage", body="Haben Sie Torten?", email=email, name="Kim")


def _lines():
    return [
        {"kind": "", "ref_id": None, "title": "Sonderanfertigung", "unit_price": "45.00", "qty": 1}
    ]


# --- create_order(custom_lines=...) -------------------------------------------------


def test_create_order_custom_free_line():
    order = services.create_order(
        items=(), custom_lines=[("Beratung vor Ort", "30.00", 2)], name="K"
    )
    item = order.items.get()
    assert item.product is None and item.combo is None
    assert item.title_snapshot == "Beratung vor Ort"
    assert item.unit_price == Decimal("30.00") and item.qty == 2
    assert order.total == Decimal("60.00")
    assert order.currency == "EUR"


def test_create_order_custom_line_with_product_freezes_price_and_reserves_stock():
    product = ProductFactory(base_price=Decimal("10.00"), stock_quantity=5)
    order = services.create_order(
        items=(), custom_lines=[("Torte (Sonderpreis)", "8.50", 2, product)], name="K"
    )
    item = order.items.get()
    assert item.product_id == product.pk
    assert item.unit_price == Decimal("8.50")  # цена из строки, не из каталога
    product.refresh_from_db()
    assert product.stock_quantity == 3  # сток по обычным правилам


def test_create_order_custom_line_out_of_stock_rolls_back():
    product = ProductFactory(base_price=Decimal("10.00"), stock_quantity=1)
    with pytest.raises(services.OutOfStock):
        services.create_order(items=(), custom_lines=[("Torte", "8.50", 2, product)], name="K")
    assert Order.objects.count() == 0


def test_create_order_custom_line_qty_validation():
    with pytest.raises(ValueError):
        services.create_order(items=(), custom_lines=[("X", "1.00", 0)], name="K")
    with pytest.raises(services.EmptyOrder):
        services.create_order(items=(), custom_lines=(), name="K")


# --- send_offer ---------------------------------------------------------------------


def test_send_offer_creates_offer_with_snapshot_and_system_message():
    conv = _conversation()
    offer = offers.send_offer(
        conv,
        lines=[
            {"kind": "product", "ref_id": 7, "title": "Schokotorte", "unit_price": "24", "qty": 1},
            {"title": "Lieferung", "unit_price": "5,50", "qty": 1},  # запятая-цена ок
            {"title": "", "unit_price": "9.99"},  # без названия — отброшена
        ],
        note="Gerne bis Freitag.",
    )
    assert offer.status == Offer.STATUS_OPEN
    assert offer.customer_email == "kunde@test.de"  # снимок из треда
    assert offer.lines.count() == 2
    assert offer.total == Decimal("29.50")
    assert offer.lines.first().kind == "product" and offer.lines.first().ref_id == "7"
    # system-сообщение в ленте треда (письма о нём не шлются)
    assert conv.messages.filter(author_role="system", body__icontains="Angebot").exists()


def test_send_offer_emails_customer_with_dedupe():
    conv = _conversation()
    offer = offers.send_offer(conv, lines=_lines())
    n = Notification.objects.get(dedupe_key=f"offer:{offer.id}:sent:customer")
    assert n.recipient == "kunde@test.de"
    assert "45" in n.payload.get("body", "")


def test_send_offer_requires_lines():
    conv = _conversation()
    with pytest.raises(ValueError):
        offers.send_offer(conv, lines=[{"title": "", "unit_price": "x"}])


# --- accept / decline ---------------------------------------------------------------


def test_accept_offer_creates_order_and_links_thread():
    conv = _conversation()
    product = ProductFactory(base_price=Decimal("10.00"), stock_quantity=5)
    offer = offers.send_offer(
        conv,
        lines=[
            {
                "kind": "product",
                "ref_id": product.pk,
                "title": "Torte",
                "unit_price": "8.50",
                "qty": 2,
            },
            {"title": "Kerzen", "unit_price": "3.00", "qty": 1},
        ],
    )
    order = offers.accept_offer(offer, payment_method="on_site")
    offer.refresh_from_db()
    assert offer.status == Offer.STATUS_ACCEPTED and offer.order_id == order.pk
    assert order.total == Decimal("20.00")
    assert order.customer.email == "kunde@test.de"  # снимок предложения
    product.refresh_from_db()
    assert product.stock_quantity == 3  # товарная строка списала сток
    conv.refresh_from_db()
    assert (conv.ref_kind, conv.ref_id) == ("order", str(order.pk))
    assert conv.ref_label == order.reference_code
    assert conv.messages.filter(author_role="system", body__icontains="angenommen").exists()


def test_accept_offer_idempotent():
    conv = _conversation()
    offer = offers.send_offer(conv, lines=_lines())
    order1 = offers.accept_offer(offer)
    order2 = offers.accept_offer(offer)
    assert order1.pk == order2.pk and Order.objects.count() == 1


def test_accept_offer_gone_product_falls_back_to_free_line():
    conv = _conversation()
    product = ProductFactory(base_price=Decimal("10.00"), stock_quantity=5)
    offer = offers.send_offer(
        conv,
        lines=[
            {
                "kind": "product",
                "ref_id": product.pk,
                "title": "Torte",
                "unit_price": "8.50",
                "qty": 1,
            }
        ],
    )
    product.is_active = False
    product.save(update_fields=["is_active"])
    order = offers.accept_offer(offer)
    item = order.items.get()
    assert item.product is None  # деактивированный товар → свободная строка
    assert item.unit_price == Decimal("8.50")
    product.refresh_from_db()
    assert product.stock_quantity == 5  # сток не тронут


def test_accept_offer_rejects_expired_and_terminal():
    conv = _conversation()
    expired = offers.send_offer(
        conv, lines=_lines(), valid_until=timezone.localdate() - timedelta(days=1)
    )
    with pytest.raises(offers.OfferUnavailable):
        offers.accept_offer(expired)

    declined = offers.send_offer(conv, lines=_lines())
    offers.decline_offer(declined)
    with pytest.raises(offers.OfferUnavailable):
        offers.accept_offer(declined)


def test_decline_offer_and_owner_email_hook():
    conv = _conversation()
    offer = offers.send_offer(conv, lines=_lines())
    offers.decline_offer(offer)
    offer.refresh_from_db()
    assert offer.status == Offer.STATUS_DECLINED and offer.declined_at is not None
    assert conv.messages.filter(author_role="system", body__icontains="abgelehnt").exists()
    # идемпотентность: повторное отклонение — no-op
    offers.decline_offer(offer)


def test_offer_fsm_terminal_states_locked():
    conv = _conversation()
    offer = offers.send_offer(conv, lines=_lines())
    offers.accept_offer(offer)
    offer.refresh_from_db()
    with pytest.raises(IllegalTransition):
        OfferSM().apply(offer, Offer.STATUS_DECLINED)
