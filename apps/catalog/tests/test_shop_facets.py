"""OS-1 (план online-shop-demo-plan-2026-09-03): магазинные фасеты каталога —
цвет, мультивыбор размера/цвета, «только со скидкой», счётчики и пилюли.

Разведка 2026-09-03 показала, что ось `ProductVariant.color` хранится и свотчи на
детали уже рисуются, а фильтра на листинге нет вовсе; размер выбирался ровно
один; счётчиков не было. Замки фиксируют новое поведение и границы: скидка
считается ТЕМ ЖЕ резолвером, что рисует промо-цену на карточке, а обе оси
сужают ОДИН вариант."""

from decimal import Decimal

import pytest
from django.http import QueryDict

from apps.catalog.facets import CatalogFacets
from apps.catalog.models import Product, ProductVariant

pytestmark = pytest.mark.django_db


def _product(name, price="49.00", **kw):
    return Product.objects.create(name={"de": name}, base_price=price, is_active=True, **kw)


def _qd(pairs):
    """QueryDict из списка пар — мультивыбор без него не воспроизвести."""
    qd = QueryDict(mutable=True)
    for key, value in pairs:
        qd.appendlist(key, value)
    return qd


def _all():
    return Product.objects.filter(is_active=True)


def test_color_chips_carry_hex_and_count():
    shirt, coat = _product("Shirt"), _product("Mantel")
    for prod in (shirt, coat):
        ProductVariant.objects.create(product=prod, label="", size="M", color="Sand")
    ProductVariant.objects.create(product=shirt, label="", size="M", color="Petrol")
    chips = CatalogFacets().present(_all(), {})["color_chips"]
    by_value = {c["value"]: c for c in chips}
    assert by_value["Sand"]["count"] == 2  # два ТОВАРА, не два варианта
    assert by_value["Petrol"]["count"] == 1
    assert by_value["Sand"]["hex"].startswith("#")  # из явного реестра COLOR_HEX


def test_single_color_hides_the_facet():
    """Один цвет на весь срез — не фильтр, а шум (то же правило, что у размера)."""
    prod = _product("Shirt")
    ProductVariant.objects.create(product=prod, label="", size="M", color="Sand")
    assert CatalogFacets().present(_all(), {})["color_chips"] == []


def test_color_filter_selects_products():
    shirt, coat = _product("Shirt"), _product("Mantel")
    ProductVariant.objects.create(product=shirt, label="", size="M", color="Sand")
    ProductVariant.objects.create(product=coat, label="", size="M", color="Petrol")
    found = CatalogFacets().apply(_all(), _qd([("farbe", "Sand")]))
    assert list(found) == [shirt]


def test_multi_select_size_is_a_union():
    small, large, huge = _product("S-Teil"), _product("L-Teil"), _product("XXL-Teil")
    ProductVariant.objects.create(product=small, label="", size="S", color="Sand")
    ProductVariant.objects.create(product=large, label="", size="L", color="Sand")
    ProductVariant.objects.create(product=huge, label="", size="XXL", color="Sand")
    found = CatalogFacets().apply(_all(), _qd([("groesse", "S"), ("groesse", "L")]))
    assert set(found) == {small, large}


def test_size_and_color_must_meet_in_one_variant():
    """«M» + «Sand» = есть песочный в размере M. Товар, у которого M только в
    другом цвете, а песочный только в другом размере, в выдачу не попадает —
    иначе фильтр обещает то, чего купить нельзя."""
    honest, liar = _product("Ehrlich"), _product("Falsch")
    ProductVariant.objects.create(product=honest, label="", size="M", color="Sand")
    ProductVariant.objects.create(product=liar, label="", size="M", color="Petrol")
    ProductVariant.objects.create(product=liar, label="", size="L", color="Sand")
    found = CatalogFacets().apply(_all(), _qd([("groesse", "M"), ("farbe", "Sand")]))
    assert list(found) == [honest]


def test_sold_out_variant_drops_out_of_the_colour_filter():
    prod = _product("Shirt")
    ProductVariant.objects.create(product=prod, label="", size="M", color="Sand", stock_quantity=0)
    assert CatalogFacets().apply(_all(), _qd([("farbe", "Sand")])).count() == 0


def test_sale_filter_matches_the_card_badge():
    """«Nur reduzierte» обязан совпадать с тем, что показывает карточка: обе
    стороны читают price_layer, поэтому фильтр не может обещать скидку, которой
    на витрине нет."""
    from apps.promotions.models import Promotion

    reduced, plain = _product("Reduziert", "50.00"), _product("Normal", "50.00")
    Promotion.objects.create(
        title={"de": "Aktion"},
        product=reduced,
        discount_percent=20,
        compare_at_price=Decimal("50.00"),
        status="active",
    )
    found = CatalogFacets().apply(_all(), {"sale": "1"})
    assert list(found) == [reduced]
    assert CatalogFacets().present(_all(), {})["sale_count"] == 1
    assert plain not in found


def test_diet_chips_are_scoped_to_the_given_set():
    """Раньше чипы считались по ВСЕМУ каталогу — страница категории предлагала
    диету, дающую ноль товаров."""
    _product("Vegan hier", diets=["vegan"])
    other = _product("Vegetarisch anderswo", diets=["vegetarisch"])
    chips = CatalogFacets().present(_all().exclude(pk=other.pk), {})["diet_chips"]
    assert [c["code"] for c in chips] == ["vegan"]
    assert chips[0]["count"] == 1


def test_plain_dict_params_still_work():
    """Вьюха страницы категории собирает параметры сама — без `getlist`."""
    prod = _product("Shirt")
    ProductVariant.objects.create(product=prod, label="", size="M", color="Sand")
    assert list(CatalogFacets().apply(_all(), {"farbe": "Sand"})) == [prod]
    assert CatalogFacets().selected({"groesse": "M"})["groesse"] == ["M"]


def test_repeated_value_is_deduped():
    assert CatalogFacets().selected(_qd([("farbe", "Sand"), ("farbe", "Sand")]))["farbe"] == [
        "Sand"
    ]
