"""FB-33 M5d-4c (G1c стопки 12): окно «Inhalt» у разделов страницы номера.

План — `docs/fb33-stack12-plan-2026-11-23.md` §3 (карта источников), §4 «G1a…e», §10 (A7, A10,
A13, Y8). Срез правит только реестр `detail_sections.DETAIL_SECTIONS["stays"]`: description и
amenities — поля номера, similar — авто. `reviews` — со своим окном, без источника. Витрина не
меняется.

Общие помощники — `test_fb33_m5d4a_product.py`.
"""

import re
import uuid

import pytest
from django.db import connection
from django.urls import reverse
from django.utils import translation

from apps.core import block_window, detail_sections, nav_registry, object_structure
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import _capture, _panel
from apps.core.tests.test_fb33_m5d1_inhalt import HINT
from apps.core.tests.test_fb33_m5d2_core import (
    ACT_HIDE,
    ACT_HIDE_MOVE,
    EMPTY,
    FILLED,
    ONLY_IF_FILLED,
    _inhalt,
    _text,
    _warm_count,
)
from apps.core.tests.test_fb33_m5d4a_product import (
    assert_msgids_in_all_po,
    bare_rows,
    cabinet_page,
    dd,
    link_of,
    section,
    source_msgids,
    sources,
    tenant_of,
    without_sources,
)
from apps.stays.models import StayUnit

pytestmark = pytest.mark.django_db
#: замки первого коммита: на базе красные (записей реестра ещё нет)
RED = pytest.mark.xfail(strict=True, reason="M5d-4c: источников у разделов номера ещё нет")

#: раздел → (вид источника, экран ссылки, «Dieser Block zeigt», «Woher» строки типа)
EXPECT = {
    "description": (
        "field",
        "stays:units",
        "die Beschreibung der Unterkunft",
        f"Feld „Beschreibung“ bei jeder Unterkunft. {ONLY_IF_FILLED}",
    ),
    "amenities": (
        "field",
        "stays:units",
        "Ausstattung, Bettart und Fläche der Unterkunft",
        "Feld „Ausstattung“ bei jeder Unterkunft. "
        "Erscheint nur, wenn mindestens eine dieser Angaben ausgefüllt ist.",
    ),
    "similar": (
        "auto",
        "",
        "bis zu 3 andere Unterkünfte — gleiche Art zuerst, dann nach Preis",
        "automatisch — aus Ihren aktiven Unterkünften. Nichts zu pflegen. "
        "Erscheint nur, wenn es weitere aktive Unterkünfte gibt.",
    ),
}
FIELD_LABELS = {"description": "Beschreibung", "amenities": "Ausstattung"}
OWN_WINDOW = ("reviews",)
#: A7б: описание и оснащение показываются при заполненных полях, «Ähnliche» — если есть другие
GATED = ("description", "amenities", "similar")
SCREEN = "Zimmer & Preise"
#: как подпись стоит в разметке (экранирована один раз)
SCREEN_HTML = "Zimmer &amp; Preise"


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    from apps.core import page_settings

    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr(page_settings, "_storefront_shows", lambda tenant, code: True)
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _hotel(**fields):
    tenant = tenant_of("hotel")
    unit = StayUnit.objects.create(
        **{"name": f"Seeblick {uuid.uuid4().hex[:6]}", "description": "Ruhig, mit Balkon", **fields}
    )
    return tenant, unit


# --- №2: строк без окна нет -----------------------------------------------------------------------


@RED
def test_no_g1_row_without_window(monkeypatch):
    tenant, unit = _hotel()
    code = object_structure.schema_code("stay", unit)
    bare, hosts = bare_rows(tenant, monkeypatch, lambda c: c in ("stay", code))
    assert {"stay_detail", object_structure.object_host("stay", unit)} <= hosts
    assert not bare, bare


# --- реестр ----------------------------------------------------------------------------------------


@RED
def test_sources_table():
    assert set(sources("stays")) == set(EXPECT)
    with translation.override("de"):
        for key, (kind, nav, shows, _woher) in EXPECT.items():
            sec = section("stays", key)
            assert (sec.source.kind, sec.content_nav) == (kind, nav), key
            assert str(sec.source.shows) == shows and not sec.source.object_only, key
    for key in OWN_WINDOW:
        sec = section("stays", key)
        assert sec.source is None and not sec.content_nav, key
    assert detail_sections.section_keys("stays") == (
        "description",
        "amenities",
        "reviews",
        "similar",
    )


def test_content_nav_is_an_unambiguous_entry():
    with translation.override("de"):
        entries = [e for e in nav_registry.ENTRIES if e.url_name == "stays:units"]
        assert len([e for e in entries if not e.query]) == 1
        assert str(nav_registry.entry_by_url("stays:units").label) == SCREEN
        assert reverse("stays:units")


@RED
def test_gated_sections_have_only_if():
    """A7б: раздел с presence-гейтом говорит, когда он появляется; поля «заполнено ли» —
    настоящие поля модели (у оснащения — те же три, по которым витрина решает показ)."""
    names = {f.name for f in StayUnit._meta.get_fields()}
    for key in GATED:
        src = section("stays", key).source
        assert str(src.only_if).startswith("Erscheint nur, wenn"), key
        assert set(src.fields) <= names, key
    assert set(section("stays", "amenities").source.fields) == {"amenities", "bed_type", "area_sqm"}


# --- строка типа -----------------------------------------------------------------------------------


@RED
@pytest.mark.parametrize("key", sorted(EXPECT))
def test_type_row_window(key):
    kind, nav, shows, woher = EXPECT[key]
    tenant, _unit = _hotel()
    part, panel, selected, view = _inhalt(tenant, f"?seite=stay&block={key}")
    assert [t["parts"] for t in block_window.tabs(selected, view)] == [["inhalt"]]
    assert "data-window-tabs" not in panel and "data-bw-preview" not in panel
    assert f"Dieser Block zeigt: {shows}." in _text(part)
    assert dd(part, "woher") == woher
    # A13: «Verschieben» — только если строка номера двигается (по флагам строки)
    moves = selected["can_up"] or selected["can_down"]
    actions = ACT_HIDE_MOVE if moves else ACT_HIDE
    visible = "sichtbar — bei allen Unterkünften." if kind == "field" else "sichtbar."
    assert selected["can_hide"] and dd(part, "visibility") == f"{visible} {actions}"
    assert "data-inhalt-fixed" not in part and HINT in part
    if kind == "auto":
        assert link_of(part) is None and "data-inhalt-reason" not in part
    else:
        assert link_of(part) == (reverse(nav), f"Inhalt bearbeiten: {SCREEN_HTML}")
        assert "data-inhalt-only-here" not in part


def test_reviews_window_untouched():
    tenant, _unit = _hotel()
    html, view, selected = _capture(Browser(tenant), "?seite=stay&block=reviews")
    assert "content" not in selected
    tabs = block_window.tabs(selected, view)
    assert tabs and "inhalt" not in [p for t in tabs for p in t["parts"]]
    assert 'data-window-part="inhalt"' not in _panel(html)


# --- №6, №12: строка одного номера -----------------------------------------------------------------


@RED
@pytest.mark.parametrize(
    "key, fields, filled",
    [
        ("description", {"description": "Ruhig"}, FILLED),
        ("description", {"description": ""}, EMPTY),
        ("description", {"description": " \n"}, EMPTY),
        ("amenities", {}, EMPTY),
        ("amenities", {"amenities": [], "bed_type": "", "area_sqm": 0}, EMPTY),
        ("amenities", {"amenities": ["wifi"]}, FILLED),
        ("amenities", {"bed_type": "Doppelbett"}, FILLED),
        ("amenities", {"area_sqm": 24}, FILLED),
    ],
)
def test_object_filled_state(key, fields, filled):
    """Строка «Nur diese Seite»: поле ЭТОГО номера и заполнено ли; ссылка — страница номера,
    подпись — его имя, «nur hier»."""
    tenant, unit = _hotel(**fields)
    code = object_structure.schema_code("stay", unit)
    part, _panel_html, selected, _view = _inhalt(tenant, f"?seite={code}&block={key}")
    assert dd(part, "woher") == f"Feld „{FIELD_LABELS[key]}“ dieser Unterkunft {filled}"
    assert selected["content"]["filled"] == filled
    assert "Erscheint nur" not in dd(part, "woher")
    href, name = link_of(part)
    assert href == reverse("stays:unit-edit", args=[unit.pk])
    assert name == f"Inhalt bearbeiten: {unit.name}" and "data-inhalt-only-here" in part


@RED
def test_object_and_type_answer_by_ref():
    tenant, unit = _hotel()
    code = object_structure.schema_code("stay", unit)
    for key in sorted(EXPECT):
        for query in (f"?seite=stay&block={key}", f"?seite={code}&block={key}"):
            _html, _view, selected = _capture(Browser(tenant), query)
            assert selected["ref"] == key and "content" in selected, query
    part, _p, _s, _v = _inhalt(tenant, f"?seite={code}&block=similar")
    assert link_of(part) is None and dd(part, "woher") == EXPECT["similar"][3]


# --- №13: подписи полей есть на форме номера ------------------------------------------------------


@RED
def test_field_label_on_cabinet_form():
    """A10: подписи полей в окне — те же строки (msgid), что на странице номера: «Beschreibung»
    — подпись поля, «Ausstattung» — заголовок группы галочек; рядом — «Bettart»."""
    tenant, unit = _hotel()
    with translation.override("de"):
        html = cabinet_page(tenant, reverse("stays:unit-edit", args=[unit.pk]))
        labels = {key: str(section("stays", key).source.field_label) for key in FIELD_LABELS}
    assert labels == FIELD_LABELS
    texts = [_text(m) for m in re.findall(r"<label\b[^>]*>(.*?)</label>", html, re.S)]
    assert any(text.startswith("Beschreibung") for text in texts), texts[:30]
    legends = [_text(m) for m in re.findall(r"<legend\b[^>]*>(.*?)</legend>", html, re.S)]
    assert "Ausstattung" in legends, legends
    assert any(text.startswith("Bettart") for text in texts), texts[:30]


# --- причина вместо ссылки -------------------------------------------------------------------------


@RED
def test_link_closed_screen_gives_a_reason(monkeypatch):
    from apps.core import packages

    tenant, _unit = _hotel()
    monkeypatch.setattr(packages, "view_allowed", lambda t, name: name != "stays:units")
    part, _panel_html, selected, _view = _inhalt(tenant, "?seite=stay&block=amenities")
    assert link_of(part) is None and selected["content"]["screen"] == SCREEN
    para = re.search(r"<p\b[^>]*data-inhalt-reason[^>]*>(.*?)</p>", part, re.S)
    assert (
        _text(para.group(1)) == f"Inhalt bearbeiten: {SCREEN_HTML} — Nicht in Ihrem Paket enthalten"
    )
    assert "<a" not in para.group(1)


# --- переводы --------------------------------------------------------------------------------------


@RED
def test_new_msgids_in_all_po():
    assert_msgids_in_all_po(source_msgids("stays", sorted(sources("stays"))))


@RED
def test_window_in_russian_has_no_german_texts():
    tenant, _unit = _hotel()
    with translation.override("ru"):
        for key in sorted(EXPECT):
            part, _panel_html, _selected, _view = _inhalt(tenant, f"?seite=stay&block={key}")
            text = _text(part)
            for german in (
                "Dieser Block zeigt",
                "Woher:",
                "Erscheint nur",
                "Feld „",
                "automatisch",
            ):
                assert german not in text, (key, german)
            assert EXPECT[key][2] not in text, key


# --- Y8: без скриптов ------------------------------------------------------------------------------


@RED
def test_inhalt_nojs_column():
    tenant, unit = _hotel()
    code = object_structure.schema_code("stay", unit)
    for query in ("?seite=stay&block=similar", f"?seite={code}&block=description"):
        _part_html, panel, _selected, _view = _inhalt(tenant, query)
        sec = re.search(r'<section id="schema-tab-was"[^>]*>', panel)
        assert sec and " hidden" not in sec.group(0), query
        assert 'value="window_done"' in panel and 'value="revert"' in panel, query
        assert "tablist" not in panel, query


# --- №31: запросы ----------------------------------------------------------------------------------


@RED
def test_inhalt_queries_not_above_the_base(monkeypatch):
    tenant, unit = _hotel()
    code = object_structure.schema_code("stay", unit)
    queries = [f"?seite=stay&block={key}" for key in ("description", "similar")]
    queries += [f"?seite={code}&block={key}" for key in ("description", "amenities", "similar")]
    b = Browser(tenant)
    with_part = {q: _warm_count(b, q) for q in queries}
    assert 'data-window-part="inhalt"' in b.get(queries[0])
    without_sources(monkeypatch, "stays")
    assert 'data-window-part="inhalt"' not in b.get(queries[0])
    for q in queries:
        assert with_part[q] <= _warm_count(b, q), q
