"""KA-12 WR-6 (E3.2): массовая видимость/цена, CSV-выгрузка товаров, новые колонки импорта."""

import csv
import io
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import views
from apps.catalog.models import PriceLog, Product
from apps.imports.processors.product import ProductProcessor

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="post", data=None):
    factory = RequestFactory()
    request = factory.post("/x/", data or {}) if method == "post" else factory.get("/x/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"u-{uuid.uuid4().hex[:8]}", password="pw1234567"
    )
    return request


def _p(price="10.00", **kw):
    return Product.objects.create(name={"de": "Brot"}, base_price=Decimal(price), **kw)


def test_bulk_visibility_hides_and_shows_selected_only():
    a, b, c = _p(), _p(), _p()
    views.products_bulk_visibility(_req(data={"ids": [str(a.pk), str(b.pk)], "action": "hide"}))
    assert [x.is_active for x in Product.objects.filter(pk__in=[a.pk, b.pk])] == [False, False]
    c.refresh_from_db()
    assert c.is_active
    views.products_bulk_visibility(_req(data={"ids": [str(a.pk), "garbage"], "action": "show"}))
    a.refresh_from_db()
    assert a.is_active


@pytest.mark.parametrize(
    "mode,amount,expected",
    [
        ("pct", "-10", "9.00"),
        ("pct", "+25", "12.50"),
        ("eur", "-2,50", "7.50"),
        ("eur", "−20", "0.00"),  # не ниже нуля
        ("set", "4,99", "4.99"),
    ],
)
def test_bulk_price_modes_write_price_log(mode, amount, expected):
    p = _p()
    views.products_bulk_price(_req(data={"ids": [str(p.pk)], "mode": mode, "amount": amount}))
    p.refresh_from_db()
    assert p.base_price == Decimal(expected)
    assert PriceLog.objects.filter(product=p, price=Decimal(expected)).exists()


@pytest.mark.parametrize(
    "data",
    [
        {"mode": "set", "amount": "-1"},
        {"mode": "pct", "amount": "-95"},
        {"mode": "bogus", "amount": "1"},
        {"mode": "pct", "amount": "abc"},
        {"mode": "pct", "amount": "NaN"},
        {"mode": "set", "amount": "1e30"},
        {"mode": "eur", "amount": "-1e30"},
    ],
)
def test_bulk_price_rejects_bad_input(data):
    p = _p()
    views.products_bulk_price(_req(data={"ids": [str(p.pk)], **data}))
    p.refresh_from_db()
    assert p.base_price == Decimal("10.00")


def test_bulk_price_needs_preise_edit_permission():
    from apps.core.view_perms import rule_for

    assert "preise.edit" in str(rule_for("catalog:products-bulk-price"))
    assert "lager.export" in str(rule_for("catalog:products-export-csv"))


def test_export_csv_columns_round_trip_and_formula_guard():
    _p(sku="=HYPERLINK(1)", gtin="4006381333931", brand="Hof", vat_rate=Decimal("7.00"))
    response = views.products_export_csv(_req("get"))
    text = response.content.decode("utf-8").lstrip("﻿")
    rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
    assert rows[0]["sku"] == "'=HYPERLINK(1)"
    assert rows[0]["gtin"] == "4006381333931"
    assert rows[0]["vat_rate"] == "7.00"
    # каждая колонка выгрузки понятна импорту (CSV ходит туда-обратно)
    from apps.imports.views import PRODUCT_FIELDS

    known = {key for key, _ in PRODUCT_FIELDS}
    assert set(views._EXPORT_COLUMNS) <= known


def test_import_new_columns_presence_guard_and_vat_validation():
    proc = ProductProcessor()
    assert any(
        "vat_rate" in e
        for e in proc.validate({"name_de": "X", "base_price": "1", "vat_rate": "16"})
    )
    p = _p(sku="A1", gtin="123", brand="Hof", list_price=Decimal("12.00"))
    proc.create_or_update(
        {
            "name_de": "Brot",
            "base_price": "10",
            "sku": "A1",
            "gtin": "",
            "brand": "",
            "vat_rate": "7 %",
        },
        update_existing=True,
    )
    p.refresh_from_db()
    assert (p.gtin, p.brand, p.list_price, p.vat_rate) == (
        "123",
        "Hof",
        Decimal("12.00"),
        Decimal("7.00"),
    )


def test_export_guards_gtin_and_import_strips_guard():
    _p(sku="-5 Eis", gtin="=1+1")
    text = views.products_export_csv(_req("get")).content.decode("utf-8").lstrip("\ufeff")
    row = next(csv.DictReader(io.StringIO(text), delimiter=";"))
    assert row["gtin"] == "'=1+1" and row["sku"] == "'-5 Eis"
    ProductProcessor().create_or_update(
        {"name_de": "Eis", "base_price": "1", "sku": row["sku"]}, update_existing=True
    )
    assert Product.objects.filter(sku="-5 Eis").count() == 1


def test_generator_rejects_huge_axes_before_building_combos():
    from apps.catalog.tests.test_wr5_variant_generator import _post

    p = _p()
    sizes = ",".join(f"s{i}" for i in range(5000))
    views.variant_generate(_post({"sizes": sizes, "colors": sizes}), pk=p.pk)
    assert p.variants.count() == 0


def test_bulk_visibility_counts_only_changed():
    from django.contrib.messages import get_messages

    a, b = _p(), _p(is_active=False)
    request = _req(data={"ids": [str(a.pk), str(b.pk)], "action": "show"})
    views.products_bulk_visibility(request)
    assert [str(m) for m in get_messages(request)] == ["1 Produkte aktualisiert."]
