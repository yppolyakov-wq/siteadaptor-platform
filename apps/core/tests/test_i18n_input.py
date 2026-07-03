"""L3d: per-locale ввод — helper i18n_input + CRUD-вьюхи Service/StayUnit/Combo."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core.i18n_input import apply_i18n_overlay, extra_locales, i18n_inputs_for
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(locales):
    return TenantFactory.build(enabled_locales=locales, default_locale=locales[0])


# --- helper -----------------------------------------------------------------


def test_extra_locales_excludes_base_and_single_locale_is_empty():
    assert extra_locales(_tenant(["de"])) == []
    assert extra_locales(_tenant(["de", "en"])) == ["en"]
    assert extra_locales(None) == []  # fail-safe без тенанта


def test_apply_overlay_writes_updates_and_deletes():
    from apps.booking.models import Service

    tenant = _tenant(["de", "en"])
    svc = Service(name="Haarschnitt", name_i18n={"en": "Old"}, description_i18n={})
    changed = apply_i18n_overlay(svc, {"name_en": " Haircut "}, tenant)
    assert changed == ["name_i18n"]
    assert svc.name_i18n == {"en": "Haircut"}
    # пустое значение удаляет ключ (фолбэк на базу)
    apply_i18n_overlay(svc, {"name_en": ""}, tenant)
    assert svc.name_i18n == {}


def test_apply_overlay_presence_guard_and_never_base_locale():
    from apps.booking.models import Service

    tenant = _tenant(["de", "en"])
    svc = Service(name="Haarschnitt", name_i18n={"en": "Haircut"})
    # поле не прислано → не трогаем (старые формы-клиенты)
    assert apply_i18n_overlay(svc, {}, tenant) == []
    assert svc.name_i18n == {"en": "Haircut"}
    # базовая локаль (de) в оверлей не пишется даже при попытке
    apply_i18n_overlay(svc, {"name_de": "Хак"}, tenant)
    assert "de" not in (svc.name_i18n or {})


def test_i18n_inputs_for_renders_values():
    from apps.booking.models import Service

    tenant = _tenant(["de", "en"])
    svc = Service(name="X", name_i18n={"en": "Haircut"}, description_i18n={})
    rows = i18n_inputs_for(svc, tenant)
    by_name = {r["input_name"]: r["value"] for r in rows}
    assert by_name == {"name_en": "Haircut", "description_en": ""}


# --- вьюхи (паритет 1 локали + оверлеи при N>1) -------------------------------


def _req(method="get", data=None, locales=("de",)):
    request = getattr(RequestFactory(), method)("/x/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    uname = f"o-{uuid.uuid4().hex[:8]}"
    request.user = get_user_model().objects.create_user(
        username=uname, email=f"{uname}@t.de", password="pw12345678"
    )
    request.tenant = _tenant(list(locales))
    return request


def test_service_create_with_overlay_and_single_locale_parity():
    from apps.booking.models import Service
    from apps.booking.views import services_view

    # N>1: оверлей пишется
    services_view(
        _req(
            "post",
            {
                "action": "create",
                "name": "Haarschnitt",
                "description": "Basis",
                "name_en": "Haircut",
                "description_en": "Base cut",
                "duration": "30",
            },
            locales=("de", "en"),
        )
    )
    svc = Service.objects.get(name="Haarschnitt")
    assert svc.name_i18n == {"en": "Haircut"}
    assert svc.description_i18n == {"en": "Base cut"}

    # 1 локаль: как раньше — никаких оверлеев
    services_view(_req("post", {"action": "create", "name": "Föhnen", "duration": "20"}))
    svc2 = Service.objects.get(name="Föhnen")
    assert svc2.name_i18n == {} and svc2.description_i18n == {}


def test_service_update_writes_overlay_and_optional_name():
    from apps.booking.models import Service
    from apps.booking.views import services_view

    svc = Service.objects.create(name="Alt", duration_minutes=30, price_cents=1000)
    services_view(
        _req(
            "post",
            {
                "action": "update",
                "service": str(svc.pk),
                "name": "Neu",
                "description": "D",
                "name_en": "New",
                "duration": "45",
                "price_eur": "12",
            },
            locales=("de", "en"),
        )
    )
    svc.refresh_from_db()
    assert svc.name == "Neu" and svc.name_i18n == {"en": "New"}

    # старый клиент формы БЕЗ поля name → имя не трогаем (presence-guard)
    services_view(
        _req(
            "post",
            {
                "action": "update",
                "service": str(svc.pk),
                "description": "D2",
                "duration": "45",
                "price_eur": "12",
            },
        )
    )
    svc.refresh_from_db()
    assert svc.name == "Neu"


def test_stayunit_create_and_update_overlay():
    from apps.stays.models import StayUnit
    from apps.stays.views import units

    units(
        _req(
            "post",
            {
                "action": "unit",
                "name": "Doppelzimmer",
                "description": "Mit Balkon",
                "name_en": "Double room",
                "price_eur": "80",
            },
            locales=("de", "en"),
        )
    )
    unit = StayUnit.objects.get(name="Doppelzimmer")
    assert unit.name_i18n == {"en": "Double room"}

    units(
        _req(
            "post",
            {
                "action": "unit_settings",
                "unit": str(unit.pk),
                "name": "Doppelzimmer Süd",
                "description": "Mit Balkon",
                "description_en": "With balcony",
                "price_eur": "85",
            },
            locales=("de", "en"),
        )
    )
    unit.refresh_from_db()
    assert unit.name == "Doppelzimmer Süd"
    assert unit.description_i18n == {"en": "With balcony"}


def test_combo_create_and_edit_overlay():
    from apps.catalog.models import Combo
    from apps.catalog.views import combo_create, combo_edit

    combo_create(
        _req(
            "post",
            {"name": "Frühstück", "price": "9.90", "name_en": "Breakfast", "is_active": "1"},
            locales=("de", "en"),
        )
    )
    combo = Combo.objects.get(name="Frühstück")
    assert combo.name_i18n == {"en": "Breakfast"}

    combo_edit(
        _req(
            "post",
            {"name": "Frühstück", "price": "9.90", "description_en": "Coffee + roll"},
            locales=("de", "en"),
        ),
        combo.pk,
    )
    combo.refresh_from_db()
    assert combo.description_i18n == {"en": "Coffee + roll"}


# --- L3d.5: динамика ModelForm (Category/Product/Promotion) -------------------


def test_category_form_de_only_tenant_hides_en_field():
    from apps.catalog.forms import CategoryForm

    form = CategoryForm(tenant=_tenant(["de"]))
    assert "name_de" in form.fields and "name_en" not in form.fields


def test_category_form_without_tenant_keeps_registry_parity():
    from apps.catalog.forms import CategoryForm

    form = CategoryForm()  # без тенанта → весь реестр (de+en) — как раньше
    assert "name_en" in form.fields and "description_en" in form.fields


def test_product_form_third_locale_appears_and_saves(settings):
    settings.LANGUAGES = [("de", "Deutsch"), ("en", "English"), ("fr", "Français")]
    from apps.catalog.forms import ProductForm

    tenant = _tenant(["de", "fr"])
    form = ProductForm(
        {
            "name_de": "Brot",
            "name_fr": "Pain",
            "description_de": "",
            "description_fr": "",
            "base_price": "3.50",
            "currency": "EUR",
            "unit": "",
        },
        tenant=tenant,
    )
    assert "name_fr" in form.fields and "name_en" not in form.fields
    assert form.is_valid(), form.errors
    product = form.save()
    assert product.name == {"de": "Brot", "fr": "Pain"}


def test_promotion_form_dynamic_initial_from_instance():
    from apps.promotions.forms import PromotionForm
    from apps.promotions.models import Promotion

    promo = Promotion.objects.create(title={"de": "Aktion", "en": "Deal"}, status="draft")
    form = PromotionForm(instance=promo, tenant=_tenant(["de", "en"]))
    assert form.fields["title_en"].initial == "Deal"
