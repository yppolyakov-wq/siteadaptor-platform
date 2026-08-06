"""I18N-10: переводы параметров товара (варианты / модификаторы / характеристики).

Замки писались ДО правок модели (характеризация): без переводов рендер и учёт
обязаны остаться прежними. Ключевой инвариант — ПЕРЕВОДИТСЯ ТОЛЬКО ЖИВОЙ ПОКАЗ:
снимки в заказе (`OrderItem.variant_label`, `modifiers`) и ключи учёта (склад,
CSV-импорт, оси фасета) остаются на базовом языке.
"""

import pytest
from django.utils import translation

from apps.catalog.models import ModifierGroup, ModifierOption, Product, ProductVariant

pytestmark = pytest.mark.django_db


def _product(name="Wollmantel"):
    return Product.objects.create(name={"de": name}, base_price="129.00", is_active=True)


def _detail_html(product) -> str:
    """Рендер витринной детали товара (вьюха живёт в promotions.public_views)."""
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.promotions import public_views
    from apps.tenants.tests.factories import TenantFactory

    request = RequestFactory().get(f"/sortiment/{product.pk}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(name="Laden", address="Feldweg 1")
    return public_views.product_detail(request, pk=product.pk).content.decode()


# --- характеризация: без переводов ничего не меняется -------------------------


def test_variant_without_overlay_renders_flat_label():
    v = ProductVariant.objects.create(product=_product(), label="groß 32cm")
    with translation.override("ru"):
        assert v.label_localized == "groß 32cm"
        assert v.size_localized == ""
        assert v.color_localized == ""


def test_modifier_without_overlay_renders_flat():
    p = _product("Pizza")
    g = ModifierGroup.objects.create(product=p, name="Teig")
    o = ModifierOption.objects.create(group=g, label="Dünn", price_delta="0.00")
    with translation.override("en"):
        assert g.name_localized == "Teig"
        assert o.label_localized == "Dünn"


# --- перевод показывается на локали, база — на немецком -----------------------


def test_variant_overlay_translates_display_only():
    v = ProductVariant.objects.create(
        product=_product(),
        label="Klein",
        size="S",
        color="Weiß",
        label_i18n={"ru": "Маленький"},
        size_i18n={"ru": "S"},
        color_i18n={"ru": "Белый"},
    )
    with translation.override("ru"):
        assert v.label_localized == "Маленький"
        assert v.color_localized == "Белый"
    with translation.override("de"):
        assert v.label_localized == "Klein"  # база — источник правды
        assert v.color_localized == "Weiß"
    # Плоские поля не тронуты: на них держатся склад, импорт и оси фасета.
    v.refresh_from_db()
    assert (v.label, v.size, v.color) == ("Klein", "S", "Weiß")


def test_modifier_overlay_translates_display_only():
    p = _product("Pizza")
    g = ModifierGroup.objects.create(
        product=p, name="Beläge hinzufügen", name_i18n={"ru": "Добавки"}
    )
    o = ModifierOption.objects.create(
        group=g, label="Pilze", price_delta="1.00", label_i18n={"ru": "Грибы"}
    )
    with translation.override("ru"):
        assert g.name_localized == "Добавки"
        assert o.label_localized == "Грибы"
    g.refresh_from_db()
    o.refresh_from_db()
    assert g.name == "Beläge hinzufügen" and o.label == "Pilze"


def test_product_material_and_care_localized():
    p = Product.objects.create(
        name={"de": "Seidentuch"},
        base_price="59.00",
        material="100 % Seide",
        care="Handwäsche kalt",
        material_i18n={"ru": "100 % шёлк"},
        care_i18n={"ru": "Ручная стирка в холодной воде"},
    )
    with translation.override("ru"):
        assert p.material_localized() == "100 % шёлк"
        assert p.care_localized() == "Ручная стирка в холодной воде"
    with translation.override("de"):
        assert p.material_localized() == "100 % Seide"


# --- инвариант: снимки заказа и ключи учёта НЕ переводятся --------------------


def test_order_snapshot_keeps_base_language():
    """Что заказано — то и зафиксировано: позиция заказа несёт плоскую метку."""
    from apps.crm.models import Customer
    from apps.orders.models import Order, OrderItem

    p = _product("Pizza Margherita")
    v = ProductVariant.objects.create(
        product=p, label="groß 32cm", price="12.50", label_i18n={"ru": "большая 32см"}
    )
    customer = Customer.objects.create(name="Test", email="t@test.de")
    order = Order.objects.create(customer=customer, reference_code="O-TEST01")
    item = OrderItem.objects.create(
        order=order,
        product=p,
        variant=v,
        title_snapshot="Pizza Margherita",
        variant_label=v.label,  # снимок — плоское поле, не *_localized
        unit_price="12.50",
        qty=1,
        modifiers=[{"label": "Pilze", "delta": "1.00"}],
    )
    with translation.override("ru"):
        item.refresh_from_db()
        assert item.variant_label == "groß 32cm"
        assert item.modifiers[0]["label"] == "Pilze"


def test_facet_axis_uses_flat_fields():
    """Оси фасета Größe/Farbe строятся на ПЛОСКИХ полях — перевод не плодит
    вторых значений и не рвёт ссылку ?groesse=."""
    p = _product("Kleid")
    ProductVariant.objects.create(
        product=p, label="S · Blau", size="S", color="Blau", color_i18n={"ru": "Синий"}
    )
    ProductVariant.objects.create(product=p, label="M · Blau", size="M", color="Blau")
    with translation.override("ru"):
        colors = set(p.variants.values_list("color", flat=True))
    assert colors == {"Blau"}


# --- витрина показывает перевод, форма отправляет плоские ключи ---------------


def test_storefront_detail_shows_translated_variant_and_modifier():
    """P2: на локали посетителя пикер варианта и группа модификаторов —
    переведённые; значения формы (pk) не меняются."""
    p = Product.objects.create(
        name={"de": "Pizza", "ru": "Пицца"}, base_price="9.50", is_active=True
    )
    ProductVariant.objects.create(
        product=p, label="groß 32cm", price="12.50", label_i18n={"ru": "большая 32 см"}
    )
    g = ModifierGroup.objects.create(product=p, name="Teig", name_i18n={"ru": "Тесто"})
    ModifierOption.objects.create(
        group=g, label="Dünn", price_delta="0.00", label_i18n={"ru": "Тонкое"}
    )

    with translation.override("ru"):
        body = _detail_html(p)
    assert "большая 32 см" in body
    assert "Тесто" in body and "Тонкое" in body
    assert "groß 32cm" not in body  # немецкая метка не осталась в показе


def test_storefront_detail_without_translations_is_unchanged():
    """Характеризация: без переводов витрина рендерит ровно прежние метки."""
    p = Product.objects.create(name={"de": "Pizza"}, base_price="9.50", is_active=True)
    ProductVariant.objects.create(product=p, label="groß 32cm", price="12.50")
    g = ModifierGroup.objects.create(product=p, name="Teig")
    ModifierOption.objects.create(group=g, label="Dünn", price_delta="0.00")

    with translation.override("ru"):
        body = _detail_html(p)
    assert "groß 32cm" in body and "Teig" in body and "Dünn" in body


def test_size_table_translated_for_visitor():
    from apps.catalog.models import Category

    cat = Category.objects.create(
        name={"de": "Kleider"},
        slug="kleider",
        size_table="Größe | Brust\nS | 86–90",
        size_table_i18n={"ru": "Размер | Грудь\nS | 86–90"},
    )
    with translation.override("ru"):
        assert cat.size_table_rows[0] == ["Размер", "Грудь"]
    with translation.override("de"):
        assert cat.size_table_rows[0] == ["Größe", "Brust"]
