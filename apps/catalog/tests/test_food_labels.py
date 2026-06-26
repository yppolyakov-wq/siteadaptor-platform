"""R4: Lebensmittel-Kennzeichnung (LMIV) — аллергены/Herkunft/Zutaten на товаре."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import food
from apps.catalog.forms import ProductForm
from apps.catalog.tests.factories import ProductFactory
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


# --- food-хелпер ----------------------------------------------------------


def test_allergen_labels_maps_codes_in_order():
    # порядок — как в ALLERGENS, не как во входе; неизвестный код отброшен
    labels = food.allergen_labels(["milch", "gluten", "unknown"])
    assert labels == ["Glutenhaltiges Getreide", "Milch (Laktose)"]


def test_allergen_labels_empty():
    assert food.allergen_labels([]) == []
    assert food.allergen_labels(None) == []


def test_all_14_eu_allergens_present():
    assert len(food.ALLERGENS) == 14


# --- модель ---------------------------------------------------------------


def test_product_allergen_labels_property():
    p = ProductFactory(allergens=["gluten", "sesam"])
    assert p.allergen_labels == ["Glutenhaltiges Getreide", "Sesam"]


# --- форма ----------------------------------------------------------------


def _form_data(**over):
    data = {
        "name_de": "Roggenbrot",
        "base_price": "4.20",
        "currency": "EUR",
        "allergens": ["gluten", "sesam"],
        "origin": "Deutschland",
        "ingredients": "Roggenmehl, Wasser, Salz, Hefe",
    }
    data.update(over)
    return data


def test_form_saves_lmiv_fields():
    form = ProductForm(_form_data())
    assert form.is_valid(), form.errors
    product = form.save()
    product.refresh_from_db()
    assert product.allergens == ["gluten", "sesam"]
    assert product.origin == "Deutschland"
    assert "Roggenmehl" in product.ingredients


def test_form_rejects_unknown_allergen():
    form = ProductForm(_form_data(allergens=["gluten", "kryptonit"]))
    assert not form.is_valid()
    assert "allergens" in form.errors


def test_form_allergens_optional():
    form = ProductForm(_form_data(allergens=[]))
    assert form.is_valid(), form.errors
    product = form.save()
    assert product.allergens == []


def test_form_edit_prefills_allergens():
    p = ProductFactory(allergens=["milch"])
    form = ProductForm(instance=p)
    assert form.fields["allergens"].initial == ["milch"]


# --- витрина --------------------------------------------------------------


def _req(path, tenant=None):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant or TenantFactory.build(name="Bäckerei X", address="Hauptstr. 1")
    return request


def test_storefront_shows_lmiv_block_when_present():
    p = ProductFactory(allergens=["gluten"], origin="Türkei", ingredients="Weizenmehl, Wasser")
    body = public_views.product_detail(_req(f"/sortiment/{p.pk}/"), pk=p.pk).content.decode()
    assert "Glutenhaltiges Getreide" in body
    assert "Türkei" in body
    assert "Weizenmehl, Wasser" in body


def test_storefront_hides_lmiv_block_when_empty():
    p = ProductFactory()  # без маркировки
    body = public_views.product_detail(_req(f"/sortiment/{p.pk}/"), pk=p.pk).content.decode()
    assert "Allergens" not in body
    assert "Glutenhaltiges Getreide" not in body


def test_storefront_card_shows_allergens_inline():
    """A4: карточка меню показывает аллергены строкой (LMIV), если они заданы."""
    ProductFactory(allergens=["gluten", "milch"], is_active=True)
    body = public_views.product_list(_req("/sortiment/")).content.decode()
    assert "Glutenhaltiges Getreide" in body and "Milch (Laktose)" in body


def test_storefront_card_no_allergen_line_when_empty():
    """Регрессия A4: без аллергенов строка не появляется (retail-товары не зашумлены)."""
    ProductFactory(is_active=True)
    body = public_views.product_list(_req("/sortiment/")).content.decode()
    assert "Glutenhaltiges Getreide" not in body


# --- A4: диет-теги (vegan/vegetarisch/…) ------------------------------------


def test_diet_badges_maps_codes_with_icons():
    from apps.catalog import food

    badges = food.diet_badges(["vegan", "unknown", "glutenfrei"])
    assert [b["code"] for b in badges] == ["vegan", "glutenfrei"]  # порядок DIETS, мусор отброшен
    assert badges[0]["icon"] and badges[0]["label"] == "Vegan"


def test_product_diet_badges_property():
    p = ProductFactory(diets=["vegetarisch"])
    assert p.diet_badges[0]["code"] == "vegetarisch"


def test_card_shows_diet_icons():
    """A4: карточка меню показывает диет-иконки при наличии тегов."""
    ProductFactory(diets=["vegan"], is_active=True)
    body = public_views.product_list(_req("/sortiment/")).content.decode()
    assert "🌱" in body  # иконка vegan


def test_product_list_diet_filter():
    """A4: ?diet=vegan фильтрует товары; чип активен."""
    veg = ProductFactory(diets=["vegan"], is_active=True)
    meat = ProductFactory(diets=[], is_active=True)
    body = public_views.product_list(_req("/sortiment/?diet=vegan")).content.decode()
    assert str(veg.pk) in body  # веган-товар показан
    assert str(meat.pk) not in body  # не-веган отфильтрован
    assert "bg-emerald-600" in body  # активный диет-чип


def test_product_list_invalid_diet_ignored():
    """Регрессия A4: невалидная диета игнорируется (без 500/пустоты)."""
    p = ProductFactory(diets=["vegan"], is_active=True)
    body = public_views.product_list(_req("/sortiment/?diet=bogus")).content.decode()
    assert str(p.pk) in body  # фильтр не применён
