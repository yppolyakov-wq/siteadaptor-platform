"""T1 (FB-12): язык кабинета — отдельный от языка витрины.

Замки: дефолт = de (кабинет как раньше, msgid); сессия переключает на переведённый
язык; невалидный игнорируется; middleware активирует локаль ТОЛЬКО на кабинет-путях
(витрину не трогает); пилотные строки под EN переводятся, под DE = msgid."""

from django.contrib.sessions.middleware import SessionMiddleware
from django.template import Context, Template
from django.test import RequestFactory
from django.utils import translation

from apps.core import i18n_cabinet
from apps.core.middleware import CabinetLocaleMiddleware


def _req(path):
    r = RequestFactory().get(path)
    SessionMiddleware(lambda x: None).process_request(r)
    return r


def test_codes_include_de_and_en():
    codes = i18n_cabinet.cabinet_language_codes()
    assert codes[0] == "de" and "en" in codes  # de первый (исходный)


def test_languages_have_labels():
    langs = {x["code"]: x["label"] for x in i18n_cabinet.cabinet_languages()}
    assert langs["de"] == "Deutsch" and langs["en"] == "English"


def test_resolve_default_is_de():
    # без сессии-выбора кабинет = немецкий (как раньше)
    assert i18n_cabinet.resolve_cabinet_locale(_req("/dashboard/")) == "de"


def test_resolve_session_override():
    r = _req("/dashboard/")
    assert i18n_cabinet.set_cabinet_locale(r, "en") is True
    assert r.session[i18n_cabinet.SESSION_KEY] == "en"
    assert i18n_cabinet.resolve_cabinet_locale(r) == "en"


def test_set_rejects_unavailable_language():
    # tr в реестре витрины, но НЕ в CABINET_LANGUAGES (ещё не переведён) → отклонён
    r = _req("/dashboard/")
    assert i18n_cabinet.set_cabinet_locale(r, "tr") is False
    assert i18n_cabinet.SESSION_KEY not in r.session
    assert i18n_cabinet.resolve_cabinet_locale(r) == "de"


def test_middleware_activates_on_cabinet_path():
    captured = {}

    def get_response(req):
        captured["lang"] = translation.get_language()
        return "ok"

    r = _req("/dashboard/")
    r.session[i18n_cabinet.SESSION_KEY] = "en"
    try:
        CabinetLocaleMiddleware(get_response)(r)
        assert captured["lang"] == "en"
        assert r.LANGUAGE_CODE == "en"
    finally:
        translation.activate("de")  # не протекать в другие тесты


def test_middleware_skips_storefront_path():
    captured = {}

    def get_response(req):
        captured["lang"] = translation.get_language()
        return "ok"

    r = _req("/sortiment/")  # витрина — не кабинет-путь
    r.session[i18n_cabinet.SESSION_KEY] = "en"
    with translation.override("de"):
        CabinetLocaleMiddleware(get_response)(r)
        assert captured["lang"] == "de"  # middleware НЕ трогает язык витрины


def _active_lang_after_mw(path):
    """Язык, активный внутри вьюхи, после прохода CabinetLocaleMiddleware по `path`."""
    r = _req(path)
    r.session[i18n_cabinet.SESSION_KEY] = "en"
    box = {}

    def get_response(req):
        box["lang"] = translation.get_language()
        return "ok"

    try:
        CabinetLocaleMiddleware(get_response)(r)
    finally:
        translation.activate("de")
    return box["lang"]


def test_middleware_covers_root_cabinet_paths():
    # разделы кабинета вне /dashboard/ (catalog/promotions/...) тоже активируются
    for path in ("/catalog/products/", "/promotions/", "/imports/", "/crm/"):
        assert _active_lang_after_mw(path) == "en", path


def test_pilot_strings_translate_under_en():
    """Пилот T1-a: под EN строки шапки переводятся; под DE = немецкий msgid (как раньше).
    Полный перевод кабинета — T1-b (.mo компилируется в CI, как email_i18n)."""
    tpl = Template(
        '{% load i18n %}{% trans "Einfach" %}|{% trans "Experte" %}|{% trans "Sprachen" %}'
    )
    with translation.override("en"):
        assert tpl.render(Context({})) == "Simple|Expert|Languages"
    with translation.override("de"):
        assert tpl.render(Context({})) == "Einfach|Experte|Sprachen"
