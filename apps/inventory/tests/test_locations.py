"""Склад-2 E2.1: мультисклад — баланс per-Standort + Umlagerung (счётчик = итого)."""

import pytest

from apps.catalog.tests.factories import ProductFactory
from apps.inventory import locations, services
from apps.inventory.models import StockLocation, StockMovement

pytestmark = pytest.mark.django_db


def _locs():
    main = StockLocation.objects.create(name="Laden", is_default=True)
    back = StockLocation.objects.create(name="Lager hinten")
    return main, back


def test_locations_enabled_only_above_one():
    assert locations.locations_enabled() is False
    StockLocation.objects.create(name="Laden", is_default=True)
    assert locations.locations_enabled() is False  # одна локация = один склад
    StockLocation.objects.create(name="Lager hinten")
    assert locations.locations_enabled() is True


def test_default_balance_is_counter_minus_nondefault():
    main, back = _locs()
    product = ProductFactory(stock_quantity=10)  # легаси: NULL-история = основной
    assert locations.location_balance(product, location=None) == 10
    assert locations.location_balance(product, location=back) == 0
    # приёмка на заднюю локацию: счётчик +5, ленджер located
    services.apply_manual_movement(
        product=product, kind=StockMovement.KIND_RECEIPT, delta=5, location=back
    )
    product.refresh_from_db()
    assert product.stock_quantity == 15
    assert locations.location_balance(product, location=back) == 5
    assert locations.location_balance(product, location=None) == 10  # дефолт не менялся
    rows = locations.location_rows(product)
    assert [(r["location"].name, r["qty"]) for r in rows] == [("Laden", 10), ("Lager hinten", 5)]
    assert sum(r["qty"] for r in rows) == product.stock_quantity  # Σ == счётчик


def test_transfer_moves_between_locations_without_counter():
    main, back = _locs()
    product = ProductFactory(stock_quantity=10)
    diff_before = services.reconciliation(product)["diff"]
    moved = locations.transfer(product=product, src=None, dst=back, qty=4)
    assert moved == 4
    product.refresh_from_db()
    assert product.stock_quantity == 10  # счётчик НЕ тронут
    assert locations.location_balance(product, location=None) == 6
    assert locations.location_balance(product, location=back) == 4
    # леджер: пара движений Σ=0 → реконсиляция леджер↔счётчик не съехала
    assert services.reconciliation(product)["diff"] == diff_before
    kinds = set(
        StockMovement.objects.filter(product=product, source="transfer").values_list(
            "kind", flat=True
        )
    )
    assert kinds == {"transfer_out", "transfer_in"}


def test_transfer_clamped_by_src_balance():
    main, back = _locs()
    product = ProductFactory(stock_quantity=3)
    moved = locations.transfer(product=product, src=None, dst=back, qty=99)
    assert moved == 3  # больше, чем есть на дефолте, не уводим
    assert locations.location_balance(product, location=None) == 0
    moved_back = locations.transfer(product=product, src=back, dst=None, qty=2)
    assert moved_back == 2
    assert locations.location_balance(product, location=back) == 1


def test_transfer_same_or_missing_locations_noop():
    product = ProductFactory(stock_quantity=5)
    assert locations.transfer(product=product, src=None, dst=None, qty=3) == 0  # локаций нет
    main, back = _locs()
    assert locations.transfer(product=product, src=main, dst=main, qty=3) == 0  # та же


def test_ledger_reconciliation_survives_transfers():
    main, back = _locs()
    product = ProductFactory(stock_quantity=0)
    services.apply_manual_movement(
        product=product, kind=StockMovement.KIND_RECEIPT, delta=8
    )  # леджер +8, счётчик 8
    product.refresh_from_db()
    assert services.reconciliation(product)["ok"] is True
    locations.transfer(product=product, src=None, dst=back, qty=5)
    product.refresh_from_db()
    assert services.reconciliation(product)["ok"] is True  # Σ transfers = 0
