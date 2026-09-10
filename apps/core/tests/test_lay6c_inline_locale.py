"""LAY-6c — инлайн-правка на канве уважает язык, который на канве показан.

Разведка 2026-09-10 (план LAY §11): `site_inline_edit` не знал про локаль вовсе.
Канва рендерится на языке посетителя (cookie, склампленная к локалям тенанта), а
правка уходила в НЕМЕЦКОЕ базовое поле. Последствия — не неудобство, а порча
контента:

* немецкая витрина начинала показывать русскую фразу;
* на канве правка не появлялась вовсе — оверлей перевода замещает базу;
* исходный немецкий текст терялся безвозвратно.

Из трёх дефектов языка редактора этот единственный ПОРТИТ данные, поэтому он
первый. Замки написаны ДО правок и краснеют на текущем коде.
"""

import json
from types import SimpleNamespace

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(slug, **kw):
    t = TenantFactory(schema_name="public", slug=slug, name=slug.upper(), **kw)
    t.site_config = {
        "hero_title": "Willkommen",
        "faq": [{"q": "Parkplatz?", "a": "Ja."}],
        "i18n": {"ru": {"hero_title": "Добро пожаловать"}},
    }
    t.save(update_fields=["site_config"])
    return t


def _edit(tenant, field, value, locale=None):
    payload = {"field": field, "value": value}
    if locale is not None:
        payload["locale"] = locale
    req = RequestFactory().post("/dashboard/site/inline/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    req._body = json.dumps(payload).encode()
    resp = views.site_inline_edit(req)
    tenant.refresh_from_db()
    return resp


def test_edit_in_a_translation_writes_the_overlay_not_the_base():
    """Правка русского текста НЕ трогает немецкое поле."""
    tenant = _tenant("lay6c1", enabled_locales=["de", "ru"], default_locale="de")
    assert _edit(tenant, "hero_title", "Здравствуйте", locale="ru").status_code in (200, 204)
    assert tenant.site_config["hero_title"] == "Willkommen", "немецкая база перезаписана"
    assert tenant.site_config["i18n"]["ru"]["hero_title"] == "Здравствуйте"


def test_edit_in_the_base_locale_still_writes_the_base():
    """Немецкая правка работает как раньше — паритет."""
    tenant = _tenant("lay6c2", enabled_locales=["de", "ru"], default_locale="de")
    _edit(tenant, "hero_title", "Servus", locale="de")
    assert tenant.site_config["hero_title"] == "Servus"
    assert tenant.site_config["i18n"]["ru"]["hero_title"] == "Добро пожаловать", "перевод сбит"


def test_missing_locale_falls_back_to_the_base():
    """Старый клиент (без поля `locale`) не должен ломаться."""
    tenant = _tenant("lay6c3", enabled_locales=["de", "ru"], default_locale="de")
    _edit(tenant, "hero_title", "Moin")
    assert tenant.site_config["hero_title"] == "Moin"


def test_unknown_locale_is_ignored_and_writes_the_base():
    """Локаль, которой у тенанта нет, не создаёт мусорный оверлей (fail-closed)."""
    tenant = _tenant("lay6c4", enabled_locales=["de", "ru"], default_locale="de")
    _edit(tenant, "hero_title", "Hallo", locale="zz")
    assert tenant.site_config["hero_title"] == "Hallo"
    assert "zz" not in (tenant.site_config.get("i18n") or {})


def test_nested_and_list_fields_write_the_overlay_too():
    """`cta.title` и `faq.<i>.q` — та же семантика (оверлей зеркалит форму базы)."""
    tenant = _tenant("lay6c5", enabled_locales=["de", "ru"], default_locale="de")
    _edit(tenant, "faq.0.q", "Есть парковка?", locale="ru")
    assert tenant.site_config["faq"][0]["q"] == "Parkplatz?", "немецкий вопрос перезаписан"
    assert tenant.site_config["i18n"]["ru"]["faq"][0]["q"] == "Есть парковка?"


def test_canvas_sends_the_locale_it_renders():
    """Клиент обязан слать локаль КАДРА — иначе сервер не может её узнать."""
    with open("templates/tenant/site_home.html", encoding="utf-8") as fh:
        body = fh.read()
    assert "documentElement.lang" in body, "канва не сообщает свой язык при инлайн-правке"
