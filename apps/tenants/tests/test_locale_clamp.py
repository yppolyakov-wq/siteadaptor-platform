"""SF-1.8: витрина говорит только на включённых тенантом языках.

LocaleMiddleware негоциирует Accept-Language по всему settings.LANGUAGES —
браузер с pl/fr/… (в реестре есть, у тенанта не включён, каталога locale/ нет)
получал витрину из сырых msgid; Accept-Language: en давал английскую витрину
бизнесу, включившему только de. StorefrontLocaleClampMiddleware стоит сразу
после LocaleMiddleware и клампит его выбор к tenant.active_locales.
"""

import pytest
from django.test import RequestFactory
from django.utils import translation

from apps.core.middleware import StorefrontLocaleClampMiddleware
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _run(tenant, path="/", active="pl"):
    """Симулируем состояние после LocaleMiddleware: активирована локаль active."""
    request = RequestFactory().get(path)
    request.tenant = tenant
    seen = {}

    def get_response(req):
        seen["lang"] = translation.get_language()
        return None

    translation.activate(active)
    try:
        StorefrontLocaleClampMiddleware(get_response)(request)
    finally:
        translation.deactivate()
    return seen["lang"], request


def test_unknown_locale_clamps_to_tenant_default():
    t = TenantFactory(enabled_locales=["de", "en"], default_locale="de")
    lang, request = _run(t, active="pl")
    assert lang == "de"
    assert request.LANGUAGE_CODE == "de"


def test_negotiated_en_stays_when_enabled():
    t = TenantFactory(enabled_locales=["de", "en"], default_locale="de")
    lang, _ = _run(t, active="en")
    assert lang == "en"


def test_en_clamped_when_tenant_is_de_only():
    # Наблюдение внешнего ТЗ «сайт встречает английским»: у de-only бизнеса
    # английский браузер больше не получает EN-витрину.
    t = TenantFactory(enabled_locales=["de"], default_locale="de")
    lang, _ = _run(t, active="en")
    assert lang == "de"


def test_cabinet_paths_untouched():
    # Языком кабинета правит CabinetLocaleMiddleware — кламп его не перебивает.
    t = TenantFactory(enabled_locales=["de"], default_locale="de")
    lang, _ = _run(t, path="/dashboard/", active="en")
    assert lang == "en"


def test_public_schema_untouched():
    t = TenantFactory(schema_name="public", enabled_locales=["de"], default_locale="de")
    lang, _ = _run(t, active="en")
    assert lang == "en"
