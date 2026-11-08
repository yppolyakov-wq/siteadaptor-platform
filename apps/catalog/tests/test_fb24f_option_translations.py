"""FB-24f: переводы значений опций и подписи своего типа на экране «Optionen».

База (немецкий ключ) не меняется — склад/заказы/фильтр держатся за неё; переводится показ:
фильтр каталога, пилюля активного фильтра, подпись варианта на витрине."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import translation

from apps.catalog import options, options_views
from apps.catalog.models import OptionValue, Product, ProductVariant
from apps.tenants.tests.factories import TenantFactory

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
    request.tenant = TenantFactory.build(
        enabled_locales=["de", "en", "ru"], default_locale="de", disabled_modules=[]
    )
    return request


def _material():
    t = options.enable_standard("material")
    options.add_values(t, "Leinen, Baumwolle")
    return t


def test_screen_renders_translation_inputs_per_value_and_language():
    t = _material()
    leinen = OptionValue.objects.get(option_type=t, value="Leinen")
    body = options_views.option_list(_req("get")).content.decode()
    assert f'name="val_{leinen.pk}_en"' in body and f'name="val_{leinen.pk}_ru"' in body
    assert 'data-i18n-base="Leinen"' in body  # «🌐 Übersetzen» знает базовый текст
    assert "data-i18n-select" in body  # переключатель языка ввода


def test_save_writes_overlay_keeps_base_and_empty_clears():
    t = _material()
    leinen = OptionValue.objects.get(option_type=t, value="Leinen")
    options_views.option_list(
        _req(
            data={
                "action": "save",
                "type": t.pk,
                "is_active": "on",
                f"val_{leinen.pk}_en": "Linen",
                f"val_{leinen.pk}_ru": "Лён",
            }
        )
    )
    leinen.refresh_from_db()
    assert leinen.value == "Leinen" and leinen.value_i18n == {"en": "Linen", "ru": "Лён"}
    options_views.option_list(
        _req(data={"action": "save", "type": t.pk, "is_active": "on", f"val_{leinen.pk}_en": ""})
    )
    leinen.refresh_from_db()
    assert leinen.value_i18n == {"ru": "Лён"}  # пустое снимает, отсутствующее не трогает


def test_custom_type_name_translation():
    t = options.add_custom("Füllung")
    options_views.option_list(
        _req(data={"action": "save", "type": t.pk, "name": "Füllung", "name_en": "Filling"})
    )
    t.refresh_from_db()
    assert t.name == "Füllung" and t.name_i18n == {"en": "Filling"}


def test_variant_label_keeps_custom_axis_in_translation():
    """Был дефект: на не-базовом языке подпись «S · Blau · Leinen» теряла свою ось."""
    t = _material()
    leinen = OptionValue.objects.get(option_type=t, value="Leinen")
    leinen.value_i18n = {"en": "Linen"}
    leinen.save()
    product = Product.objects.create(
        name={"de": "Kissen"}, base_price=Decimal("19.90"), option_axes=["color", "material"]
    )
    v = ProductVariant.objects.create(
        product=product, color="Blau", color_i18n={"en": "Blue"}, label="Blau · Leinen"
    )
    options.set_variant_option(v, t, "Leinen")
    v = ProductVariant.objects.get(pk=v.pk)
    with translation.override("en"):
        assert v.label_localized == "Blue · Linen"
    with translation.override("de"):
        assert v.label_localized == "Blau · Leinen"


def test_facet_chips_carry_translated_label():
    from apps.catalog.facets import CatalogFacets

    t = _material()
    for value in ("Leinen", "Baumwolle"):
        ov = OptionValue.objects.get(option_type=t, value=value)
        ov.value_i18n = {"en": {"Leinen": "Linen", "Baumwolle": "Cotton"}[value]}
        ov.save()
        p = Product.objects.create(name={"de": value}, base_price=Decimal("9"))
        variant = ProductVariant.objects.create(product=p, label=value)
        options.set_variant_option(variant, t, value)
    with translation.override("en"):
        chips = CatalogFacets._option_chips(Product.objects.all())
    labels = {v["value"]: v["label"] for v in chips[0]["values"]}
    assert labels == {"Leinen": "Linen", "Baumwolle": "Cotton"}
