"""T-8.26 п.3 (3a): остаток, изменённый массовым `.update()`, доезжает до снимка каталога
города через хук на леджере (`StockMovement`). План — docs/t8-26-3-stock-sync-plan-2026-10-16.md."""

import ast
import pathlib
from decimal import Decimal
from unittest import mock

import pytest
from django.db import transaction

from apps.aggregator import stock_sync, tasks
from apps.aggregator.models import AggregatorListing
from apps.catalog.models import Product
from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement
from apps.orders import services as order_services
from apps.orders.state_machine import OrderSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

PHOTO = [{"url": "/media/demo/jacke.webp", "is_primary": True}]


def _tenant():
    return TenantFactory(schema_name="public", slug="walder", name="Walder Faden", city="Solingen")


def _product(**kw):
    kw.setdefault("name", {"de": "Winterjacke"})
    kw.setdefault("base_price", Decimal("89.00"))
    kw.setdefault("images", PHOTO)
    return Product.objects.create(**kw)


@pytest.fixture
def enqueued(monkeypatch):
    calls = []
    monkeypatch.setattr(
        tasks.sync_aggregator_product,
        "apply_async",
        lambda kwargs=None, countdown=None, **kw: calls.append((kwargs, countdown)),
    )
    return calls


def test_order_cancel_mass_update_enqueues_product_sync(
    enqueued, django_capture_on_commit_callbacks
):
    _tenant()
    product = _product(stock_quantity=3)
    with django_capture_on_commit_callbacks(execute=True):
        order = order_services.create_order(items=[(product, 2)], name="K")
    enqueued.clear()
    with django_capture_on_commit_callbacks(execute=True):
        OrderSM().apply(order, "cancelled")  # _restore_stock = .update(F + qty)
    assert enqueued, "возврат остатка через .update() не поставил синк товара"
    kwargs, countdown = enqueued[-1]
    assert kwargs["product_id"] == str(product.pk) and kwargs["tenant_schema"] == "public"
    assert kwargs["dedupe_key"].startswith(f"agg-stock:public:{product.pk}:")
    assert countdown == stock_sync.SYNC_BUCKET


def test_burst_in_one_window_coalesces_to_one_key(enqueued, django_capture_on_commit_callbacks):
    _tenant()
    product = _product(stock_quantity=10)
    with mock.patch("apps.aggregator.stock_sync.time.time", return_value=1_000_000.0):
        with django_capture_on_commit_callbacks(execute=True):
            for i in range(5):
                record_movement(
                    product=product, delta=-1, kind=StockMovement.KIND_SALE, source=f"t{i}"
                )
    keys = {k["dedupe_key"] for k, _ in enqueued}
    assert len(enqueued) == 5 and len(keys) == 1  # idempotent_task выполнит один синк


def test_transfer_between_locations_does_not_enqueue(enqueued, django_capture_on_commit_callbacks):
    _tenant()
    product = _product(stock_quantity=10)
    with django_capture_on_commit_callbacks(execute=True):
        record_movement(product=product, delta=-2, kind=StockMovement.KIND_TRANSFER_OUT)
        record_movement(product=product, delta=2, kind=StockMovement.KIND_TRANSFER_IN)
    assert enqueued == []


def test_sold_out_after_cancel_flips_back_without_mocks():
    _tenant()
    product = _product(stock_quantity=1)
    order = order_services.create_order(items=[(product, 1)], name="K")
    assert tasks.sync_product_listing("public", product.pk) == "upserted"
    row = AggregatorListing.objects.get(listing_kind="product", source_ref=str(product.pk))
    assert row.availability == "sold_out"
    with transaction.atomic():
        OrderSM().apply(order, "cancelled")
    assert tasks.sync_product_listing("public", product.pk) == "upserted"
    row.refresh_from_db()
    assert row.availability == ""


# --- скан-замок: каждый массовый .update() остатка сопровождается движением леджера ------

_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _calls_in(node, name):
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            f = sub.func
            if (isinstance(f, ast.Name) and f.id == name) or (
                isinstance(f, ast.Attribute) and f.attr == name
            ):
                return True
    return False


def _update_calls(tree, keyword):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "update"
                    and any(k.arg == keyword for k in sub.keywords)
                ):
                    yield node


def _source_files():
    for path in _ROOT.glob("**/*.py"):
        parts = path.parts
        if "tests" in parts or "migrations" in parts or path.name.startswith("test_"):
            continue
        yield path


@pytest.mark.parametrize("keyword,guard", [("stock_quantity", "record_movement")])
def test_every_mass_stock_update_sits_next_to_ledger_movement(keyword, guard):
    offenders = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in _update_calls(tree, keyword):
            if not _calls_in(fn, guard):
                offenders.append(f"{path.relative_to(_ROOT)}::{fn.name}")
    assert not offenders, offenders


def test_every_promotion_limit_update_touches_listing():
    """3b (Р-2): лимит акции меняется только .update() — рядом обязан стоять touch_promotion."""
    offenders = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in _update_calls(tree, "available_quantity"):
            if not _calls_in(fn, "touch_promotion"):
                offenders.append(f"{path.relative_to(_ROOT)}::{fn.name}")
    assert not offenders, offenders
