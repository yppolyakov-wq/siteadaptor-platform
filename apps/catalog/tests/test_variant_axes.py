"""M4-A (план m4a-variant-axes-plan-2026-07-31): оси варианта size/color
добавлены РЯДОМ с label — существующие подсистемы (склад/заказы/импорт) держатся
на label и не должны сломаться."""

import pytest

from apps.catalog.models import Product, ProductVariant

pytestmark = pytest.mark.django_db


def _product(name="Wollmantel"):
    return Product.objects.create(name={"de": name}, base_price="129.00", is_active=True)


def test_label_generated_from_axes_when_empty():
    v = ProductVariant.objects.create(product=_product(), label="", size="S", color="Blau")
    assert v.label == "S · Blau"


def test_single_axis_gives_plain_label():
    v = ProductVariant.objects.create(product=_product(), label="", size="M")
    assert v.label == "M"


def test_manual_label_is_never_overwritten():
    """Старые варианты и ручной ввод остаются как есть — на label держатся
    позиции заказа, склад-леджер и CSV-импорт."""
    v = ProductVariant.objects.create(product=_product(), label="100 g", size="S", color="Rot")
    assert v.label == "100 g"
    v.size = "L"
    v.save()
    assert v.label == "100 g"


def test_no_axes_behaves_exactly_as_before():
    v = ProductVariant.objects.create(product=_product(), label="6er-Pack")
    assert (v.size, v.color) == ("", "")
    assert v.label == "6er-Pack"


def test_variant_image_url_and_fallback():
    p = _product()
    plain = ProductVariant.objects.create(product=p, label="S")
    assert plain.image_url == ""
    with_img = ProductVariant.objects.create(
        product=p, label="M", images=[{"id": "a", "url": "/media/v.webp"}]
    )
    assert with_img.image_url == "/media/v.webp"


def test_size_chips_use_axis_not_cartesian_label():
    """Ловушка №1 плана: с осями чипы обязаны быть «S/M», а не «S · Blau»."""
    from apps.catalog.facets import CatalogFacets

    p = _product()
    for size in ("S", "M"):
        for color in ("Blau", "Rot"):
            ProductVariant.objects.create(product=p, label="", size=size, color=color)
    chips = CatalogFacets().present(Product.objects.filter(is_active=True), {})["size_chips"]
    assert sorted(chips) == ["M", "S"]


def test_size_chips_fall_back_to_label_without_axes():
    """Без осей — прежнее поведение (легаси-товары с «100 g»/«250 g»)."""
    from apps.catalog.facets import CatalogFacets

    p = _product()
    ProductVariant.objects.create(product=p, label="100 g")
    ProductVariant.objects.create(product=p, label="250 g")
    chips = CatalogFacets().present(Product.objects.filter(is_active=True), {})["size_chips"]
    assert sorted(chips) == ["100 g", "250 g"]


def test_size_facet_filters_by_axis():
    """Клик по чипу «S» должен что-то найти — фильтр и чипы смотрят в одно поле."""
    from apps.catalog.facets import CatalogFacets

    small, large = _product("Mantel"), _product("Hose")
    ProductVariant.objects.create(product=small, label="", size="S", color="Blau")
    ProductVariant.objects.create(product=large, label="", size="XL", color="Blau")
    found = CatalogFacets().apply(Product.objects.all(), {"groesse": "S"})
    assert list(found) == [small]
