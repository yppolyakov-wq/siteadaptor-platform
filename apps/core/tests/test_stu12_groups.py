"""STU-12e: настройки блока сгруппированы (Inhalt · Darstellung · Erweitert).

ТЗ `docs/stu12-studio-simplification-plan-2026-09-09.md` §2 (12e): тексты контент-секций
(`_section_fields.html`), поля баннера (`hero_title`/`hero_text`/`hero_image`) и карточки
архетипов переезжают В СТРОКУ СВОЕЙ СЕКЦИИ — с теми же `name=`, внутри `#home-form`
(W0: ни одно поле не пропало из формы, скрытие только CSS). Настройки строки делятся на
три группы: Inhalt (данные) · Darstellung (вид) · Erweitert (`data-expert`).

Отдельно: высота «Abstand» становится КОНТРОЛОМ (сегодня её задаёт только пресет вставки,
а Save её теряет), а вставка блока открывает его настройки.
"""

import pathlib
import re
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TPL = pathlib.Path("templates/tenant/site_home.html")

# ключ секции → поля, которые обязаны жить В ЕЁ строке (те же name=, что и раньше)
SECTION_FIELDS = {
    "cta": ("cta_title", "cta_button_label", "cta_text", "cta_button_url"),
    "testimonials": ("testimonials_text",),
    "process": ("process_text",),
    "team": ("team_text",),
    "trust": ("trust_since", "trust_marks"),
    "usp_bar": ("usp_text",),
    # LAY-1b (осознанная переписка): FAQ правится ПАРАМИ полей — владелец просил
    # «заголовок и описание отдельными полями и кнопочку добавить» вместо одной
    # простыни «Вопрос | Ответ». Сентинел `faq_present` отличает новую форму от
    # старой; `faq_text` остаётся в парсере ради демо-китов и прежнего черновика.
    "faq": ("faq_q_0", "faq_a_0", "faq_present"),
    "hero": ("hero_title", "hero_text", "hero_image"),
}


def _req(method, path, tenant, data=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _builder(tenant):
    return views.home_builder_view(_req("get", "/dashboard/site/home/", tenant)).content.decode()


def _segment(body, start_marker, end_marker):
    i = body.index(start_marker)
    return body[i : body.index(end_marker, i)]


def _row(body, key):
    """Разметка строки секции `key`: от её `order_<key>` до начала следующей строки."""
    i = body.index(f'name="order_{key}"')
    start = body.rindex('class="home-block ', 0, i)
    nxt = body.find('class="home-block ', i)
    return body[start : nxt if nxt != -1 else body.index('id="home-cblocks"', i)]


def _post_builder(tenant, data):
    resp = views.home_builder_view(_req("post", "/dashboard/site/home/", tenant, data))
    assert resp.status_code == 302, resp.status_code
    tenant.refresh_from_db()
    return siteconfig.normalize(tenant.site_config)


def test_section_texts_live_in_their_own_row():
    """Текст секции правится ТАМ ЖЕ, где её вид, — в строке блока, а не в общем ящике."""
    body = _builder(TenantFactory(slug="stgr1", name="StGr1"))
    for key, fields in SECTION_FIELDS.items():
        row = _row(body, key)
        for name in fields:
            assert f'name="{name}"' in row, f"{name} обязан быть в строке секции {key}"
    # общий ящик «Content sections» больше не нужен — иначе поля были бы в двух местах
    for name in ("faq_q_0", "cta_title", "usp_text", "hero_title"):
        assert body.count(f'name="{name}"') == 1, f"{name} не должен дублироваться"


def test_archetype_cards_live_in_the_archetypes_row():
    tenant = TenantFactory(slug="stgr2", name="StGr2")
    body = _builder(tenant)
    row = _row(body, "archetypes")
    names = re.findall(r'name="(arch_(?:visible|label|blurb)_[a-z_]+)"', body)
    assert names, "у тенанта есть тизеры архетипов — иначе тест бессмысленен"
    for name in names:
        assert f'name="{name}"' in row, f"{name} обязан быть в строке «Unser Angebot»"


def test_block_settings_are_grouped():
    """Три группы в строке: данные · вид · продвинутое (F8A)."""
    body = _builder(TenantFactory(slug="stgr3", name="StGr3"))
    row = _row(body, "faq")
    for grp in ("inhalt", "darstellung", "erweitert"):
        assert f'data-grp="{grp}"' in row, grp
    # Erweitert — только для Эксперта (тот же механизм, что и остальные data-expert)
    adv = _segment(row, 'data-grp="erweitert"', "</details>")
    assert "data-expert" in adv


def test_no_field_leaves_the_form_after_the_move():
    """W0: все поля контента остаются в `#home-form` (скрытие — только CSS)."""
    body = _builder(TenantFactory(slug="stgr4", name="StGr4"))
    form = _segment(body, 'id="home-form"', "</form>")
    for fields in SECTION_FIELDS.values():
        for name in fields:
            assert f'name="{name}"' in form, name


def test_save_without_content_fields_keeps_the_texts():
    """Страховка W0-класса: `parse_content_sections` пишет ВСЕ 11 ключей без presence-гарда.

    Пока поля лежали в общем ящике, они уезжали в каждый POST. После переезда в строки
    любой POST без них (чужая форма, будущий гейт строки по архетипу) стёр бы тексты —
    поэтому парсинг гейтится сентинелом, который рисует сама форма.
    """
    tenant = TenantFactory(
        slug="stgr5",
        name="StGr5",
        site_config={"faq": [{"q": "Parkplatz?", "a": "Ja."}], "cta": {"title": "Jetzt buchen"}},
    )
    cfg = _post_builder(tenant, {"order_faq": "1", "enabled_faq": "on"})
    assert cfg["faq"] == [{"q": "Parkplatz?", "a": "Ja."}], "POST без полей текста не стирает FAQ"
    assert cfg["cta"]["title"] == "Jetzt buchen"


def test_save_with_the_sentinel_still_writes_the_texts():
    tenant = TenantFactory(slug="stgr6", name="StGr6")
    cfg = _post_builder(
        tenant,
        {
            "content_sections_present": "1",
            "faq_text": "Parkplatz? | Ja, direkt davor.",
            "cta_title": "Tisch reservieren",
        },
    )
    assert cfg["faq"] == [{"q": "Parkplatz?", "a": "Ja, direkt davor."}]
    assert cfg["cta"]["title"] == "Tisch reservieren"


def test_spacer_height_survives_save():
    """Сегодня Save ТЕРЯЕТ высоту отступа: `_read_cblock_data` не знает про spacer."""
    tenant = TenantFactory(
        slug="stgr7",
        name="StGr7",
        site_config={
            "sections": [
                {
                    "key": "spacer",
                    "id": "sp1",
                    "enabled": True,
                    "order": 1,
                    "data": {"height": "lg"},
                }
            ]
        },
    )
    body = _builder(tenant)
    assert 'name="cb_sp1_height"' in body, "у отступа обязан быть контрол высоты"
    cfg = _post_builder(
        tenant,
        {
            "cb_id": "sp1",
            "cb_type_sp1": "spacer",
            "enabled_cb_sp1": "on",
            "order_cb_sp1": "1",
            "cb_sp1_height": "xl",
        },
    )
    spacer = next(s for s in cfg["sections"] if s.get("id") == "sp1")
    assert spacer["data"] == {"height": "xl"}, spacer["data"]


def test_live_draft_carries_the_spacer_height():
    tpl = TPL.read_text(encoding="utf-8")
    fields = _segment(tpl, "var CB_DATA_FIELDS", "]")
    assert '"height"' in fields, "черновик обязан слать высоту — иначе превью её теряет"


def test_inserting_a_block_opens_its_settings():
    """После вставки блок открывается — иначе владелец ищет его в списке руками."""
    tenant = TenantFactory(slug="stgr8", name="StGr8")
    resp = views.home_builder_view(
        _req("post", "/dashboard/site/home/", tenant, {"action": "add_block", "block_type": "text"})
    )
    assert resp.status_code == 302
    assert "block=" in resp["Location"], resp["Location"]
    tpl = TPL.read_text(encoding="utf-8")
    assert "openBlockPopup(" in _segment(tpl, "BLD_OPEN_BLOCK", "</script>")
