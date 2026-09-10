"""LAY-6a/6b — редактор работает в ОДНОМ выбранном языке контента.

Разведка и решения — `docs/lay-unified-output-plan-2026-09-09.md` §11–§12.

До правок панель Студии не звала `localize` ни разу: канва рендерилась на русском,
а поля панели приходили немецкими — владелец правил не то, что видит, и Save
затирал немецкую базу русским текстом. Ввести перевод из панели было негде вовсе.

Правило волны: **переводится только текст**; структура (порядок и видимость секций,
раскладки, стили) общая для всех языков и всегда пишется в базу.

Замки написаны ДО правок и краснеют на текущем коде.
"""

from types import SimpleNamespace

import pytest
from django.conf import settings
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(slug, **kw):
    kw.setdefault("enabled_locales", ["de", "ru"])
    kw.setdefault("default_locale", "de")
    t = TenantFactory(schema_name="public", slug=slug, name=slug.upper(), **kw)
    t.site_config = siteconfig.normalize(
        {
            "hero_title": "Willkommen",
            "hero_text": "Frisch aus dem Ofen",
            "about_title": "Über uns",
            "about_text": "Seit 1998.",
            "faq": [{"q": "Parkplatz?", "a": "Ja."}],
            "i18n": {
                "ru": {
                    "hero_title": "Добро пожаловать",
                    "about_title": "О нас",
                    "faq": [{"q": "Есть парковка?", "a": "Да."}],
                }
            },
        }
    )
    t.save(update_fields=["site_config"])
    return t


def _req(method, path, data=None, tenant=None, lang_cookie=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    if lang_cookie:
        req.COOKIES[settings.LANGUAGE_COOKIE_NAME] = lang_cookie
    return req


def _body(tenant, lang_cookie=None, qs=""):
    resp = views.home_builder_view(
        _req("get", "/dashboard/site/home/" + qs, tenant=tenant, lang_cookie=lang_cookie)
    )
    assert resp.status_code == 200, resp.status_code
    return resp.content.decode()


def _save(tenant, data, lang_cookie=None):
    resp = views.home_builder_view(
        _req("post", "/dashboard/site/home/", data, tenant, lang_cookie=lang_cookie)
    )
    assert resp.status_code == 302
    tenant.refresh_from_db()
    return siteconfig.normalize(tenant.site_config)


def _form(**extra):
    """Минимальный POST основной формы билдера (как её шлёт панель)."""
    data = {
        "hero_title": "Willkommen",
        "hero_text": "Frisch aus dem Ofen",
        "about_title": "Über uns",
        "about_text": "Seit 1998.",
        "content_sections_present": "1",
        "faq_present": "1",
        "faq_q_0": "Parkplatz?",
        "faq_a_0": "Ja.",
    }
    data.update(extra)
    return data


# ── 6a. Панель читает в языке канвы ──────────────────────────────────────────


def test_panel_shows_the_translation_when_the_canvas_is_in_that_language():
    """Канва на русском → в полях панели русский текст, а не немецкая база."""
    tenant = _tenant("lay6a1")
    body = _body(tenant, lang_cookie="ru")
    assert "Добро пожаловать" in body, "панель показывает базу, а не язык канвы"
    assert "Есть парковка?" in body, "список FAQ показан не в языке канвы"


def test_panel_in_the_base_language_is_unchanged():
    """Паритет: канва на немецком → прежние немецкие значения."""
    body = _body(_tenant("lay6a2"), lang_cookie="de")
    assert "Willkommen" in body and "Parkplatz?" in body


def test_language_switch_is_offered_only_when_there_is_a_choice():
    """Селект языка контента — при двух и более локалях; при одной его нет."""
    tenant = _tenant("lay6a3")
    assert 'name="clang"' in _body(tenant), "нет переключателя языка контента"
    tenant.enabled_locales = ["de"]  # одноязычный сайт — выбирать не из чего
    tenant.save(update_fields=["enabled_locales"])
    assert 'name="clang"' not in _body(tenant), "переключатель у одноязычного тенанта"


def test_clang_sets_the_storefront_cookie_and_redirects():
    """`?clang=ru` ставит куку витрины (её же читает канва) и уходит без параметра."""
    tenant = _tenant("lay6a5")
    resp = views.home_builder_view(_req("get", "/dashboard/site/home/?clang=ru", tenant=tenant))
    assert resp.status_code == 302
    assert "clang" not in resp["Location"]
    assert resp.cookies[settings.LANGUAGE_COOKIE_NAME].value == "ru"


def test_unknown_language_is_not_accepted():
    """Локаль вне включённых у тенанта не ставится (fail-closed)."""
    tenant = _tenant("lay6a6")
    resp = views.home_builder_view(_req("get", "/dashboard/site/home/?clang=zz", tenant=tenant))
    assert resp.status_code == 302
    ck = resp.cookies.get(settings.LANGUAGE_COOKIE_NAME)
    assert ck is None or ck.value != "zz"


# ── 6b. Save пишет перевод, а не базу ────────────────────────────────────────


def test_save_in_a_translation_writes_the_overlay_and_keeps_the_base():
    tenant = _tenant("lay6b1")
    cfg = _save(
        tenant,
        _form(
            hero_title="Здравствуйте",
            about_title="О нас",
            faq_q_0="Есть парковка?",
            faq_a_0="Да, бесплатно.",
            content_lang="ru",
        ),
        lang_cookie="ru",
    )
    assert cfg["hero_title"] == "Willkommen", "немецкая база перезаписана переводом"
    assert cfg["faq"][0]["a"] == "Ja.", "немецкий ответ перезаписан"
    ov = cfg["i18n"]["ru"]
    assert ov["hero_title"] == "Здравствуйте"
    assert ov["faq"][0]["a"] == "Да, бесплатно."


def test_save_in_the_base_language_is_unchanged():
    """Паритет: сохранение на немецком пишет базу и не трогает перевод."""
    tenant = _tenant("lay6b2")
    cfg = _save(tenant, _form(hero_title="Servus", content_lang="de"), lang_cookie="de")
    assert cfg["hero_title"] == "Servus"
    assert cfg["i18n"]["ru"]["hero_title"] == "Добро пожаловать", "перевод сбит"


def test_structure_is_shared_between_languages():
    """Порядок/видимость/раскладка — общие: пишутся в базу даже на русском."""
    tenant = _tenant("lay6b3")
    cfg = _save(
        tenant,
        _form(content_lang="ru", enabled_products="on", order_products="1", cols_products="4"),
        lang_cookie="ru",
    )
    products = next(s for s in cfg["sections"] if s.get("key") == "products")
    assert products["enabled"] is True
    assert str((products.get("layout") or {}).get("cols")) == "4"
    ov_sections = (cfg.get("i18n", {}).get("ru") or {}).get("sections") or []
    assert all(set(b or {}) <= {"data"} for b in ov_sections), "структура секций утекла в перевод"


def test_unchanged_fields_do_not_create_overlay_noise():
    """Поле не тронуто (пришло тем же переводом) → база цела, оверлей прежний."""
    tenant = _tenant("lay6b4")
    cfg = _save(
        tenant,
        _form(
            hero_title="Добро пожаловать",
            about_title="О нас",
            faq_q_0="Есть парковка?",
            faq_a_0="Да.",
            content_lang="ru",
        ),
        lang_cookie="ru",
    )
    assert cfg["hero_title"] == "Willkommen"
    assert cfg["about_title"] == "Über uns"
    assert cfg["i18n"]["ru"]["hero_title"] == "Добро пожаловать"


def test_a_new_list_item_added_in_a_translation_gets_a_base_text():
    """У нового вопроса немецкого оригинала нет — его текст идёт в базу (§12.4)."""
    tenant = _tenant("lay6b5")
    cfg = _save(
        tenant,
        _form(
            faq_q_0="Есть парковка?",
            faq_a_0="Да.",
            faq_q_1="Принимаете карты?",
            faq_a_1="Да, все.",
            content_lang="ru",
        ),
        lang_cookie="ru",
    )
    assert len(cfg["faq"]) == 2
    assert cfg["faq"][1]["q"] == "Принимаете карты?", "новый вопрос потерян"


def test_cblock_texts_go_to_the_overlay_too():
    """Текст C-блока страницы — тот же путь (данные блока, не его структура)."""
    tenant = _tenant("lay6b6")
    tenant.site_config = siteconfig.normalize(
        {
            **tenant.site_config,
            "sections": [
                {
                    "key": "text",
                    "id": "cb1",
                    "enabled": True,
                    "order": 1,
                    "data": {"title": "Unser Team"},
                }
            ],
        }
    )
    tenant.save(update_fields=["site_config"])
    cfg = _save(
        tenant,
        _form(
            content_lang="ru",
            cb_id="cb1",
            cb_type_cb1="text",
            cb_enabled_cb1="on",
            order_cb_cb1="1",
            cb_cb1_title="Наша команда",
        ),
        lang_cookie="ru",
    )
    block = next(s for s in cfg["sections"] if s.get("id") == "cb1")
    assert block["data"]["title"] == "Unser Team", "немецкий заголовок блока перезаписан"
    ov_blocks = cfg["i18n"]["ru"].get("sections") or []
    assert any((b or {}).get("data", {}).get("title") == "Наша команда" for b in ov_blocks)


# ── База = LANGUAGE_CODE, а не default_locale (§12.3) ────────────────────────


def test_tenant_whose_default_is_russian_still_edits_the_overlay():
    """У тенанта с `default_locale="ru"` правка на ru идёт в оверлей ru: иначе она
    ушла бы в базу и была бы не видна — существующий оверлей замещает базу."""
    import json

    tenant = _tenant("lay6b7", enabled_locales=["de", "ru"], default_locale="ru")
    req = _req("post", "/dashboard/site/inline/", tenant=tenant)
    req._body = json.dumps({"field": "hero_title", "value": "Привет", "locale": "ru"}).encode()
    views.site_inline_edit(req)
    tenant.refresh_from_db()
    assert tenant.site_config["hero_title"] == "Willkommen", "немецкая база перезаписана"
    assert tenant.site_config["i18n"]["ru"]["hero_title"] == "Привет"


# ── Реестр переводимых ключей — один на проект ───────────────────────────────


def test_translatable_registry_has_one_owner():
    """Обход демо-переводов и разбор Save обязаны читать ОДИН список ключей."""
    from apps.tenants import demo_i18n

    assert demo_i18n._TRANSLATABLE_CONFIG_KEYS is siteconfig.TRANSLATABLE_KEYS


# ── Черновик знает свой язык (иначе он же и портит базу) ─────────────────────


def test_a_draft_typed_in_one_language_is_not_restored_in_another():
    """Черновик, набранный на русском, не должен подставляться в НЕМЕЦКУЮ форму:
    иначе следующий Save на немецком запишет русский текст в базу."""
    import json

    tenant = _tenant("lay6b8")
    req = _req("post", "/dashboard/site/preview/draft/", tenant=tenant, lang_cookie="ru")
    req._body = json.dumps({"hero_title": "Черновик"}).encode()
    views.site_preview_draft(req)
    tenant.refresh_from_db()
    assert (tenant.site_config.get("_draft") or {}).get("hero_title") == "Черновик"

    body = _body(tenant, lang_cookie="de")
    assert "Черновик" not in body, "русский черновик подставлен в немецкую форму"
    assert "Willkommen" in body
    # На своём языке черновик по-прежнему восстанавливается.
    assert "Черновик" in _body(tenant, lang_cookie="ru")


def test_links_and_photos_are_not_translated():
    """Адрес и картинка — не текст: правка на русском должна менять их ВЕЗДЕ,
    иначе немецкая витрина осталась бы со старой ссылкой."""
    tenant = _tenant("lay6b9")
    cfg = dict(tenant.site_config)
    cfg["cta"] = {
        "title": "Jetzt buchen",
        "text": "Schnell",
        "button_label": "Buchen",
        "button_url": "/termin/",
    }
    tenant.site_config = siteconfig.normalize(cfg)
    tenant.save(update_fields=["site_config"])
    saved = _save(
        tenant,
        _form(
            content_lang="ru",
            cta_title="Записаться",
            cta_text="Быстро",
            cta_button_label="Записаться",
            cta_button_url="/buchen/",
        ),
        lang_cookie="ru",
    )
    assert saved["cta"]["button_url"] == "/buchen/", (
        "адрес уехал в перевод — база со старой ссылкой"
    )
    assert saved["cta"]["title"] == "Jetzt buchen", "немецкий заголовок перезаписан"
    assert saved["i18n"]["ru"]["cta"]["title"] == "Записаться"
    assert "button_url" not in saved["i18n"]["ru"]["cta"]
