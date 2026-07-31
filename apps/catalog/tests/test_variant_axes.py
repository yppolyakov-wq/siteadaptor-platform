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


def test_mixed_catalog_keeps_legacy_label_sizes():
    """Смешанный каталог: товар с осями НЕ должен вытеснять легаси-label из
    чипов и фильтра (иначе половина ассортимента становится ненаходимой)."""
    from apps.catalog.facets import CatalogFacets

    axed, legacy = _product("Kleid"), _product("Tee")
    ProductVariant.objects.create(product=axed, label="", size="S", color="Blau")
    ProductVariant.objects.create(product=legacy, label="100 g")
    facets = CatalogFacets()
    chips = facets.present(Product.objects.filter(is_active=True), {})["size_chips"]
    assert sorted(chips) == ["100 g", "S"]
    assert list(facets.apply(Product.objects.all(), {"groesse": "100 g"})) == [legacy]
    assert list(facets.apply(Product.objects.all(), {"groesse": "S"})) == [axed]


def test_size_facet_skips_sold_out_variant():
    """Чип показывает только доступный размер (остаток 0 → товар не в выдаче)."""
    from apps.catalog.facets import CatalogFacets

    p = _product("Kleid")
    ProductVariant.objects.create(product=p, label="", size="S", color="Blau", stock_quantity=0)
    assert list(CatalogFacets().apply(Product.objects.all(), {"groesse": "S"})) == []


def test_cart_form_field_set_unchanged_with_axes(settings):
    """Ловушка №2 плана: оси НЕ добавляют полей формы — замок buybox пинит набор
    ровно {csrf, product, variant, mod, qty}. Оси живут в data-атрибутах."""
    import re

    from django.template.loader import render_to_string

    settings.ROOT_URLCONF = "config.urls_tenant"
    p = _product()
    ProductVariant.objects.create(product=p, label="", size="S", color="Blau")
    html = render_to_string("storefront/_add_to_cart_form.html", {"product": p})
    names = set(re.findall(r'name="([a-z_]+)"', html))
    assert names <= {"csrfmiddlewaretoken", "product", "variant", "mod", "qty"}
    assert 'data-size="S"' in html and 'data-color="Blau"' in html


def test_variant_photo_exposed_for_swap(settings):
    """Фото варианта попадает в data-image — JS подменяет главное фото галереи."""
    from django.template.loader import render_to_string

    settings.ROOT_URLCONF = "config.urls_tenant"
    p = _product()
    ProductVariant.objects.create(
        product=p, label="M", images=[{"id": "a", "url": "/media/blau.webp"}]
    )
    html = render_to_string("storefront/_add_to_cart_form.html", {"product": p})
    assert 'data-image="/media/blau.webp"' in html
    assert "js-media-main" in html  # цель подмены — существующая галерея
