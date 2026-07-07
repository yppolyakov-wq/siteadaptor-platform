"""U-D3.2: врезка склад-леджера в orders(sale/restore) + jobs(commit).

Ключевой инвариант реконсиляции: delta движения == фактическое изменение
счётчика (движки склад не заменены — леджер логирует их append-only)."""

from decimal import Decimal

import pytest

from apps.catalog.tests.factories import ProductFactory
from apps.inventory.models import StockMovement
from apps.inventory.services import ledger_balance

pytestmark = pytest.mark.django_db


def test_order_sale_logs_movement_matching_counter_change():
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal("8.00"), stock_quantity=10)
    create_order(items=[(product, 3)], name="Max", email="m@test.de")
    product.refresh_from_db()
    assert product.stock_quantity == 7  # счётчик двинул движок _reserve_stock
    mv = StockMovement.objects.filter(product=product, kind="sale")
    assert mv.count() == 1 and mv.first().delta == -3
    assert ledger_balance(product) == product.stock_quantity - 10  # delta == Δсчётчика


def test_untracked_product_logs_no_movement():
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal("8.00"), stock_quantity=None)
    create_order(items=[(product, 2)], name="Max", email="m@test.de")
    assert not StockMovement.objects.filter(product=product).exists()


def test_order_cancel_logs_return_movement():
    from apps.orders.services import create_order
    from apps.orders.state_machine import OrderSM

    product = ProductFactory(base_price=Decimal("8.00"), stock_quantity=10)
    order = create_order(items=[(product, 3)], name="Max", email="m@test.de")
    OrderSM().apply(order, "cancelled")  # new→cancelled → _restore_stock
    product.refresh_from_db()
    assert product.stock_quantity == 10  # остаток вернулся
    assert StockMovement.objects.filter(product=product, kind="return", delta=3).count() == 1
    assert ledger_balance(product) == 0  # -3 (sale) + 3 (return)


def test_job_commit_logs_actual_consumption_after_clamp():
    from apps.jobs import services
    from apps.jobs.state_machine import JobSM

    job = services.create_job(title="Reparatur", name="Kunde")
    product = ProductFactory(stock_quantity=2)
    services.set_lines(job, [{"text": "Teil", "qty": 5, "unit_price": "5.00", "product": product}])
    sm = JobSM()
    for dst in ("quoted", "accepted", "done"):
        job = sm.apply(job, dst)
    product.refresh_from_db()
    assert product.stock_quantity == 0  # клампнуто (нехватка)
    mv = StockMovement.objects.filter(product=product, kind="commit")
    assert mv.count() == 1 and mv.first().delta == -2  # ФАКТИЧЕСКИЙ расход, не −5
    assert ledger_balance(product) == -2
