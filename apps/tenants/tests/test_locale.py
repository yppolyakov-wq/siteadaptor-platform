"""Волна L / L1 — рантайм-биндинг локалей (N-locale, генерик).

Проверяем, что `Tenant.enabled_locales`/`default_locale` действительно читаются в
рантайме (резолвер `active_locales`), переключатель/`set_language` валидируют против
включённых локалей тенанта, а оверлей витрины (`siteconfig`) — генерик по реестру
`settings.LANGUAGES`, а не захардкоженный EN. Языки добавляются как ДАННЫЕ
(`settings.LANGUAGES`), без правки кода.
"""

import pytest
from django.test import RequestFactory

from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

# Реестр из 3 языков — для проверки генерик-поведения (не хардкод DE/EN).
LANGUAGES_3 = [("de", "Deutsch"), ("en", "English"), ("fr", "Français")]


# --- L1: резолвер active_locales ------------------------------------------


def test_active_locales_returns_enabled_intersect_registry():
    t = TenantFactory.build(enabled_locales=["de", "en"], default_locale="de")
    assert t.active_locales == ["de", "en"]


def test_active_locales_generic_third_language(settings):
    """Третья локаль работает без правок кода — только `settings.LANGUAGES`."""
    settings.LANGUAGES = LANGUAGES_3
    t = TenantFactory.build(enabled_locales=["de", "fr"], default_locale="de")
    assert t.active_locales == ["de", "fr"]  # EN не показывается, FR — да


def test_active_locales_drops_unknown_locale(settings):
    """Локаль не из реестра (`settings.LANGUAGES`) отбрасывается."""
    settings.LANGUAGES = LANGUAGES_3
    t = TenantFactory.build(enabled_locales=["de", "zz", "fr"], default_locale="de")
    assert t.active_locales == ["de", "fr"]  # zz нет в реестре → выброшена


def test_active_locales_empty_falls_back_to_default():
    """Пустой enabled_locales → [default_locale] (легаси-тенант, без регресса)."""
    t = TenantFactory.build(enabled_locales=[], default_locale="de")
    assert t.active_locales == ["de"]


def test_active_locales_dedupes_preserving_order():
    t = TenantFactory.build(enabled_locales=["en", "de", "en"], default_locale="de")
    assert t.active_locales == ["en", "de"]


def test_active_locales_ignores_non_string_entries(settings):
    settings.LANGUAGES = LANGUAGES_3
    t = TenantFactory.build(enabled_locales=["de", 5, None, "fr"], default_locale="de")
    assert t.active_locales == ["de", "fr"]


# --- L1: set_language валидирует против active_locales тенанта -------------


@pytest.fixture()
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _set_lang(tenant, lang):
    req = RequestFactory().get("/lang/", {"lang": lang})
    if tenant is not None:
        req.tenant = tenant
    return public_views.set_language(req)


def test_set_language_accepts_enabled_locale(_tenant_urlconf):
    t = TenantFactory.build(enabled_locales=["de", "en"], default_locale="de")
    resp = _set_lang(t, "en")
    assert resp.cookies["django_language"].value == "en"


def test_set_language_rejects_disabled_locale_uses_default(_tenant_urlconf, settings):
    """Локаль, которую тенант НЕ открыл, → default_locale (не переключает)."""
    settings.LANGUAGES = LANGUAGES_3
    t = TenantFactory.build(enabled_locales=["de", "fr"], default_locale="de")
    resp = _set_lang(t, "en")  # EN есть в реестре, но не включён у тенанта
    assert resp.cookies["django_language"].value == "de"


def test_set_language_unknown_locale_uses_default(_tenant_urlconf):
    t = TenantFactory.build(enabled_locales=["de", "en"], default_locale="en")
    resp = _set_lang(t, "zz")  # мусор → default_locale тенанта
    assert resp.cookies["django_language"].value == "en"


def test_set_language_third_locale_when_enabled(_tenant_urlconf, settings):
    settings.LANGUAGES = LANGUAGES_3
    t = TenantFactory.build(enabled_locales=["de", "fr"], default_locale="de")
    resp = _set_lang(t, "fr")
    assert resp.cookies["django_language"].value == "fr"


def test_set_language_no_tenant_validates_against_registry(_tenant_urlconf):
    """Вне тенант-контекста — фолбэк на реестр settings.LANGUAGES (как до L1)."""
    assert _set_lang(None, "en").cookies["django_language"].value == "en"  # в реестре
    assert _set_lang(None, "zz").cookies["django_language"].value == "de"  # мусор → базовая


# --- L1: оверлей витрины генерик по реестру (не только EN) -----------------


def test_overlay_locales_derived_from_registry(settings):
    settings.LANGUAGES = LANGUAGES_3
    assert siteconfig.overlay_locales() == {"en", "fr"}  # реестр минус базовая (de)


def test_normalize_keeps_third_locale_overlay(settings):
    """Оверлей 3-й локали переживает normalize, если она в реестре."""
    settings.LANGUAGES = LANGUAGES_3
    cfg = siteconfig.normalize(
        {
            "hero_title": "Hallo",
            "i18n": {
                "en": {"hero_title": "Hello"},
                "fr": {"hero_title": "Bonjour"},
                "de": {"hero_title": "x"},  # базовая — не оверлеится
            },
        }
    )
    assert cfg["i18n"] == {"en": {"hero_title": "Hello"}, "fr": {"hero_title": "Bonjour"}}


def test_localize_applies_third_locale(settings):
    settings.LANGUAGES = LANGUAGES_3
    cfg = siteconfig.normalize({"hero_title": "Hallo", "i18n": {"fr": {"hero_title": "Bonjour"}}})
    assert siteconfig.localize(cfg, "fr")["hero_title"] == "Bonjour"
    assert siteconfig.localize(cfg, "de")["hero_title"] == "Hallo"  # база — фолбэк


def test_normalize_drops_locale_outside_registry():
    """Без FR в реестре (дефолт DE/EN) — FR-оверлей отбрасывается (как раньше EN-only)."""
    cfg = siteconfig.normalize(
        {"hero_title": "Hallo", "i18n": {"en": {"hero_title": "Hello"}, "fr": {"hero_title": "x"}}}
    )
    assert cfg["i18n"] == {"en": {"hero_title": "Hello"}}


# --- L1: контекст-процессор отдаёт storefront_locales ---------------------


def test_context_exposes_storefront_locales(_tenant_urlconf, settings):
    from apps.core import context

    settings.LANGUAGES = LANGUAGES_3
    tenant = TenantFactory(enabled_locales=["de", "fr"], default_locale="de")
    req = RequestFactory().get("/")
    req.tenant = tenant
    ctx = context.modules_nav(req)
    assert ctx["storefront_locales"] == [
        {"code": "de", "label": "DE"},
        {"code": "fr", "label": "FR"},
    ]
