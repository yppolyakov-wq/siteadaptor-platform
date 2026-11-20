"""FB-33 M3-3d «Von einer Seite ↔ Eigener Text»: смена вида внутри семьи текстовых блоков
(text, image_text ↔ textpage). Решение владельца (п. 3 плана M3): оба источника помнятся,
на сайте — только активный. Один список «поля пары, которые хранятся неактивными» —
`block_catalog.INACTIVE_FIELDS`; чистильщик, Студия и сводка строки читают его.

Замки C0 (до кода): туда-обратно байт-в-байт (тексты, фото, страница, перевод), рендер,
сводка, факты ИИ и поиск видят только активный вид, нормализация идемпотентна, старая
форма Студии не откатывает запомненное, «Abbrechen» окна — байт-в-байт, чужие значения
отброшены."""

import copy
import json
import uuid
from pathlib import Path

import pytest
from django.template import Context, Template
from django.test import RequestFactory

from apps.core import aufbau_draft, block_catalog, site_schema
from apps.core.models import ContentPage
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window import _shop
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

PAGE = str(uuid.uuid4())
TEXT = {
    "title": "Über uns",
    "body": "Seit 1998 backen wir.",
    "align": "center",
    "size": "lg",
    "color": "accent",
    "url": "/m/a.jpg",
    "side": "right",
    "rounded": "3xl",
}


def _clean(key, data):
    return siteconfig._clean_cblock_data(key, data)


def _dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _items(key, data):
    return [{"key": key, "id": "b1", "enabled": True, "width": "w6", "data": _clean(key, data)}]


def _switch(items, *keys):
    for key in keys:
        site_schema.mutate(items, "catalog", "switch", ref="b1", value=key)
        # то, что ляжет в базу, — через нормализатор (идемпотентно)
        items[0]["data"] = _clean(items[0]["key"], items[0]["data"])
    return items


# ───────────── один список и функция данных плашки ─────────────


def test_switch_keeps_both_only_for_the_text_source_pairs():
    assert block_catalog.switch_keeps_both("text", "textpage")
    assert block_catalog.switch_keeps_both("textpage", "image_text")
    assert not block_catalog.switch_keeps_both("text", "image_text")
    assert not block_catalog.switch_keeps_both("text", "text")
    assert not block_catalog.switch_keeps_both("button", "textpage")


def test_text_views_switch_to_von_einer_seite_and_back():
    assert {k for k, _ in block_catalog.switch_options("text")} == {
        "text",
        "image_text",
        "textpage",
    }
    assert {k for k, _ in block_catalog.switch_options("textpage")} == {
        "text",
        "image_text",
        "textpage",
    }
    assert block_catalog.can_switch("textpage", "text")


def test_one_list_of_inactive_fields():
    fields = block_catalog.INACTIVE_FIELDS
    assert set(fields["text"]) >= {"page", "mode"}
    assert set(fields["image_text"]) == {"page", "mode"}
    assert set(fields["textpage"]) == {
        "title",
        "body",
        "align",
        "size",
        "color",
        "url",
        "side",
        "rounded",
    }
    # каждое неактивное поле — своё поле партнёра по смене вида (не выдумано)
    own = {
        "text": _clean("text", TEXT),
        "image_text": _clean("image_text", TEXT),
        "textpage": _clean("textpage", {"page": PAGE, "mode": "teaser"}),
    }
    for key, names in fields.items():
        partners = set().union(
            *(set(own[p]) for p in own if p != key and block_catalog.can_switch(key, p))
        )
        assert set(names) <= partners, (key, set(names) - partners)


# ───────────── туда-обратно ─────────────


def test_text_to_textpage_and_back_is_byte_for_byte():
    items = _items("text", TEXT)
    before = _dump(items)
    _switch(items, "textpage")
    assert items[0]["key"] == "textpage" and items[0]["width"] == "w6"
    _switch(items, "text")
    assert _dump(items) == before


def test_image_text_to_textpage_and_back_is_byte_for_byte():
    items = _items("image_text", {**TEXT, "side": "left", "body": ""})
    before = _dump(items)
    _switch(items, "textpage", "image_text")
    assert _dump(items) == before


def test_textpage_to_text_and_back_keeps_page_and_mode():
    pk = str(_page().pk)  # страница есть — смена вида её не снимает
    items = _items("textpage", {"page": pk, "mode": "teaser"})
    before = _dump(items)
    _switch(items, "text")
    assert items[0]["data"]["page"] == pk and items[0]["data"]["mode"] == "teaser"
    _switch(items, "textpage")
    assert _dump(items) == before
    # через «Foto + Text» (без фото: сторона по умолчанию не запоминается)
    _switch(items, "image_text", "text", "textpage")
    assert _dump(items) == before


def test_own_text_typed_on_text_survives_a_trip_through_textpage():
    """Текст, набранный во вкладке «Texte» у «Eigener Text», не теряется на «Von einer
    Seite» и обратно, и выбранная страница — тоже."""
    pk = str(_page().pk)
    items = _items("textpage", {"page": pk})
    _switch(items, "text")
    items[0]["data"].update(title="Neu", body="Mein Text")
    _switch(items, "textpage")
    assert items[0]["data"]["page"] == pk
    _switch(items, "text")
    assert items[0]["data"]["title"] == "Neu" and items[0]["data"]["body"] == "Mein Text"


def test_normalisation_is_idempotent():
    for key in ("text", "image_text", "textpage"):
        for data in (TEXT, {"page": PAGE, "mode": "teaser"}, {**TEXT, "page": PAGE}, {}):
            once = _clean(key, data)
            assert _clean(key, once) == once, (key, data)


def test_foreign_values_are_dropped():
    junk = {
        "page": "nicht-uuid",
        "mode": "full",
        "side": "top",
        "rounded": "huge",
        "align": "left",
        "size": "xxl",
        "color": "#f00",
        "title": 5,
        "caption": "fremd",
        "label": "fremd",
    }
    assert _clean("textpage", junk) == {}
    assert _clean("text", junk) == {"title": "", "body": ""}
    assert "page" not in _clean("image_text", junk) and "mode" not in _clean("image_text", junk)
    # фото без адреса у «Nur Text» не помнится (M2e) — и через «Von einer Seite» тоже
    assert _clean("text", _clean("textpage", {"side": "right"})) == {"title": "", "body": ""}


# ───────────── переводы ─────────────


def test_translation_overlay_survives_text_textpage_text():
    cfg = siteconfig.normalize({"page_blocks": {"catalog": _items("text", TEXT)}})
    siteconfig.set_overlay_value(cfg, "ru", ("page_blocks", "catalog", 0, "data", "title"), "О нас")
    cfg = siteconfig.normalize(cfg)
    before = _dump(cfg)
    for key in ("textpage", "text"):
        site_schema.mutate(cfg["page_blocks"]["catalog"], "catalog", "switch", ref="b1", value=key)
        cfg = siteconfig.normalize(cfg)
    assert _dump(cfg) == before
    assert siteconfig.localize(cfg, "ru")["page_blocks"]["catalog"][0]["data"]["title"] == "О нас"


def test_page_and_mode_are_not_translatable():
    assert not siteconfig._is_translatable_field("page")
    assert not siteconfig._is_translatable_field("mode")


# ───────────── только активный вид ─────────────


def _render(tenant, block):
    request = RequestFactory().get("/")
    request.tenant = tenant
    tpl = Template("{% load siteui %}{% render_block block %}")
    return tpl.render(Context({"request": request, "block": block, "pb_host": "catalog"}))


def test_site_renders_only_the_active_source(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _shop()
    page = ContentPage.objects.create(
        slug="geschichte", title="Unsere Geschichte", body="<p>SEITENTEXT</p>"
    )
    remembered = {**TEXT, "title": "EIGENER-TITEL", "body": "EIGENER-TEXT"}
    as_textpage = _clean("textpage", {**remembered, "page": str(page.pk)})
    html = _render(tenant, {"key": "textpage", "id": "b1", "data": as_textpage})
    assert "SEITENTEXT" in html and "Unsere Geschichte" in html
    assert "EIGENER" not in html and "/m/a.jpg" not in html
    as_text = _clean("text", {**remembered, "page": str(page.pk)})
    html = _render(tenant, {"key": "text", "id": "b1", "data": as_text})
    assert "EIGENER-TITEL" in html and "SEITENTEXT" not in html and "Geschichte" not in html
    as_image_text = _clean("image_text", {**remembered, "page": str(page.pk)})
    html = _render(tenant, {"key": "image_text", "id": "b1", "data": as_image_text})
    assert "EIGENER-TITEL" in html and "SEITENTEXT" not in html


def test_template_context_gets_only_active_fields():
    data = _clean("textpage", {**TEXT, "page": PAGE})
    assert block_catalog.active_data("textpage", data) == {"page": PAGE}
    text = _clean("text", {**TEXT, "page": PAGE, "mode": "teaser"})
    assert "page" not in block_catalog.active_data("text", text)
    assert block_catalog.active_data("button", {"label": "x"}) == {"label": "x"}


def test_row_summary_does_not_show_the_remembered_title():
    """У «Von einer Seite» без страницы сводка строки не показывает запомненный свой
    заголовок (он не на сайте)."""
    item = {"key": "textpage", "id": "b1", "data": _clean("textpage", TEXT)}
    assert "Über uns" not in site_schema._row_summary({}, item)
    item = {"key": "text", "id": "b1", "data": _clean("text", {**TEXT, "page": PAGE})}
    assert "Über uns" in site_schema._row_summary({}, item)


def test_search_seo_and_text_facts_do_not_read_block_data():
    """Поиск портала, SEO и факты ИИ блоки страниц не читают вовсе. Начнут — только через
    `block_catalog.active_data` (иначе в выдачу попал бы текст, которого нет на сайте)."""
    root = Path(__file__).resolve().parents[2]
    files = [root / "core" / "seo.py", root / "core" / "text_facts.py"]
    files += [p for p in (root / "aggregator").rglob("*.py") if "tests" not in p.parts]
    for path in files:
        src = path.read_text(encoding="utf-8")
        if "page_blocks" in src or "_clean_cblock_data" in src:
            assert "active_data" in src, path


def test_cscart_cleanup_compares_only_own_text_blocks():
    from apps.imports import cscart

    legacy = "Alter Text"
    remembered = {"key": "textpage", "id": "b1", "data": _clean("textpage", {"body": legacy})}
    own = {"key": "text", "id": "b2", "data": _clean("text", {"body": legacy})}
    assert not cscart._is_legacy_text_block(remembered, legacy)
    assert cscart._is_legacy_text_block(own, legacy)


def test_demo_translation_of_block_data_ignores_page_and_mode():
    """Перевод демо-данных блока берёт текстовые поля любого блока (и запомненные — их
    увидят, если владелец вернёт вид); адрес страницы и режим не переводятся."""
    from apps.tenants import demo_i18n

    out = demo_i18n._tr_cblock_data({"page": PAGE, "mode": "teaser", "title": "x"}, "en") or {}
    assert "page" not in out and "mode" not in out


# ───────────── писатели data целиком ─────────────


def test_studio_save_keeps_the_remembered_fields():
    saved = [{"key": "textpage", "id": "b1", "data": _clean("textpage", {**TEXT, "page": PAGE})}]
    posted = [{"key": "textpage", "id": "b1", "data": {"page": PAGE, "mode": ""}}]
    for keep in (False, True):
        merged = site_schema.merge_structure(saved, posted, keep_data=keep)[0]["data"]
        assert _clean("textpage", merged) == saved[0]["data"], keep
    saved = [{"key": "text", "id": "b1", "data": _clean("text", {**TEXT, "page": PAGE})}]
    posted = [{"key": "text", "id": "b1", "data": {"title": "Neu", "body": "B"}}]
    merged = _clean("text", site_schema.merge_structure(saved, posted)[0]["data"])
    assert merged["title"] == "Neu" and merged["page"] == PAGE and merged["url"] == "/m/a.jpg"


def test_studio_form_cannot_plant_inactive_fields():
    """Форма Студии неактивных полей не несёт — присланные отбрасываются (их пишет только
    смена вида)."""
    saved = [{"key": "text", "id": "b1", "data": {"title": "T", "body": "B"}}]
    posted = [{"key": "text", "id": "b1", "data": {"title": "T", "body": "B", "page": PAGE}}]
    assert "page" not in site_schema.merge_structure(saved, posted)[0]["data"]


def test_stale_studio_form_of_the_other_view_does_not_roll_back():
    """Вкладка Студии открыта, пока блок был «Eigener Text»; в «Seitenaufbau» его сменили
    на «Von einer Seite» — её «Speichern» вид и данные не откатывает."""
    saved = [{"key": "textpage", "id": "b1", "data": _clean("textpage", {**TEXT, "page": PAGE})}]
    posted = [{"key": "text", "id": "b1", "data": {"title": "Alt", "body": "Alt"}}]
    for keep in (False, True):
        assert site_schema.merge_structure(saved, posted, keep_data=keep) == saved


def test_panel_edit_of_the_active_view_keeps_the_other():
    items = _items("text", {**TEXT, "page": PAGE})
    site_schema.mutate(items, "catalog", "update", ref="b1", fields={"title": "Neu", "body": "B"})
    assert items[0]["data"]["page"] == PAGE and items[0]["data"]["title"] == "Neu"


# ───────────── окно: «Abbrechen» ─────────────


def _drafts(b):
    return copy.deepcopy((b.session or {}).get(aufbau_draft.SESSION_KEY) or {})


def test_cancel_after_switching_returns_key_and_data_byte_for_byte():
    b = Browser(_shop())
    b.get("?seite=home&block=t1")
    b.post(seite="home", ref="t1", wopen="openT1", op="switch", value="textpage")
    item = next(i for i in _drafts(b)["home"]["items"] if i.get("id") == "t1")
    assert item["key"] == "textpage" and item["data"]["title"] == "Hallo"
    b.post(seite="home", ref="t1", wopen="openT1", op="revert")
    assert _drafts(b) == {}


# ───────────── ревью ECC (security-reviewer, silent-failure-hunter) ─────────────


def _page(slug="geschichte", **kw):
    return ContentPage.objects.create(slug=slug, title="Geschichte", body="<p>x</p>", **kw)


def test_switch_to_textpage_drops_a_gone_page_with_a_note():
    items = _items("text", {**TEXT, "page": PAGE})  # такой страницы нет
    notes = []
    site_schema.mutate(items, "text", "switch", ref="b1", value="textpage", notes=notes)
    assert "page" not in items[0]["data"] and items[0]["data"]["title"] == TEXT["title"]
    assert notes == [site_schema.textpage_page_note()]


def test_switch_to_textpage_drops_the_page_it_stands_on():
    page = _page()
    items = _items("text", {**TEXT, "page": str(page.pk)})
    notes = []
    code = f"text@seite:{page.slug}"
    site_schema.mutate(items, code, "switch", ref="b1", value="textpage", notes=notes)
    assert "page" not in items[0]["data"] and notes


def test_switch_keeps_an_existing_page_silently():
    page = _page()
    items = _items("text", {**TEXT, "page": str(page.pk)})
    notes = []
    site_schema.mutate(items, "catalog", "switch", ref="b1", value="textpage", notes=notes)
    assert items[0]["data"]["page"] == str(page.pk) and notes == []


def test_side_and_rounded_are_not_translatable():
    assert not siteconfig._is_translatable_field("side")
    assert not siteconfig._is_translatable_field("rounded")


def test_paid_translation_paths_do_not_read_block_data():
    """Платный машинный и ручной перевод блоки страниц не собирают — запомненный текст не
    уходит в перевод. Начнут — только через `block_catalog.active_data`."""
    root = Path(__file__).resolve().parents[2]
    for name in ("i18n_translate.py", "translate_views.py", "text_draft.py", "i18n_cabinet.py"):
        src = (root / "core" / name).read_text(encoding="utf-8")
        if "page_blocks" in src or "_clean_cblock_data" in src:
            assert "active_data" in src, name


def test_demo_translation_also_covers_remembered_texts():
    """Зафиксировано (ревью): словарный перевод демо (бесплатный, без ИИ) берёт текстовые
    поля любого блока — и запомненные у «Von einer Seite»: вернув вид, владелец увидит
    перевод. Демо-киты запомненных полей не сеют."""
    from apps.tenants import demo_i18n

    fields = set(demo_i18n._CBLOCK_TEXT_FIELDS)
    assert {"title", "body"} <= fields and not fields & {"page", "mode", "side", "rounded"}


def test_block_template_keeps_only_the_active_view():
    tpls = siteconfig.normalize_block_templates(
        {
            "a": {"key": "textpage", "data": {**TEXT, "page": PAGE}},
            "b": {"key": "text", "data": {**TEXT, "page": PAGE}},
        }
    )
    assert tpls["a"]["data"] == {"page": PAGE}
    assert "page" not in tpls["b"]["data"] and "url" not in tpls["b"]["data"]
    assert tpls["b"]["data"]["title"] == TEXT["title"]


def test_template_insert_checks_the_page():
    tpls = siteconfig.normalize_block_templates({"a": {"key": "textpage", "data": {"page": PAGE}}})
    items, notes = [], []
    ref = site_schema.mutate(items, "text", "add", block_type="tpl:a", templates=tpls, notes=notes)
    assert ref and "page" not in items[0]["data"] and notes


def test_texts_are_capped_on_input_not_on_normalisation():
    long_title = "T" * 300
    # сохранённое раньше нормализация не режет (витрина прежняя, круг байт-в-байт)
    assert _clean("text", {"title": long_title})["title"] == long_title
    assert _clean("textpage", {"title": long_title})["title"] == long_title
    items, notes = _items("text", {"title": "x"}), []
    site_schema.mutate(
        items, "catalog", "update", ref="b1", fields={"title": long_title}, notes=notes
    )
    cap = siteconfig.CBLOCK_TEXT_CAPS["title"]
    assert items[0]["data"]["title"] == "T" * cap and notes == [siteconfig.cap_note()]


def test_studio_form_caps_texts_with_a_note():
    from django.http import QueryDict

    from apps.core import views

    post = QueryDict(mutable=True)
    post.update({"cb_b1_title": "T" * 300, "cb_b1_body": "B" * 25_000, "cb_b1_url": "/x"})
    notes = []
    data = views._read_cblock_data(post, "b1", "image_text", notes)
    assert len(data["title"]) == 200 and len(data["body"]) == 20_000 and notes


def test_inactive_fields_match_what_the_cleaner_keeps():
    """Один источник: ключи `INACTIVE_FIELDS[k]` — ровно то, что чистильщик `k` хранит
    сверх своих полей (дрейф трёх мест ловит этот тест)."""
    full = {**TEXT, "page": PAGE, "mode": "teaser"}
    own = {
        "text": {"title", "body", "align", "size", "color"},
        "image_text": {"url", "title", "body", "side", "align", "size", "color", "rounded"},
        "textpage": {"page", "mode"},
    }
    for key, names in block_catalog.INACTIVE_FIELDS.items():
        assert set(_clean(key, full)) - own[key] == set(names), key


def test_render_uses_the_canonical_key(monkeypatch):
    seen = []
    real = block_catalog.active_data
    monkeypatch.setattr(block_catalog, "active_data", lambda k, d: seen.append(k) or real(k, d))
    from apps.tenants.templatetags import siteui

    # старые блоки нормализация переименовывает; партиал легаси-ключа — для проверки
    monkeypatch.setitem(
        siteui.CBLOCK_TEMPLATES, "promo_list", "storefront/sections/_block_text.html"
    )
    ctx = Context({"request": RequestFactory().get("/")})
    siteui.render_block(ctx, {"key": "promo_list", "id": "x", "data": {}})
    assert seen == ["list"]


def test_image_text_without_photo_keeps_its_side_through_textpage():
    items = _items("image_text", {"title": "T", "side": "right"})
    before = _dump(items)
    _switch(items, "textpage", "image_text")
    assert _dump(items) == before


def test_studio_changed_page_is_checked():
    saved = {"info": [{"key": "textpage", "id": "b1", "data": {}}]}
    merged = {"info": [{"key": "textpage", "id": "b1", "data": {"page": PAGE}}]}
    notes = []
    site_schema.check_changed_pages(saved, merged, notes)
    assert merged["info"][0]["data"] == {} and notes
    page = _page()
    merged = {"info": [{"key": "textpage", "id": "b1", "data": {"page": str(page.pk)}}]}
    site_schema.check_changed_pages(saved, merged, notes := [])
    assert merged["info"][0]["data"]["page"] == str(page.pk) and notes == []


def test_saving_the_draft_keeps_both_sources():
    """«Speichern» черновика (aufbau_draft.commit) пишет блок с обоими источниками."""
    from apps.tenants.models import Tenant

    tenant = _shop()
    b = Browser(tenant)
    b.post(seite="home", ref="t1", op="switch", value="textpage")
    b.post(seite="home", op="save")
    rows = Tenant.objects.get(pk=tenant.pk).site_config["sections"]
    row = next(r for r in rows if r.get("id") == "t1")
    assert row["key"] == "textpage" and row["data"]["title"] == "Hallo"
    b.post(seite="home", ref="t1", op="switch", value="text")
    b.post(seite="home", op="save")
    rows = Tenant.objects.get(pk=tenant.pk).site_config["sections"]
    row = next(r for r in rows if r.get("id") == "t1")
    assert row["key"] == "text" and row["data"] == {"title": "Hallo", "body": "Welt"}
