"""FB-24b/c: экран «Optionen», оси товара и генератор вариантов по N осям."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import options, options_views, views
from apps.catalog.models import OptionType, OptionValue, Product, VariantOption

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="post", data=None):
    request = getattr(RequestFactory(), method)("/x/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"u-{uuid.uuid4().hex[:8]}", password="pw1234567"
    )
    return request


def _product():
    return Product.objects.create(name={"de": "Shirt"}, base_price=Decimal("19.90"))


def test_screen_lists_all_standard_types():
    body = options_views.option_list(_req("get")).content.decode()
    for label in (
        "Größe",
        "Farbe",
        "Material",
        "Volumen",
        "Gewicht",
        "Geschmack",
        "Länge",
        "Stückzahl",
    ):
        assert label in body


def test_enable_standard_is_idempotent_and_hide_keeps_row():
    options_views.option_list(_req(data={"action": "standard", "code": "material", "on": "1"}))
    options_views.option_list(_req(data={"action": "standard", "code": "material", "on": "1"}))
    assert OptionType.objects.filter(code="material").count() == 1
    options_views.option_list(_req(data={"action": "standard", "code": "material", "on": "0"}))
    assert OptionType.objects.get(code="material").is_active is False
    # чужой код стандартом не становится
    options_views.option_list(_req(data={"action": "standard", "code": "evil", "on": "1"}))
    assert not OptionType.objects.filter(code="evil").exists()


def test_custom_type_never_takes_a_standard_code():
    t = options.add_custom("Material")
    assert t.code != "material" and t.standard == ""
    assert options.add_custom("   ") is None


def test_values_dedup_case_insensitive_and_delete_only_unused():
    t = options.add_custom("Füllung")
    options_views.option_list(
        _req(
            data={
                "action": "save",
                "type": t.pk,
                "is_active": "on",
                "new_values": "Vanille, vanille, Schoko",
            }
        )
    )
    assert list(t.values.values_list("value", flat=True)) == ["Vanille", "Schoko"]
    p = _product()
    variant = p.variants.create(label="A")
    options.set_variant_option(variant, t, "Vanille")
    used = t.values.get(value="Vanille")
    options_views.option_list(_req(data={"action": "delete_value", "type": t.pk, "value": used.pk}))
    assert OptionValue.objects.filter(pk=used.pk).exists(), "используемое значение не удаляется"
    options_views.option_list(_req(data={"action": "delete", "type": t.pk}))
    assert OptionType.objects.filter(pk=t.pk).exists(), "используемый тип не удаляется"


def test_product_axes_default_and_cap():
    p = _product()
    assert options.product_axes(p) == ["size", "color"]
    options.enable_standard("material")
    t = options.add_custom("Füllung")
    options_views.product_axes(_req(data={"axes": ["material", t.code, "size", "color"]}), pk=p.pk)
    p.refresh_from_db()
    assert p.option_axes == ["material", t.code, "size"]


def test_generator_builds_three_axes_and_links_values():
    p = _product()
    options.enable_standard("material")
    options.set_product_axes(p, ["size", "color", "material"])
    views.variant_generate(
        _req(data={"sizes": "S, M", "colors": "Blau", "axis_material": "Baumwolle, Leinen"}),
        pk=p.pk,
    )
    labels = set(p.variants.values_list("label", flat=True))
    assert labels == {
        "S · Blau · Baumwolle", "S · Blau · Leinen", "M · Blau · Baumwolle", "M · Blau · Leinen",
    }  # fmt: skip
    assert VariantOption.objects.filter(variant__product=p).count() == 4
    # повтор не плодит дублей
    views.variant_generate(
        _req(data={"sizes": "S, M", "colors": "Blau", "axis_material": "Baumwolle, Leinen"}),
        pk=p.pk,
    )
    assert p.variants.count() == 4


def test_generator_default_axes_unchanged():
    p = _product()
    views.variant_generate(_req(data={"sizes": "S", "colors": "Rot"}), pk=p.pk)
    assert list(p.variants.values_list("label", flat=True)) == ["S · Rot"]
