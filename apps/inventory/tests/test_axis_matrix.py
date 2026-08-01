"""Разрез склада по осям варианта — матрица «размер × цвет» (2026-08-01).

Вопрос владельца: учитывается ли количество определённого цвета и размера
отдельно. Учёт был (единица = вариант), не было ЭКРАНА в разрезе осей.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.inventory import matrix, views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _grid(sizes=("S", "M"), colors=("Blau", "Rot"), stock=3):
    product = ProductFactory()
    for s in sizes:
        for c in colors:
            ProductVariant.objects.create(
                product=product,
                label=f"{s} · {c}",
                size=s,
                color=c,
                price="19.90",
                stock_quantity=stock,
            )
    return product


def _get(params=None):
    req = RequestFactory().get("/dashboard/stock/", params or {})
    req.tenant = TenantFactory.build()
    req.user = get_user_model()(username="o", is_active=True)
    req.session = {}
    req._messages = FallbackStorage(req)
    return req


def test_matrix_totals_answer_how_much_of_each_size_and_colour():
    product = _grid(stock=3)
    m = matrix.product_matrix(product)
    assert m["sizes"] == ["S", "M"] and m["colors"] == ["Blau", "Rot"]
    assert [r["total"] for r in m["rows"]] == [6, 6]  # всего размера S / размера M
    assert m["col_totals"] == [6, 6]  # всего синих / всего красных
    assert m["total"] == 12


def test_missing_combination_is_not_a_zero():
    """Пустая ячейка = такой комбинации нет. При инвентаризации разница с нулём
    принципиальна: ноль надо пересчитать, отсутствующего варианта не существует."""
    product = _grid()
    ProductVariant.objects.filter(product=product, label="M · Rot").delete()
    m = matrix.product_matrix(product)
    cells = {(r["size"], c): r["cells"][i] for r in m["rows"] for i, c in enumerate(m["colors"])}
    assert cells[("M", "Rot")]["variant"] is None
    assert cells[("M", "Rot")]["qty"] is None
    assert cells[("S", "Rot")]["qty"] == 3


def test_untracked_variant_does_not_count_as_zero():
    """stock_quantity=None — «без лимита», а не ноль: в сумму не идёт."""
    product = _grid()
    ProductVariant.objects.filter(product=product, label="S · Blau").update(stock_quantity=None)
    m = matrix.product_matrix(product)
    assert m["rows"][0]["total"] == 3  # только «S · Rot»
    assert m["total"] == 9


def test_no_matrix_without_both_axes():
    """Легаси-варианты одним label («100 g») — матрица выродилась бы в столбец."""
    product = ProductFactory()
    for label in ("100 g", "250 g"):
        ProductVariant.objects.create(product=product, label=label, price="4.90", stock_quantity=5)
    assert matrix.product_matrix(product) is None


def test_filter_narrows_flat_table_to_one_axis_value():
    rows = [
        {"value": "v1", "variant": v, "product": v.product}
        for v in _grid().variants.all().order_by("label")
    ]
    only_m = matrix.filter_rows(rows, size="M")
    assert {r["variant"].size for r in only_m} == {"M"}
    only_blue = matrix.filter_rows(rows, color="Blau")
    assert {r["variant"].color for r in only_blue} == {"Blau"}
    assert len(matrix.filter_rows(rows, size="M", color="Blau")) == 1


def test_filter_drops_products_without_variants():
    """У товара без вариантов нет ни размера, ни цвета — показывать его в выдаче
    «размер M» было бы враньём."""
    product = ProductFactory()
    rows = [{"value": f"p{product.pk}", "variant": None, "product": product}]
    assert matrix.filter_rows(rows, size="M") == []
    assert matrix.filter_rows(rows) == rows  # без фильтра — как было


def test_stock_page_shows_matrix_and_axis_filters():
    _grid()
    body = views.stock(_get()).content.decode()
    assert "Größe × Farbe" in body
    assert 'name="groesse"' in body and 'name="farbe"' in body

    filtered = views.stock(_get({"groesse": "M"})).content.decode()
    # Фильтр сужает ПЛОСКУЮ таблицу; матрица остаётся полной — она и есть обзор,
    # обрезать её до одной строки значило бы лишить смысла.
    flat = filtered[filtered.index(">Marge<") :]  # заголовок именно плоской таблицы
    flat = flat[: flat.index("</table>")]
    assert "M · Blau" in flat and "S · Blau" not in flat
    assert "Größe × Farbe" in filtered  # матрица на месте
    assert "Nur die gefilterten Artikel" in filtered  # предупреждение об Inventur


def test_csv_export_has_separate_axis_columns():
    """Склеенный label в Excel не сводится — нужны отдельные колонки."""
    from apps.inventory.models import StockMovement

    product = _grid()
    variant = product.variants.get(label="S · Blau")
    StockMovement.objects.create(
        product=product, variant=variant, kind="receipt", delta=5, source="manual"
    )
    body = views.stock(_get({"export": "csv"})).content.decode()
    header = body.splitlines()[0]
    assert "Größe" in header and "Farbe" in header
    assert ",S,Blau," in body.replace("\r", "")
