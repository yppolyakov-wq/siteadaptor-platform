"""Склад-2 E1.5: врезка FEFO в атомик заказа/возврата.

Продажа гасит партии по ближайшему MHD (в той же atomic, что декремент счётчика);
возврат/отмена доливает партии обратно. Для товаров БЕЗ партий поведение прежнее
(паритет — партии не создаются, счётчик/леджер как раньше)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.tests.factories import ProductFactory
from apps.inventory.models import Lot
from apps.inventory.services import lot_balance, receive_lot
from apps.orders import services
from apps.orders.state_machine import OrderSM

pytestmark = pytest.mark.django_db


def _date(days):
    return timezone.localdate() + timedelta(days=days)


def test_order_sale_consumes_fefo_nearest_mhd_first():
    product = ProductFactory(base_price=Decimal("5.00"), stock_quantity=0)
    receive_lot(product=product, qty=10, mhd=_date(30), lot_code="far")
    receive_lot(product=product, qty=5, mhd=_date(3), lot_code="near")
    services.create_order(items=[(product, 7)], name="K")
    product.refresh_from_db()
    assert product.stock_quantity == 8  # 15 − 7 (счётчик как обычно)
    by = {lot.lot_code: lot.qty_remaining for lot in Lot.objects.filter(product=product)}
    assert by["near"] == 0  # ближайший MHD списан первым (5)
    assert by["far"] == 8  # затем дальний (2 из 10)
    assert lot_balance(product) == 8  # Σ партий == счётчик


def test_order_sale_without_lots_is_parity():
    # Товар без партий: продажа не создаёт партий, счётчик как раньше.
    product = ProductFactory(base_price=Decimal("5.00"), stock_quantity=10)
    services.create_order(items=[(product, 3)], name="K")
    product.refresh_from_db()
    assert product.stock_quantity == 7
    assert Lot.objects.filter(product=product).count() == 0  # партии не заведены


def test_cancel_restores_lots():
    product = ProductFactory(base_price=Decimal("5.00"), stock_quantity=0)
    receive_lot(product=product, qty=6, mhd=_date(5), lot_code="A")
    order = services.create_order(items=[(product, 4)], name="K")
    product.refresh_from_db()
    assert product.stock_quantity == 2 and lot_balance(product) == 2  # списано 4
    OrderSM().apply(order, "cancelled")
    product.refresh_from_db()
    assert product.stock_quantity == 6  # счётчик вернулся
    assert lot_balance(product) == 6  # партия долита обратно (реконсиляция)


def test_job_commit_consumes_fefo():
    from apps.jobs import services as job_services
    from apps.jobs.state_machine import JobSM

    product = ProductFactory(base_price=Decimal("5.00"), stock_quantity=0)
    receive_lot(product=product, qty=5, mhd=_date(4), lot_code="mat")  # counter 5, lot 5
    job = job_services.create_job(title="Reparatur", name="Kunde")
    job_services.set_lines(
        job, [{"text": "Teil", "qty": 2, "unit_price": "5.00", "product": product}]
    )
    sm = JobSM()
    for dst in ("quoted", "accepted", "done"):
        job = sm.apply(job, dst)
    product.refresh_from_db()
    assert product.stock_quantity == 3  # 5 − 2 (Materialverbrauch)
    assert lot_balance(product) == 3  # партия погашена FEFO


def test_order_sale_underflow_lots_capped_counter_is_truth():
    # Партий меньше, чем счётчик (частичный приход по партиям): продажа гасит партии
    # сколько есть, недостачу докрывает чистый счётчик (Σlot < счётчик — это ок).
    product = ProductFactory(base_price=Decimal("5.00"), stock_quantity=10)  # counter 10
    receive_lot(product=product, qty=3, mhd=_date(2), lot_code="only")  # counter→13, lot 3
    services.create_order(items=[(product, 5)], name="K")
    product.refresh_from_db()
    assert product.stock_quantity == 8  # 13 − 5
    assert lot_balance(product) == 0  # партия (3) исчерпана, остаток из счётчика
