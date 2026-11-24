"""FB-33 M5d-4a (G1a стопки 12): окно «Inhalt» у разделов страницы товара.

План — `docs/fb33-stack12-plan-2026-11-23.md` §0 «M5dG1» (тексты), §3 (карта источников), §4
«G1a…e», правки ревью §10 (A1, A7, A8, A10, Y8), ответы владельца §11 (список товаров — запись
«Sortiment»). Срез правит только реестр `detail_sections.DETAIL_SECTIONS["catalog"]`: у разделов
description, info, sizes, anprobe, waitlist, instore, question, recent появляется источник
(`ContentSource`), у «Ähnliche Produkte» — только на строке одного товара (`object_only`). `trust`
и `reviews` остаются со своим окном. Витрина не меняется: шаблоны и вьюхи витрины не тронуты.

Общие помощники замков среза (их же берут G1b и G1c) — здесь.
"""

import dataclasses
import re
import uuid
from pathlib import Path

import polib
import pytest
from django.db import connection
from django.urls import reverse
from django.utils import translation

from apps.catalog.models import Category, Product
from apps.core import block_window, detail_sections, nav_registry, object_structure, window_parts
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import _capture, _panel
from apps.core.tests.test_fb33_m5d1_inhalt import HINT, _inventory
from apps.core.tests.test_fb33_m5d2_core import (
    ACT_HIDE,
    ACT_HIDE_MOVE,
    EMPTY,
    FILLED,
    LMIV,
    ONLY_IF_FILLED,
    _inhalt,
    _req,
    _text,
    _warm_count,
)
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
LANGS = ("de", "en", "tr", "ru", "uk")
AUTO_BROWSER = "automatisch — im Browser des Besuchers. Nichts zu pflegen."

#: раздел → (вид источника, экран ссылки, «Dieser Block zeigt», «Woher» строки типа)
EXPECT = {
    "description": (
        "field",
        "sellable-manage",
        "die Beschreibung des Produkts",
        f"Feld „Beschreibung“ bei jedem Produkt. {ONLY_IF_FILLED}",
    ),
    "info": (
        "field",
        "sellable-manage",
        "die Kennzeichnung des Produkts: Marke, Zustand, Material, Pflege, Herkunft, Zutaten, "
        "Allergene und Zusatzstoffe",
        # FB-33 M5d-8 (E7): «Woher» — списком полей; здесь вводная фраза, список — замки
        # `test_fb33_e7_woher_list.py`
        "Diese Felder bei jedem Produkt:",
    ),
    "sizes": (
        "setting",
        "catalog:category-list",
        "die Größentabelle der Kategorie, zu der das Produkt gehört",
        "Feld „Größentabelle“ bei der Kategorie. "
        "Erscheint nur, wenn die Kategorie eine Größentabelle hat.",
    ),
    "anprobe": (
        "auto",
        "",
        "das Formular „In der Anprobe zurücklegen“ — unverbindlich reservieren, 48 Stunden",
        "automatisch — aus Bestand und Größen des Produkts. Nichts zu pflegen. "
        "Erscheint nur, wenn die Anprobe-Reservierung eingeschaltet, die Online-Bestellung aktiv "
        "und das Produkt vorrätig ist.",
    ),
    "waitlist": (
        "auto",
        "",
        "das Formular „Ausverkauft? Benachrichtigen lassen“ — eine E-Mail, sobald das Produkt "
        "wieder da ist",
        "automatisch — aus dem Bestand des Produkts. Nichts zu pflegen. "
        "Erscheint nur, wenn das Produkt oder eine Größe ausverkauft ist.",
    ),
    "instore": (
        "setting",
        "settings",
        "den Hinweis „Im Laden erhältlich“ mit Öffnungszeiten und Adresse",
        "Ihre Geschäftsdaten (Adresse, Öffnungszeiten).",
    ),
    "question": (
        "auto",
        "",
        "den Link zum Nachrichtenformular — mit dem Namen des Produkts",
        "automatisch — die Frage kommt in „Nachrichten“ an. Nichts zu pflegen. "
        "Erscheint nur, wenn das Modul „Nachrichten“ aktiv ist.",
    ),
    "recent": (
        "auto",
        "",
        "die Produkte, die sich der Besucher zuletzt angesehen hat",
        f"{AUTO_BROWSER} Erscheint nur, wenn der Besucher schon andere Produkte angesehen hat.",
    ),
}
#: «Ähnliche Produkte» — источник только у строки одного товара (A1)
RELATED = (
    "weitere Produkte derselben Kategorie — empfohlene zuerst",
    "automatisch — aus der Kategorie des Produkts. Nichts zu pflegen. "
    "Erscheint nur, wenn die Kategorie weitere aktive Produkte hat.",
)
#: со своим окном — источника нет и не будет
OWN_WINDOW = ("trust", "reviews")
#: A7б: разделы, которые страница показывает не всегда (гейты `product_detail.html` и вьюхи):
#: у каждого — «Erscheint nur, wenn …». «Im Geschäft erhältlich» гейта не имеет.
GATED = ("description", "info", "sizes", "anprobe", "waitlist", "question", "related", "recent")
#: подписи экранов ссылки (записи `nav_registry`, de)
SCREENS = {
    "sellable-manage": "Sortiment",
    "catalog:category-list": "Kategorien",
    "settings": "Mein Geschäft",
}


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    from apps.core import page_settings

    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr(page_settings, "_storefront_shows", lambda tenant, code: True)
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def tenant_of(business_type):
    tenant = TenantFactory(
        business_type=business_type, disabled_modules=list(default_disabled_for(business_type))
    )
    connection.tenant = tenant
    return tenant


def _shop(bt="online_shop", **fields):
    tenant = tenant_of(bt)
    category = Category.objects.create(
        name={"de": "Tee", "en": ""}, slug=f"tee-{uuid.uuid4().hex[:8]}"
    )
    product = Product.objects.create(
        name={"de": "Darjeeling", "en": ""},
        base_price="9.90",
        category=category,
        **{"description": {"de": "Fein", "en": ""}, **fields},
    )
    return tenant, product


def section(module, key):
    return next(s for s in detail_sections.sections_for(module) if s.key == key)


def sources(module) -> dict:
    return {s.key: s.source for s in detail_sections.sections_for(module) if s.source}


def source_msgids(module, keys) -> list[str]:
    """msgid всех текстов источников раздела (без общих строк ядра — они в замке P0)."""
    out = []
    with translation.override(None):
        for key in keys:
            src = section(module, key).source
            for text in (src.shows, src.woher, src.note, src.only_if):
                if text and str(text) != ONLY_IF_FILLED:
                    out.append(str(text))
    return out


def assert_msgids_in_all_po(msgids):
    """№16: строки среза — во всех пяти каталогах, без дублей пары (msgctxt, msgid), с
    переводом (de — пусто или сам msgid), плейсхолдеры целы."""
    assert msgids and len(msgids) == len(set(msgids))
    for lang in LANGS:
        po = polib.pofile(str(ROOT / f"locale/{lang}/LC_MESSAGES/django.po"))
        entries = [e for e in po if not e.obsolete]
        pairs = [(e.msgctxt, e.msgid) for e in entries]
        assert len(pairs) == len(set(pairs)), lang
        have = {(e.msgctxt, e.msgid): e for e in entries}
        for msgid in msgids:
            entry = have.get((None, msgid))
            assert entry is not None, (lang, msgid)
            assert "fuzzy" not in entry.flags, (lang, msgid)
            if lang == "de":
                assert entry.msgstr in ("", msgid), (lang, msgid)
            else:
                assert entry.msgstr and entry.msgstr != msgid, (lang, msgid)


def bare_rows(tenant, monkeypatch, wanted) -> tuple[list, set]:
    """Логика `scripts/fb33_m5d_inventory.py` (ответ — разметка вьюхи): строки страниц, чей
    код подходит `wanted`, без окна; вторым — хосты, которые фикстура реально обошла."""
    from apps.core import view_perms
    from apps.core.tests.test_fb33_m5d_inventory import view_fetch
    from apps.tenants import siteconfig

    monkeypatch.setattr(view_perms, "allowed", lambda *a, **k: True)
    mod = _inventory()
    saved = siteconfig.normalize(tenant.site_config)
    codes = {r.code for r in mod.schema_pages(tenant, saved) if wanted(r.code)}
    lines = mod.inventory(tenant, view_fetch(tenant), codes=codes)
    assert not [ln for ln in lines if ln.get("skipped")]
    bare = [(ln["code"], ln["ref"]) for ln in lines if ln.get("key") and not ln["window"]]
    return bare, {ln["host"] for ln in lines if ln.get("key")}


def without_sources(monkeypatch, module):
    """Реестр модуля как до среза (без источников) — для сравнения числа запросов."""
    monkeypatch.setitem(
        detail_sections.DETAIL_SECTIONS,
        module,
        tuple(
            dataclasses.replace(s, source=None, content_nav="") if s.source else s
            for s in detail_sections.DETAIL_SECTIONS[module]
        ),
    )


def dd(part: str, name: str) -> str:
    found = re.search(rf"<dd\b[^>]*data-inhalt-{name}[^>]*>(.*?)</dd>", part, re.S)
    return _text(found.group(1)) if found else ""


def woher_of(part: str, selected: dict) -> str:
    """«Woher» фразой; FB-33 M5d-8 (E7): у списка полей — его вводная фраза."""
    woher_list = selected["content"].get("woher_list")
    return woher_list["intro"] if woher_list else dd(part, "woher")


def link_of(part: str):
    a = re.search(r"<a\b([^>]*data-inhalt-link[^>]*)>(.*?)</a>", part, re.S)
    if a is None:
        return None
    return re.search(r'href="([^"]*)"', a.group(1)).group(1), _text(a.group(2))


# --- №2: строк без окна нет -----------------------------------------------------------------------


@pytest.mark.parametrize("bt", ["online_shop", "bakery"])
def test_no_g1_row_without_window(monkeypatch, bt):
    """У страницы товара (тип и «Nur diese Seite») окно есть у каждой строки."""
    tenant, product = _shop(bt)
    code = object_structure.schema_code("product", product)
    bare, hosts = bare_rows(tenant, monkeypatch, lambda c: c in ("product", code))
    assert {"product_detail", object_structure.object_host("product", product)} <= hosts
    assert not bare, bare


# --- реестр: таблица источников --------------------------------------------------------------------


def test_sources_table():
    """Источник — у восьми разделов и у «Ähnliche Produkte» (только объект); виды, экраны и
    тексты — по таблице; `trust` и `reviews` — без источника."""
    got = sources("catalog")
    assert set(got) == set(EXPECT) | {"related"}
    with translation.override("de"):
        for key, (kind, nav, shows, _woher) in EXPECT.items():
            sec = section("catalog", key)
            assert (sec.source.kind, sec.content_nav) == (kind, nav), key
            assert str(sec.source.shows) == shows, key
            assert not sec.source.object_only, key
        related = section("catalog", "related")
        assert related.source.kind == "auto" and related.source.object_only
        assert not related.content_nav and str(related.source.shows) == RELATED[0]
    for key in OWN_WINDOW:
        sec = section("catalog", key)
        assert sec.source is None and not sec.content_nav, key
    # реестр по-прежнему держит только подписи и флаги: порядок и ключи товара — как были
    assert detail_sections.section_keys("catalog") == (
        "description",
        "info",
        "sizes",
        "trust",
        "anprobe",
        "waitlist",
        "instore",
        "question",
        "reviews",
        "related",
        "recent",
    )


def test_content_navs_are_unambiguous_entries():
    """Экран ссылки — запись `nav_registry` (одна без `query`); подпись — её подпись."""
    with translation.override("de"):
        for key, (_kind, nav, _shows, _woher) in EXPECT.items():
            if not nav:
                continue
            entries = [e for e in nav_registry.ENTRIES if e.url_name == nav]
            assert len([e for e in entries if not e.query]) == 1, key
            assert str(nav_registry.entry_by_url(nav).label) == SCREENS[nav], key
            assert reverse(nav), key


def test_gated_sections_have_only_if():
    """A7б: раздел с presence-гейтом говорит, когда он появляется."""
    for key in GATED:
        assert str(section("catalog", key).source.only_if).startswith("Erscheint nur, wenn"), key
    assert not section("catalog", "instore").source.only_if


# --- строка типа: окно -----------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(EXPECT))
def test_type_row_window(key):
    """Окно строки типа: «zeigt», «Woher», видимость и действия — по флагам строки; ссылка —
    экран источника, у `auto` ссылки и причины нет; одна вкладка, без «Vorschau»."""
    kind, nav, shows, woher = EXPECT[key]
    tenant, _product = _shop()
    part, panel, selected, view = _inhalt(tenant, f"?seite=product&block={key}")
    assert [t["parts"] for t in block_window.tabs(selected, view)] == [["inhalt"]]
    assert "data-window-tabs" not in panel and "data-bw-preview" not in panel
    assert f"Dieser Block zeigt: {shows}." in _text(part)
    assert woher_of(part, selected) == woher
    moves = selected["can_up"] or selected["can_down"]
    actions = ACT_HIDE_MOVE if moves else ACT_HIDE
    visible = "sichtbar — bei allen Produkten." if kind == "field" else "sichtbar."
    assert selected["can_hide"] and dd(part, "visibility") == f"{visible} {actions}"
    assert "data-inhalt-fixed" not in part and "🔒" not in part and HINT in part
    link = link_of(part)
    if kind == "auto":
        assert link is None and "data-inhalt-reason" not in part
        assert selected["content"]["link"] is None and not selected["content"]["reason"]
    else:
        assert link == (reverse(nav), f"Inhalt bearbeiten: {SCREENS[nav]}")
        assert "data-inhalt-only-here" not in part


@pytest.mark.parametrize("key", OWN_WINDOW)
def test_rows_with_own_window_untouched(key):
    """`trust` и `reviews` — окно прежнее, части «Inhalt» нет."""
    tenant, _product = _shop()
    html, view, selected = _capture(Browser(tenant), f"?seite=product&block={key}")
    assert "content" not in selected
    tabs = block_window.tabs(selected, view)
    assert tabs and "inhalt" not in [p for t in tabs for p in t["parts"]]
    assert 'data-window-part="inhalt"' not in _panel(html)


def test_related_part_only_on_the_object_row():
    """A1: «Ähnliche Produkte» — у типа окно «Seite» без «Inhalt» (эталон `product|related`
    держит замок P0), у одного товара — «Inhalt» без ссылки."""
    tenant, product = _shop()
    html, view, selected = _capture(Browser(tenant), "?seite=product&block=related")
    assert "content" not in selected and 'data-window-part="inhalt"' not in _panel(html)
    assert block_window.tabs(selected, view)
    code = object_structure.schema_code("product", product)
    part, _panel_html, selected, view = _inhalt(tenant, f"?seite={code}&block=related")
    assert [t["parts"] for t in block_window.tabs(selected, view)] == [["inhalt"]]
    assert f"Dieser Block zeigt: {RELATED[0]}." in _text(part)
    assert dd(part, "woher") == RELATED[1]
    assert link_of(part) is None and "data-inhalt-reason" not in part
    assert dd(part, "visibility").startswith("Standard: sichtbar.")


# --- №6, №12: строка одного товара -----------------------------------------------------------------


@pytest.mark.parametrize(
    "fields, filled",
    [
        ({"description": {"de": "Fein", "en": ""}}, FILLED),
        ({"description": {"de": "", "en": ""}}, EMPTY),
        ({"description": {"de": ""}}, EMPTY),
        ({"description": {}}, EMPTY),
    ],
)
def test_object_filled_state(fields, filled):
    """Строка «Nur diese Seite»: поле ЭТОГО товара и заполнено ли; ссылка — форма товара,
    подпись — его имя, «nur hier»."""
    tenant, product = _shop(**fields)
    code = object_structure.schema_code("product", product)
    part, _panel_html, selected, _view = _inhalt(tenant, f"?seite={code}&block=description")
    assert dd(part, "woher") == f"Feld „Beschreibung“ dieses Produkts {filled}"
    assert ONLY_IF_FILLED not in part
    assert dd(part, "visibility").startswith("Standard: sichtbar.")
    href, name = link_of(part)
    assert href == reverse("catalog:product-edit", args=[product.pk])
    assert name == "Inhalt bearbeiten: Darjeeling"
    assert "data-inhalt-only-here" in part
    assert selected["content"]["filled"] == filled


@pytest.mark.parametrize(
    "fields, filled",
    [
        ({}, EMPTY),
        ({"brand": "Ronnefeldt"}, FILLED),
        ({"allergens": ["gluten"]}, FILLED),
        ({"allergens": [], "additives": [], "ingredients": "  "}, EMPTY),
        ({"origin": "Indien"}, FILLED),
    ],
)
def test_object_info_filled_by_any_field(fields, filled):
    """«Kennzeichnung» заполнена, если заполнено хоть одно её поле (те же поля, что гейт
    `product_has_info` витрины)."""
    tenant, product = _shop(**fields)
    code = object_structure.schema_code("product", product)
    _part, _panel_html, selected, _view = _inhalt(tenant, f"?seite={code}&block=info")
    # FB-33 M5d-8 (E7): «Woher» — списком полей с итогом «N von M»; «заполнено ли» раздела —
    # прежнее «хватает одного»
    assert selected["content"]["woher_list"]["intro"].startswith("Felder dieses Produkts — ")
    assert selected["content"]["filled"] == filled


def test_info_fields_are_the_storefront_gate():
    """Поля «заполнено ли» у «Kennzeichnung» — поля модели, по которым витрина решает показ."""
    fields = {str(f) for f in section("catalog", "info").source.fields}
    assert fields == {
        "brand",
        "condition",
        "material",
        "care",
        "origin",
        "ingredients",
        "allergens",
        "additives",
    }
    names = {f.name for f in Product._meta.get_fields()}
    assert fields <= names and "description" in names
    view = (ROOT / "apps/promotions/public_views.py").read_text(encoding="utf-8")
    gate = view[view.index('"product_has_info": bool(') :][:600]
    for name in fields - {"allergens", "additives"}:
        assert f"product.{name}" in gate, name
    assert "product.allergen_labels" in gate and "product.additive_labels" in gate


def test_object_and_type_answer_by_ref():
    """№12: у типа и у одного товара окно отвечает на тот же ref раздела; свой блок с тем же
    видом и общий блок части не получают (точный ref — замок P0)."""
    tenant, product = _shop()
    code = object_structure.schema_code("product", product)
    for key in sorted(EXPECT):
        for query in (f"?seite=product&block={key}", f"?seite={code}&block={key}"):
            _html, _view, selected = _capture(Browser(tenant), query)
            assert selected["ref"] == key and "content" in selected, query
    host = object_structure.object_host("product", product)
    row = {"ref": "shared:description", "key": "description", "label": "x"}
    window_parts.content_part(row, host, _req(tenant), code=code)
    assert "content" not in row


def test_object_settings_and_auto_rows():
    """У одного товара настройка ведёт на экран настройки (без «nur hier»), авто — без ссылки."""
    tenant, product = _shop()
    code = object_structure.schema_code("product", product)
    part, _p, _s, _v = _inhalt(tenant, f"?seite={code}&block=instore")
    assert link_of(part) == (reverse("settings"), "Inhalt bearbeiten: Mein Geschäft")
    assert "data-inhalt-only-here" not in part
    assert dd(part, "woher") == EXPECT["instore"][3]
    part, _p, _s, _v = _inhalt(tenant, f"?seite={code}&block=recent")
    assert link_of(part) is None and dd(part, "woher") == EXPECT["recent"][3]


# --- свой замок G1a: у еды «Kennzeichnung» не скрывается ------------------------------------------


def test_food_info_not_hideable_text():
    """У еды раздел «Kennzeichnung» скрыть нельзя (LMIV): видимость — текст LMIV, действий
    нет — и у типа, и у одного товара; у магазина — обычный текст."""
    tenant, product = _shop("bakery")
    code = object_structure.schema_code("product", product)
    for query in ("?seite=product&block=info", f"?seite={code}&block=info"):
        part, _panel_html, selected, _view = _inhalt(tenant, query)
        assert not selected["can_hide"], query
        assert dd(part, "visibility") == LMIV, query
        assert "Ausblenden" not in dd(part, "visibility"), query
    shop, _p = _shop()
    part, _panel_html, selected, _view = _inhalt(shop, "?seite=product&block=info")
    assert selected["can_hide"] and dd(part, "visibility").startswith("sichtbar — bei allen")


# --- №13: подпись поля есть на форме товара --------------------------------------------------------


def cabinet_page(tenant, path) -> str:
    from apps.core.models import Membership
    from apps.core.tests.test_staff_walk import _open as walk_open
    from apps.core.tests.test_staff_walk import _user

    resp = walk_open(path, tenant, _user(Membership.ROLE_OWNER))
    assert resp.status_code == 200, path
    return resp.content.decode()


def test_field_label_on_cabinet_form():
    """A10: подписи полей в окне — те же строки (msgid), что на форме товара: «Beschreibung»
    — подпись поля, «Kennzeichnung» — вкладка формы (у еды видна)."""
    tenant, product = _shop("bakery")
    with translation.override("de"):
        html = cabinet_page(tenant, reverse("catalog:product-edit", args=[product.pk]))
        description = str(section("catalog", "description").source.field_label)
        info = str(section("catalog", "info").source.field_label)
    assert (description, info) == ("Beschreibung", "Kennzeichnung")
    labels = [_text(m) for m in re.findall(r"<label\b[^>]*>(.*?)</label>", html, re.S)]
    assert any(text.startswith("Beschreibung") for text in labels), labels[:20]
    tab = re.search(r'<button\b[^>]*data-pf-tab="kennz"[^>]*>(.*?)</button>', html, re.S)
    assert tab and _text(tab.group(1)) == "Kennzeichnung"
    assert "hidden" not in re.search(r'class="([^"]*)"', tab.group(0)).group(1).split()
    # на форме категории — поле, на которое ссылается «Größentabelle»
    with translation.override("de"):
        html = cabinet_page(tenant, reverse("catalog:category-edit", args=[product.category_id]))
    assert "Größentabelle" in html


# --- №22 / Y3, Y6: ссылка и причина ----------------------------------------------------------------


def test_link_closed_screen_gives_a_reason(monkeypatch):
    """Экран ссылки закрыт (пакет) — причина одним абзацем с именем экрана, без ссылки."""
    from apps.core import packages

    tenant, _product = _shop()
    monkeypatch.setattr(packages, "view_allowed", lambda t, name: name != "catalog:category-list")
    part, _panel_html, selected, _view = _inhalt(tenant, "?seite=product&block=sizes")
    assert link_of(part) is None and selected["content"]["screen"] == "Kategorien"
    para = re.search(r"<p\b[^>]*data-inhalt-reason[^>]*>(.*?)</p>", part, re.S)
    assert _text(para.group(1)) == "Inhalt bearbeiten: Kategorien — Nicht in Ihrem Paket enthalten"
    assert "<a" not in para.group(1)


# --- №13 (язык), №16: переводы ---------------------------------------------------------------------


def test_new_msgids_in_all_po():
    assert_msgids_in_all_po(source_msgids("catalog", sorted(sources("catalog"))))


def test_window_in_russian_has_no_german_texts():
    tenant, _product = _shop()
    with translation.override("ru"):
        for key in ("description", "sizes", "recent", "instore"):
            part, _panel_html, _selected, _view = _inhalt(tenant, f"?seite=product&block={key}")
            text = _text(part)
            for german in (
                "Dieser Block zeigt",
                "Woher:",
                "Erscheint nur",
                "automatisch",
                "Feld „",
            ):
                assert german not in text, (key, german)
            assert EXPECT[key][2] not in text, key


# --- Y8: без скриптов — та же часть колонкой -------------------------------------------------------


def test_inhalt_nojs_column():
    tenant, product = _shop()
    code = object_structure.schema_code("product", product)
    for query in ("?seite=product&block=description", f"?seite={code}&block=recent"):
        _part_html, panel, _selected, _view = _inhalt(tenant, query)
        sec = re.search(r'<section id="schema-tab-was"[^>]*>', panel)
        assert sec and " hidden" not in sec.group(0), query
        assert 'value="window_done"' in panel and 'value="revert"' in panel, query
        assert "tablist" not in panel, query


# --- №31: запросы ----------------------------------------------------------------------------------


def test_inhalt_queries_not_above_the_base(monkeypatch):
    """Окно «Inhalt» строки типа и строки товара не добавляет запросов к экрану без него."""
    tenant, product = _shop()
    code = object_structure.schema_code("product", product)
    queries = [f"?seite=product&block={key}" for key in ("description", "sizes", "recent")]
    queries += [f"?seite={code}&block={key}" for key in ("description", "instore", "related")]
    b = Browser(tenant)
    with_part = {q: _warm_count(b, q) for q in queries}
    assert 'data-window-part="inhalt"' in b.get(queries[0])
    without_sources(monkeypatch, "catalog")
    assert 'data-window-part="inhalt"' not in b.get(queries[0])
    for q in queries:
        assert with_part[q] <= _warm_count(b, q), q
