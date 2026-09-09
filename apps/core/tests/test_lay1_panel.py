"""LAY-1 — фидбэк владельца по панели Студии (4 скриншота, 2026-09-09).

Разбор и план — `docs/lay-unified-output-plan-2026-09-09.md` (§6, §8). Здесь замки на
три дефекта, которые чинятся независимо от решения по архитектуре видов вывода:

* **Д-A** «Содержание» пусто у блоков «О нас» и «Контакты и часы работы»: у первого
  тексты правились ТОЛЬКО инлайн на канве, у второго данных в `site_config` нет вовсе
  (это поля бизнеса), а пустую группу никто не прятал.
* **Д-B** FAQ одной простынёй «Вопрос | Ответ» вместо пар полей с кнопкой «добавить»,
  и на канве блок FAQ не редактируется (ни одного `data-edit`).
* **Д-D4** строка «Применить макет ко всем целевым страницам» — второй писатель тех же
  ключей раскладки без охвата и без пометки настройки.

Замки написаны ДО правок и краснеют на текущем коде.
"""

from types import SimpleNamespace

import pytest
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


def _request(method, path, data=None, tenant=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _body(tenant):
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    assert resp.status_code == 200
    return resp.content.decode()


def _save(tenant, data):
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    return siteconfig.normalize(tenant.site_config)


# ── Д-A. «О нас»: тексты правятся в панели, а не только на канве ──────────────


def test_about_texts_are_editable_in_the_panel():
    tenant = TenantFactory(schema_name="public", slug="lay1a", name="LAY1A")
    body = _body(tenant)
    assert 'name="about_title"' in body, "в строке блока «О нас» нет поля заголовка"
    assert 'name="about_text"' in body, "в строке блока «О нас» нет поля текста"


def test_about_texts_are_saved_and_survive_a_foreign_post():
    """Presence-guard (W0): чужой POST без этих полей не стирает тексты."""
    tenant = TenantFactory(schema_name="public", slug="lay1a2", name="LAY1A2")
    cfg = _save(tenant, {"about_title": "Über uns", "about_text": "Seit 1998."})
    assert cfg["about_title"] == "Über uns"
    assert cfg["about_text"] == "Seit 1998."
    cfg = _save(tenant, {"hero_title": "X"})  # форма без блока «О нас»
    assert cfg["about_title"] == "Über uns", "чужой POST стёр заголовок (класс W0)"
    assert cfg["about_text"] == "Seit 1998."


def test_about_texts_reach_the_live_draft():
    """Живой черновик: правка видна на канве до Save (как у баннера)."""
    tenant = TenantFactory(schema_name="public", slug="lay1a3", name="LAY1A3")
    req = _request("post", "/dashboard/site/preview-draft/", tenant=tenant)
    req._body = b'{"about_title": "Neu", "about_text": "Text"}'
    req.META["CONTENT_TYPE"] = "application/json"
    resp = views.site_preview_draft(req)
    assert resp.status_code in (200, 204)
    draft = req.session.get("site_preview_draft") or {}
    assert draft.get("about_title") == "Neu"
    assert draft.get("about_text") == "Text"


# ── Д-A. «Контакты и часы»: группа не бывает пустой ──────────────────────────


def test_contact_block_explains_where_its_data_lives():
    """У блока контактов данных в site_config нет — панель обязана сказать, где они."""
    tenant = TenantFactory(schema_name="public", slug="lay1a4", name="LAY1A4")
    body = _body(tenant)
    assert 'data-lay-hint="contact"' in body, "блок контактов молчит про источник данных"


# ── Д-B. FAQ парами полей + слот для нового вопроса ──────────────────────────


def test_faq_is_edited_as_pairs_with_an_empty_slot():
    tenant = TenantFactory(schema_name="public", slug="lay1b", name="LAY1B")
    tenant.site_config = siteconfig.normalize({"faq": [{"q": "Parkplatz?", "a": "Ja."}]})
    tenant.save(update_fields=["site_config"])
    body = _body(tenant)
    assert 'name="faq_q_0"' in body and 'name="faq_a_0"' in body, "FAQ не парами полей"
    assert 'name="faq_q_1"' in body, "нет пустого слота для нового вопроса"


def test_faq_pairs_are_parsed_and_empty_rows_dropped():
    got = siteconfig.parse_content_sections(
        {
            "faq_present": "1",
            "faq_q_0": "Parkplatz?",
            "faq_a_0": "Ja, direkt davor.",
            "faq_q_1": "",
            "faq_a_1": "",
            "faq_q_2": "Lieferung?",
            "faq_a_2": "Ab 30 €.",
        }.get
    )["faq"]
    assert got == [
        {"q": "Parkplatz?", "a": "Ja, direkt davor."},
        {"q": "Lieferung?", "a": "Ab 30 €."},
    ]


def test_faq_textarea_still_works_for_old_forms():
    """Обратная совместимость: демо-киты и старые формы шлют `faq_text`."""
    got = siteconfig.parse_content_sections({"faq_text": "Frage? | Antwort."}.get)["faq"]
    assert got == [{"q": "Frage?", "a": "Antwort."}]


def test_faq_pairs_reach_the_live_draft():
    tenant = TenantFactory(schema_name="public", slug="lay1b2", name="LAY1B2")
    req = _request("post", "/dashboard/site/preview-draft/", tenant=tenant)
    req._body = b'{"faq_present": "1", "faq_q_0": "Q?", "faq_a_0": "A."}'
    req.META["CONTENT_TYPE"] = "application/json"
    resp = views.site_preview_draft(req)
    assert resp.status_code in (200, 204)
    draft = req.session.get("site_preview_draft") or {}
    assert draft.get("faq") == [{"q": "Q?", "a": "A."}]


# ── Д-B. FAQ правится прямо в блоке на канве ─────────────────────────────────


def test_faq_section_is_inline_editable_on_the_canvas():
    from django.template.loader import render_to_string

    html = render_to_string(
        "storefront/sections/_faq.html",
        {"site": {"faq": [{"q": "Frage?", "a": "Antwort."}]}, "section_row": {}},
    )
    assert 'data-edit="faq.0.q"' in html, "вопрос не редактируется на канве"
    assert 'data-edit="faq.0.a"' in html, "ответ не редактируется на канве"


def test_inline_edit_accepts_faq_pairs_and_rejects_garbage():
    import json

    tenant = TenantFactory(schema_name="public", slug="lay1b3", name="LAY1B3")
    tenant.site_config = siteconfig.normalize({"faq": [{"q": "Alt", "a": "Alt"}]})
    tenant.save(update_fields=["site_config"])

    def _post(field, value):
        req = _request("post", "/dashboard/site/inline/", tenant=tenant)
        req._body = json.dumps({"field": field, "value": value}).encode()
        return views.site_inline_edit(req)

    assert _post("faq.0.q", "Neu?").status_code in (200, 204)
    tenant.refresh_from_db()
    assert tenant.site_config["faq"][0]["q"] == "Neu?"
    assert _post("faq.9.q", "X").status_code == 400, "индекс вне списка обязан отбиваться"
    assert _post("faq.0.x", "X").status_code == 400, "чужое поле пары обязано отбиваться"
    assert _post("faq.q.0", "X").status_code == 400, "нечисловой индекс обязан отбиваться"


# ── Д-D4. Второй писатель раскладки помечен как настройка ────────────────────


def test_apply_layout_to_all_has_no_second_source_of_truth():
    """Строка «применить ко всем» была ВТОРЫМ селектором тех же ключей раскладки.

    Свой набор пресетов у неё не знал про расширенные пресеты каталога, поэтому
    «применить» молча сбрасывало прайс-вид. Теперь это действие без своего значения:
    берёт раскладку открытой страницы и копирует в остальные списки.
    """
    tenant = TenantFactory(schema_name="public", slug="lay1d", name="LAY1D")
    body = _body(tenant)
    assert 'id="apply-all-preset"' not in body, "второй селектор раскладки остался"
    assert 'id="apply-all-landings"' in body, "удобное действие потеряно целиком"
