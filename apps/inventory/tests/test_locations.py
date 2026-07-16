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


# --- E2.2: кабинет (Standorte/Umlagerung/приёмка на локацию) ---


def _req(method="get", data=None):
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.tenants.tests.factories import TenantFactory

    req = getattr(RequestFactory(), method)("/dashboard/stock/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)

    class _User:
        is_authenticated = True
        is_active = True
        username = "chef"

    req.user = _User()
    req.tenant = TenantFactory.build(business_type="bakery")
    return req


def test_cabinet_location_create_first_is_default(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.inventory import views

    views.stock(_req("post", {"action": "location_create", "name": "Laden"}))
    views.stock(_req("post", {"action": "location_create", "name": "Lager hinten"}))
    laden = StockLocation.objects.get(name="Laden")
    assert laden.is_default is True  # первый Standort = Hauptlager
    assert StockLocation.objects.get(name="Lager hinten").is_default is False


def test_cabinet_transfer_action(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.inventory import views

    main, back = _locs()
    product = ProductFactory(stock_quantity=9)
    views.stock(
        _req(
            "post",
            {
                "action": "transfer",
                "entity": f"p{product.pk}",
                "src": str(main.pk),
                "dst": str(back.pk),
                "qty": "4",
            },
        )
    )
    product.refresh_from_db()
    assert product.stock_quantity == 9  # счётчик не тронут
    assert locations.location_balance(product, location=back) == 4


def test_cabinet_receipt_with_location(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.inventory import views

    main, back = _locs()
    product = ProductFactory(stock_quantity=0)
    views.stock(
        _req(
            "post",
            {
                "action": "receipt",
                "entity": f"p{product.pk}",
                "qty": "5",
                "location": str(back.pk),
            },
        )
    )
    product.refresh_from_db()
    assert product.stock_quantity == 5
    assert locations.location_balance(product, location=back) == 5  # приход на локацию
    assert locations.location_balance(product, location=None) == 0


def test_cabinet_renders_standorte_section(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.inventory import views

    _locs()
    html = views.stock(_req()).content.decode()
    assert "Standorte" in html and "Umlagern" in html  # секция + форма переброса


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
