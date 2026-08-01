"""Виды отображения вариантов и опций (O-2, план option-display-styles-2026-08-01).

Решение владельца: вид выбирает ВЛАДЕЛЕЦ из реестра. Ключевые инварианты:
пустой вид = прежняя разметка, набор полей формы корзины не меняется ни при
каком виде (его пинит test_buybox_parity), свотчи только выставляют значение
существующего селекта.
"""

import re

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import option_styles
from apps.catalog.models import ModifierGroup, ModifierOption, ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _detail(product, tenant=None):
    request = RequestFactory().get(f"/sortiment/{product.pk}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant or TenantFactory.build()
    return public_views.product_detail(request, pk=product.pk).content.decode()


def _cart_form(body):
    start = body.index('action="/warenkorb/add/"')
    start = body.rindex("<form", 0, start)
    return body[start : body.index("</form>", start)]


def _with_variants(style="", colors=("Blau", "Rot"), sizes=("S", "M")):
    product = ProductFactory(variant_style=style)
    for c in colors:
        for s in sizes:
            ProductVariant.objects.create(
                product=product, label=f"{s} · {c}", size=s, color=c, price="19.90"
            )
    return product


# --- реестр ----------------------------------------------------------------


def test_color_hex_only_from_explicit_dictionary():
    """Угадывание цвета по строке недопустимо: «Sonnengelb» стало бы чёрным."""
    assert option_styles.color_hex("Blau")
    assert option_styles.color_hex("blau") == option_styles.color_hex("Blau")
    assert option_styles.color_hex("Sonnengelb") == ""
    assert option_styles.color_hex("") == ""


def test_variant_style_falls_back_to_site_default_then_empty():
    product = ProductFactory(variant_style="")
    assert option_styles.variant_style(product, "photo") == "photo"
    assert option_styles.variant_style(product, "") == ""
    assert option_styles.variant_style(product, "мусор") == ""
    product.variant_style = "buttons"
    assert option_styles.variant_style(product, "photo") == "buttons"  # товар сильнее
    product.variant_style = "мусор"
    assert option_styles.variant_style(product, "") == ""  # не 500


def test_site_default_keys_match_catalog_registry():
    """Один источник правды: normalize и витрина принимают одни и те же виды."""
    from apps.tenants import siteconfig

    assert set(siteconfig._VARIANT_STYLE_KEYS) == {k for k in option_styles.VARIANT_STYLE_KEYS if k}


# --- витрина ---------------------------------------------------------------


def test_empty_style_keeps_plain_select_and_no_swatches():
    body = _detail(_with_variants(""))
    form = _cart_form(body)
    assert 'name="variant"' in form
    assert "data-pick-ui" not in form  # разметки выбора нет вовсе


@pytest.mark.parametrize("style", ["buttons", "color", "photo", "list", "axes"])
def test_every_style_keeps_the_exact_form_fields(style):
    """Свотчи не вводят новых имён полей — иначе поедет приём корзины."""
    form = _cart_form(_detail(_with_variants(style)))
    assert set(re.findall(r'name="([^"]+)"', form)) == {
        "csrfmiddlewaretoken",
        "product",
        "variant",
        "qty",
    }
    assert "data-pick-ui" in form
    assert "data-pick-select" in form


def test_swatches_render_before_the_select():
    """CSS прячет селект соседним правилом — порядок обязателен."""
    form = _cart_form(_detail(_with_variants("buttons")))
    assert form.index("data-pick-ui") < form.index('name="variant"')


def test_axes_style_renders_two_rows_without_duplicating_colors():
    form = _cart_form(_detail(_with_variants("axes")))
    assert 'data-pick-axis="color"' in form and 'data-pick-axis="size"' in form
    assert form.count('data-pick-value="Blau"') == 1  # цвет один раз, не на каждый размер
    assert form.count('data-pick-value="S"') == 1


def test_axes_style_degrades_to_buttons_without_both_axes():
    """Одна ось → «две оси» выродились бы в один ряд и запутали бы гостя."""
    form = _cart_form(_detail(_with_variants("axes", colors=("",), sizes=("S", "M"))))
    assert "data-pick-axis" not in form
    assert "data-pick-ui" in form


def test_site_default_applies_when_product_has_no_own_style():
    tenant = TenantFactory.build(site_config={"site_defaults": {"variant_style": "photo"}})
    form = _cart_form(_detail(_with_variants(""), tenant=tenant))
    assert "data-pick-cols" in form  # фото-плитки — грид


# --- модификаторы ----------------------------------------------------------


def _with_modifier(style, *, multi, image=None):
    product = ProductFactory()
    group = ModifierGroup.objects.create(
        product=product,
        name="Beilage",
        min_select=0,
        max_select=0 if multi else 1,
        display_style=style,
    )
    ModifierOption.objects.create(
        group=group, label="Pommes", price_delta="2.50", image=image or {}
    )
    return product


def test_modifier_multi_tiles_are_plain_checkboxes():
    """Множественный выбор не требует JS: чекбокс сам и есть поле."""
    form = _cart_form(_detail(_with_modifier("tiles", multi=True)))
    assert 'type="checkbox" name="mod"' in form
    assert "data-pick-ui" not in form


def test_modifier_single_keeps_select_in_dom():
    """Радиокнопки с общим именем `mod` слиплись бы в ОДНУ группу на весь товар —
    поэтому одиночный выбор остаётся селектом, а плитки им управляют."""
    form = _cart_form(_detail(_with_modifier("tiles", multi=False)))
    assert 'name="mod"' in form and "<select" in form
    assert "data-pick-ui" in form and "data-pick-select" in form


def test_modifier_option_photo_is_rendered():
    product = _with_modifier("tiles", multi=True, image={"url": "/media/x.jpg"})
    assert "/media/x.jpg" in _cart_form(_detail(product))


def test_modifier_empty_style_matches_previous_markup():
    form = _cart_form(_detail(_with_modifier("", multi=True)))
    assert 'type="checkbox" name="mod"' in form
    assert "data-pick" not in form
