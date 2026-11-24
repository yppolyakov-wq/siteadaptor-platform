"""FB-33 M5b-2: замки по ревью среза A (django-reviewer, silent-failure-hunter).

План — `docs/fb33-stack10-plan-2026-11-22.md` §8. Пункты ревью:

1. сессия до деплоя с двумя снимками окна (`__page` «Einstellungen der Seite» и `__title`
   «Seitentitel»): снимок — одного окна, второй не затирается, а вливается (чего нет в
   снимке окна с присланным токеном — переносится из второго, прежде всего `title`); без
   токена — оба ждут; что отброшено — в лог; переводы `btr` сливаются по языкам;
2. снимок `__page`, открытый до деплоя (без `title`): первая правка заголовка в этом окне
   дописывает в снимок заголовок до неё — «Abbrechen» откатывает и его;
3. метка «Überschrift der Seite»: ряд, в котором блоки и над, и под точкой заголовка, —
   метка перед этим рядом;
4. ссылка «Wie auf der Seite …» не строится, когда правило не даёт строки;
5. ссылка на форму категории у ★-строки — у категории строка есть всегда;
6. «Darstellung der Liste – im Block …» у ★-строки — у каждого списка со своим видом;
7. повреждённый снимок `__title` (не словарь) — отброшен с логом `warning`.
"""

import copy
import logging
import re

import pytest
from django.db import connection

from apps.core import aufbau_draft, block_views, page_title, page_window, site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window import _shop
from apps.core.tests.test_fb33_m3_window_before import CFG, _panel
from apps.core.tests.test_fb33_m5b2_server import _as_before_deploy
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

PAGE = site_schema.PAGE_REF
TITLE = page_title.TITLE_REF
CODE = "promos"
WOPEN = "openRvA"  # окно «Seitentitel» (до деплоя — `__title`)
OTHER = "openRvB"  # окно «Einstellungen der Seite» (`__page`)
LOGGER = "apps.core.aufbau_draft"


@pytest.fixture(autouse=True)
def _restore_connection_tenant():
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _tenant(bt="friseur", config=None):
    tenant = TenantFactory(
        business_type=bt,
        disabled_modules=list(default_disabled_for(bt)),
        site_config=copy.deepcopy(config) if config is not None else {},
    )
    connection.tenant = tenant
    return tenant


def _drafts(b):
    return copy.deepcopy((b.session or {}).get(aufbau_draft.SESSION_KEY) or {})


def _free_setting(b, code):
    """Первая настройка строки `__page` с невыбранным значением: (код, значение)."""
    html = b.get(f"?seite={code}&block={PAGE}")
    for form in re.finditer(
        r'<form method="post"[^>]*data-schema-setting="([a-z_]+)" data-pt-setting.*?</form>',
        html,
        re.S,
    ):
        radios = re.findall(r'<input type="radio"[^>]*name="value"[^>]*>', form.group(0))
        free = [
            re.search(r'value="([^"]*)"', r).group(1)
            for r in radios
            if " checked" not in r and " disabled" not in r
        ]
        if free:
            return form.group(1), free[0]
    raise AssertionError(f"у {code} нет настройки с выбором")


def _two_windows():
    """Сессия до деплоя у одной страницы: окно «Einstellungen der Seite» (`__page`, токен
    OTHER) правило настройку типа, окно «Seitentitel» (`__title`, токен WOPEN) — заголовок и
    перевод. Снимки — настоящие (их пишет код), ключи заголовка — как до слияния."""
    tenant = _shop()
    title = Browser(tenant)
    title.post(seite=CODE, ref=PAGE, op="update", panel_present="1", wopen=WOPEN,
               f_title="Neu", f_tr_title_en="Deals")  # fmt: skip
    _as_before_deploy(title)
    old = _drafts(title)[CODE]
    b = Browser(tenant)
    setting, value = _free_setting(b, CODE)
    _resp, msgs = b.post(seite=CODE, ref=PAGE, op="setting", setting=setting, value=value,
                         wopen=OTHER)  # fmt: skip
    draft = b.session[aufbau_draft.SESSION_KEY][CODE]
    assert draft.get("settings"), msgs
    draft[aufbau_draft.WINDOW_KEY][PAGE].pop("title", None)  # снимок окна до деплоя — без заголовка
    legacy = old[aufbau_draft.WINDOW_KEY][TITLE]
    for key in ("codes", "settings"):  # окно «Seitentitel» до деплоя настроек типа не несло
        legacy.pop(key, None)
    draft[aufbau_draft.WINDOW_KEY][TITLE] = legacy
    for key in ("title", "btr", "btr_base"):
        draft[key] = old[key]
    b.session.modified = True
    assert set(draft[aufbau_draft.WINDOW_KEY]) == {PAGE, TITLE}
    return b


# ───────────── 1. два снимка: слияние вместо затирания ─────────────


@pytest.mark.parametrize("token", (OTHER, WOPEN))
def test_two_snapshots_cancel_reverts_settings_and_title(token):
    """Какое бы из двух окон ни нажало «Abbrechen» (его токен — в снимке), откатываются и
    настройки, и заголовок с переводом: снимки слиты, ни один не затёрт."""
    b = _two_windows()
    _resp, msgs = b.post(seite=CODE, ref=PAGE, op="revert", wopen=token)
    assert "Änderungen an diesem Block zurückgenommen." in msgs
    assert _drafts(b) == {}, "настройки, заголовок и перевод — как до правок"


def test_two_snapshots_merged_into_window_of_the_token():
    b = _two_windows()
    b.post(seite=CODE, ref=PAGE, op="update", panel_present="1", wopen=OTHER,
           f_title="Neu 2")  # fmt: skip
    window = _drafts(b)[CODE][aufbau_draft.WINDOW_KEY]
    assert set(window) == {PAGE}
    proto = window[PAGE]
    assert proto["wopen"] == OTHER
    # заголовок — как при открытии окна «Seitentitel» (сохранённого своего заголовка нет)
    assert proto["title"] == [True, {}]
    assert proto.get("settings") or proto.get("codes")


def test_two_snapshots_without_token_untouched():
    """Без токена выбрать окно нечем: оба снимка остаются как были (и с пустым `wopen` у
    обоих: `"" == ""` — не совпадение токена)."""
    b = _two_windows()
    window = b.session[aufbau_draft.SESSION_KEY][CODE][aufbau_draft.WINDOW_KEY]
    window[PAGE]["wopen"] = ""
    window[TITLE]["wopen"] = ""
    b.session.modified = True
    before = copy.deepcopy(window)
    b.get(f"?seite={CODE}")
    assert _drafts(b)[CODE][aufbau_draft.WINDOW_KEY] == before


def test_two_snapshots_foreign_token_untouched():
    b = _two_windows()
    before = copy.deepcopy(_drafts(b)[CODE][aufbau_draft.WINDOW_KEY])
    b.get(f"?seite={CODE}&block={PAGE}&wopen=openRvZ")
    assert _drafts(b)[CODE][aufbau_draft.WINDOW_KEY] == before


def test_two_snapshots_merge_logged(caplog):
    b = _two_windows()
    with caplog.at_level(logging.INFO, logger=LOGGER):
        b.get(f"?seite={CODE}&block={PAGE}&wopen={OTHER}")
    said = " | ".join(r.getMessage() for r in caplog.records if r.name == LOGGER)
    assert "merged" in said and "title" in said, said


def test_btr_merged_by_language_conflict_logged(caplog):
    """Переводы под `__title` и `__page` у одного черновика: сливаются по языкам; ключ,
    который есть в обоих с разным текстом, — остаётся у `__page`, отброшенное — в лог."""
    b = _two_windows()
    draft = b.session[aufbau_draft.SESSION_KEY][CODE]
    draft["btr"][PAGE] = {"ru": {"title": "Акции"}, "en": {"title": "Offers"}}
    draft["btr"][TITLE]["ru"] = {"intro": "Текст"}
    draft["btr_base"][PAGE] = draft["btr_base"][TITLE]
    b.session.modified = True
    with caplog.at_level(logging.INFO, logger=LOGGER):
        b.get(f"?seite={CODE}")
    btr = _drafts(b)[CODE]["btr"]
    assert set(btr) == {PAGE}
    assert btr[PAGE] == {"ru": {"title": "Акции", "intro": "Текст"}, "en": {"title": "Offers"}}
    said = " | ".join(r.getMessage() for r in caplog.records if r.name == LOGGER)
    assert "dropped" in said and "btr.en.title" in said, said


# ───────────── 2. снимок `__page` до деплоя — без заголовка ─────────────


def test_page_snapshot_before_deploy_gets_title_on_first_title_edit():
    tenant = _shop()
    b = Browser(tenant)
    setting, value = _free_setting(b, CODE)
    b.post(seite=CODE, ref=PAGE, op="setting", setting=setting, value=value, wopen=OTHER)
    draft = b.session[aufbau_draft.SESSION_KEY][CODE]
    draft[aufbau_draft.WINDOW_KEY][PAGE].pop("title")  # окно открыто до деплоя
    b.session.modified = True
    # после деплоя окно перерисовано с полями заголовка — тот же токен
    b.post(seite=CODE, ref=PAGE, op="update", panel_present="1", wopen=OTHER, f_title="Neu")
    assert _drafts(b)[CODE]["title"] == {"title": "Neu"}
    assert _drafts(b)[CODE][aufbau_draft.WINDOW_KEY][PAGE]["title"] == [True, {}]
    _resp, msgs = b.post(seite=CODE, ref=PAGE, op="revert", wopen=OTHER)
    assert "Änderungen an diesem Block zurückgenommen." in msgs
    assert _drafts(b) == {}, "и настройка, и заголовок — как при открытии"


def test_page_snapshot_before_deploy_without_title_edit_keeps_title():
    """Заголовок правили в другом окне (не в этом): «Abbrechen» этого окна его не трогает."""
    tenant = _shop()
    b = Browser(tenant)
    setting, value = _free_setting(b, CODE)
    b.post(seite=CODE, ref=PAGE, op="setting", setting=setting, value=value, wopen=OTHER)
    draft = b.session[aufbau_draft.SESSION_KEY][CODE]
    draft[aufbau_draft.WINDOW_KEY][PAGE].pop("title")
    draft["title"] = {"title": "Anderswo"}
    b.session.modified = True
    _resp, msgs = b.post(seite=CODE, ref=PAGE, op="revert", wopen=OTHER)
    assert "Änderungen an diesem Block zurückgenommen." in msgs
    left = _drafts(b)[CODE]
    assert left["title"] == {"title": "Anderswo"} and not left.get("settings")


# ───────────── 7. повреждённый снимок ─────────────


@pytest.mark.parametrize("with_page", (True, False))
def test_broken_legacy_snapshot_dropped_with_warning(caplog, with_page):
    b = _two_windows()
    window = b.session[aufbau_draft.SESSION_KEY][CODE][aufbau_draft.WINDOW_KEY]
    window[TITLE] = "kaputt"
    if not with_page:
        window.pop(PAGE)
    b.session.modified = True
    with caplog.at_level(logging.INFO, logger=LOGGER):
        b.get(f"?seite={CODE}&block={PAGE}&wopen={WOPEN}")
    window = _drafts(b)[CODE].get(aufbau_draft.WINDOW_KEY) or {}
    assert TITLE not in window and window.get(PAGE, {}) != "kaputt"
    assert any(r.levelno == logging.WARNING and TITLE in r.getMessage() for r in caplog.records)


# ───────────── 3. метка заголовка и ряд узких блоков ─────────────


def _hint_after(blocks, at):
    from apps.core.site_schema_views import _title_hint

    layout = site_schema.schema_layout(blocks)
    hint = _title_hint(layout, blocks, at, "message")
    return hint and hint["after"]


def _b(ref, width=""):
    return {"ref": ref, "key": ref, "enabled": True, "width": width}


def test_hint_before_row_that_straddles_the_title():
    # ряд [a ½, b ½]: a над заголовком, b под ним — метка перед рядом (перед первым: -1)
    assert _hint_after([_b("a", "w12"), _b("b", "w12"), _b("c")], 1) == -1
    # ряд целиком над заголовком — после него
    assert _hint_after([_b("a", "w12"), _b("b", "w12"), _b("c")], 2) == 0
    # второй ряд разрезан точкой заголовка — метка после первого ряда (перед вторым)
    assert _hint_after([_b("x"), _b("a", "w12"), _b("b", "w12")], 2) == 0
    assert _hint_after([_b("x"), _b("a", "w12"), _b("b", "w12"), _b("y")], 3) == 1


def test_hint_before_first_row_in_markup(monkeypatch):
    """Фото-шапка ½ и соседний блок ½ в одном ряду (заголовок — под шапкой): метка — перед
    рядом, не после него. Сохранённое состояние ширину шапке списка не даёт (normalize) —
    ряд собран подменой строк схемы: замок разметки, а не данных."""
    real = site_schema.blocks_for

    def narrow(config, code, *args, **kwargs):
        blocks = real(config, code, *args, **kwargs)
        if code == "services":
            for b in blocks[:2]:
                b["width"] = "w12"
        return blocks

    monkeypatch.setattr(site_schema, "blocks_for", narrow)
    tenant = _tenant()
    saved = siteconfig.normalize(tenant.site_config)
    blocks = site_schema.blocks_for(saved, "services", tenant=None)
    layout = site_schema.schema_layout(blocks)
    row = [b["ref"] for b in layout["lines"][0]["blocks"]]
    assert row == ["page_head", "groups"], row
    assert site_schema.title_hint_at("services", blocks) == 1
    html = Browser(tenant).get("?seite=services")
    cols = html[html.index("data-schema-blocks") :]
    assert cols.count("data-schema-title-hint") == 1
    assert cols.index("data-schema-title-hint") < cols.index('data-schema-block="page_head"')


# ───────────── 4. ссылка «Wie auf der Seite …» без строки ─────────────


def test_list_view_link_not_built_without_row(monkeypatch):
    tenant = _shop()
    saved = siteconfig.normalize(tenant.site_config)
    selected = next(
        b for b in site_schema.blocks_for(saved, "home", tenant=None) if b["ref"] == "l1"
    )
    view = block_views.list_view(saved, selected)
    assert view["inherits"] and "block=__page" in view["link"], view
    monkeypatch.setattr(site_schema, "page_row_ref", lambda tenant, code, blocks=None: "")
    view = block_views.list_view(saved, selected)
    assert view["link"] == "", view


def test_settings_url_never_has_empty_block():
    """`settings_url` — по правилу с `tenant=None`: у любого известного типа строка есть
    (пусто — только у неизвестного кода, тогда адрес — экран без блока)."""
    from apps.core import studio_pages

    for pt in studio_pages.PAGE_TYPES:
        url = site_schema.settings_url(pt.code)
        assert "block=&" not in url and not url.endswith("block="), (pt.code, url)


# ───────────── 5. ссылка на форму категории ─────────────


@pytest.mark.parametrize("bt", ("online_shop", "restaurant", "baeckerei"))
def test_category_always_has_page_row_and_seo_link(bt):
    from apps.catalog.models import Category

    Category.objects.create(name={"de": "Brot"}, slug="brot")
    tenant = _tenant(bt)
    code = "category@catalog:brot"
    assert site_schema.page_row_ref(tenant, code) == PAGE, bt
    cfg = siteconfig.normalize(tenant.site_config)
    row = page_window.pseudo_row(PAGE, PAGE, "catalog:brot", cfg)
    page_window.decorate(row, cfg, "catalog:brot", code)
    assert row.get("seo_link", {}).get("url"), bt


# ───────────── 6. «Darstellung der Liste» у ★-строки ─────────────


@pytest.mark.parametrize("bt", ("online_shop", "events", "tour_operator", "friseur"))
def test_list_link_on_page_row_for_every_own_view(bt):
    """`mainview`/`groupview` строки ★ заполняет `blocks_for` — до `list_links`; ссылка у
    ★-строки есть у каждого списка со своим видом (каталог, категория, акции, туры, …)."""
    tenant = _tenant(bt, CFG if bt == "online_shop" else None)
    saved = siteconfig.normalize(tenant.site_config)
    rows = [r for _l, items in site_schema.type_groups(tenant, saved) for r in items]
    seen = []
    for row in rows:
        blocks = site_schema.blocks_for(saved, row.code, host=row.host, tenant=None)
        main = next((b for b in blocks if b.get("main") and not b.get("cblock")), None)
        if not page_window.main_has_view(main):
            continue
        if site_schema.page_row_ref(tenant, row.code, blocks) != PAGE:
            continue
        seen.append(row.code)
        panel = _panel(Browser(tenant).get(f"?seite={row.code}&block={PAGE}"))
        assert "data-schema-list-link" in panel, (bt, row.code)
    if bt != "friseur":
        assert seen, bt
