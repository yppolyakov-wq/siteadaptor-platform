"""FB-33 M5d-4b (G1b стопки 12): окно «Inhalt» у разделов страницы услуги.

План — `docs/fb33-stack12-plan-2026-11-23.md` §3 (карта источников), §4 «G1a…e», §10 (A7, A10,
Y8). Срез правит только реестр `detail_sections.DETAIL_SECTIONS["booking"]`: description,
attributes и video — поля услуги (у видео — ещё фраза про номер WhatsApp), upsell — товары
(«Sortiment»). `faq`, `team`, `reviews` — со своим окном, без источника. Витрина не меняется.

Общие помощники — `test_fb33_m5d4a_product.py`.
"""

import re

import pytest
from django.db import connection
from django.urls import reverse
from django.utils import translation

from apps.booking.models import Service
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

pytestmark = pytest.mark.django_db

VIDEO_NOTE = "Der Chat geht an Ihre WhatsApp-Nummer aus „Mein Geschäft“."
VIDEO_ONLY_IF = "Erscheint nur, wenn das Häkchen gesetzt und eine WhatsApp-Nummer eingetragen ist."
#: раздел → (вид источника, экран ссылки, «Dieser Block zeigt», «Woher» строки типа)
EXPECT = {
    "description": (
        "field",
        "booking:services",
        "die Beschreibung der Leistung",
        f"Feld „Beschreibung (Leistungsumfang)“ bei jeder Leistung. {ONLY_IF_FILLED}",
    ),
    "video": (
        "field",
        "booking:services",
        "den Knopf „Per Video zeigen lassen“ — er öffnet einen WhatsApp-Chat",
        f"Feld „Video-Beratung möglich“ bei jeder Leistung. {VIDEO_ONLY_IF}",
    ),
    "attributes": (
        "field",
        "booking:services",
        "die Details der Leistung als Liste — bis zu 12 Punkte",
        f"Feld „Details — ein Punkt pro Zeile“ bei jeder Leistung. {ONLY_IF_FILLED}",
    ),
    "upsell": (
        "setting",
        "sellable-manage",
        "bis zu 4 Produkte unter der Leistung — empfohlene zuerst",
        "Ihre Produkte — die mit Häkchen „Empfohlen“ stehen vorn. "
        "Erscheint nur, wenn es aktive Produkte gibt.",
    ),
}
#: подписи полей формы услуги (`templates/booking/service_page.html`, de)
FIELD_LABELS = {
    "description": "Beschreibung (Leistungsumfang)",
    "video": "Video-Beratung möglich",
    "attributes": "Details — ein Punkt pro Zeile",
}
OWN_WINDOW = ("faq", "team", "reviews")
#: A7б: у услуги каждый из четырёх разделов появляется по условию (`_present` вьюхи)
GATED = ("description", "video", "attributes", "upsell")
SCREENS = {"booking:services": "Leistungen", "sellable-manage": "Sortiment"}


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    from apps.core import page_settings

    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr(page_settings, "_storefront_shows", lambda tenant, code: True)
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _salon(**fields):
    tenant = tenant_of("friseur")
    service = Service.objects.create(
        **{
            "name": "Haarschnitt",
            "duration_minutes": 30,
            "price_cents": 3500,
            "description": "Waschen, Schneiden, Föhnen",
            **fields,
        }
    )
    return tenant, service


# --- №2: строк без окна нет -----------------------------------------------------------------------


def test_no_g1_row_without_window(monkeypatch):
    tenant, service = _salon()
    code = object_structure.schema_code("service", service)
    bare, hosts = bare_rows(tenant, monkeypatch, lambda c: c in ("service", code))
    assert {"service_detail", object_structure.object_host("service", service)} <= hosts
    assert not bare, bare


# --- реестр ----------------------------------------------------------------------------------------


def test_sources_table():
    assert set(sources("booking")) == set(EXPECT)
    with translation.override("de"):
        for key, (kind, nav, shows, _woher) in EXPECT.items():
            sec = section("booking", key)
            assert (sec.source.kind, sec.content_nav) == (kind, nav), key
            assert str(sec.source.shows) == shows and not sec.source.object_only, key
        assert str(section("booking", "video").source.note) == VIDEO_NOTE
    for key in OWN_WINDOW:
        sec = section("booking", key)
        assert sec.source is None and not sec.content_nav, key
    assert detail_sections.section_keys("booking") == (
        "description",
        "video",
        "attributes",
        "faq",
        "team",
        "reviews",
        "upsell",
    )


def test_content_navs_are_unambiguous_entries():
    with translation.override("de"):
        for nav, label in SCREENS.items():
            entries = [e for e in nav_registry.ENTRIES if e.url_name == nav]
            assert len([e for e in entries if not e.query]) == 1, nav
            assert str(nav_registry.entry_by_url(nav).label) == label, nav
            assert reverse(nav), nav


def test_gated_sections_have_only_if():
    """A7б: раздел с presence-гейтом говорит, когда он появляется; поля «заполнено ли» —
    настоящие поля модели."""
    names = {f.name for f in Service._meta.get_fields()}
    for key in GATED:
        src = section("booking", key).source
        assert str(src.only_if).startswith("Erscheint nur, wenn"), key
        assert set(src.fields) <= names, key
    assert section("booking", "video").source.fields == ("is_video",)


# --- строка типа -----------------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(EXPECT))
def test_type_row_window(key):
    kind, nav, shows, woher = EXPECT[key]
    tenant, _service = _salon()
    part, panel, selected, view = _inhalt(tenant, f"?seite=service&block={key}")
    assert [t["parts"] for t in block_window.tabs(selected, view)] == [["inhalt"]]
    assert "data-window-tabs" not in panel and "data-bw-preview" not in panel
    note = f" {VIDEO_NOTE}" if key == "video" else ""
    assert f"Dieser Block zeigt: {shows}.{note}" in _text(part)
    assert dd(part, "woher") == woher
    moves = selected["can_up"] or selected["can_down"]
    actions = ACT_HIDE_MOVE if moves else ACT_HIDE
    visible = "sichtbar — bei allen Leistungen." if kind == "field" else "sichtbar."
    assert selected["can_hide"] and dd(part, "visibility") == f"{visible} {actions}"
    assert "data-inhalt-fixed" not in part and HINT in part
    assert link_of(part) == (reverse(nav), f"Inhalt bearbeiten: {SCREENS[nav]}")
    assert "data-inhalt-only-here" not in part


@pytest.mark.parametrize("key", OWN_WINDOW)
def test_rows_with_own_window_untouched(key):
    tenant, _service = _salon()
    html, view, selected = _capture(Browser(tenant), f"?seite=service&block={key}")
    assert "content" not in selected
    tabs = block_window.tabs(selected, view)
    assert tabs and "inhalt" not in [p for t in tabs for p in t["parts"]]
    assert 'data-window-part="inhalt"' not in _panel(html)


# --- №6, №12: строка одной услуги ------------------------------------------------------------------


@pytest.mark.parametrize(
    "key, fields, filled",
    [
        ("description", {"description": "Waschen"}, FILLED),
        ("description", {"description": "  "}, EMPTY),
        ("description", {"description": ""}, EMPTY),
        ("video", {"is_video": True}, FILLED),
        ("video", {"is_video": False}, EMPTY),
        ("attributes", {"attributes": ["Handtuch inklusive"]}, FILLED),
        ("attributes", {"attributes": []}, EMPTY),
        ("attributes", {"attributes": ["", "  "]}, EMPTY),
    ],
)
def test_object_filled_state(key, fields, filled):
    """Строка «Nur diese Seite»: поле ЭТОЙ услуги и заполнено ли; ссылка — страница услуги,
    подпись — её имя, «nur hier»."""
    tenant, service = _salon(**fields)
    code = object_structure.schema_code("service", service)
    part, _panel_html, selected, _view = _inhalt(tenant, f"?seite={code}&block={key}")
    assert dd(part, "woher") == f"Feld „{FIELD_LABELS[key]}“ dieser Leistung {filled}"
    assert selected["content"]["filled"] == filled
    assert "Erscheint nur" not in dd(part, "woher")
    href, name = link_of(part)
    assert href == reverse("booking:service-edit", args=[service.pk])
    assert name == "Inhalt bearbeiten: Haarschnitt" and "data-inhalt-only-here" in part
    if key == "video":
        assert VIDEO_NOTE in _text(part)


def test_object_and_type_answer_by_ref():
    tenant, service = _salon()
    code = object_structure.schema_code("service", service)
    for key in sorted(EXPECT):
        for query in (f"?seite=service&block={key}", f"?seite={code}&block={key}"):
            _html, _view, selected = _capture(Browser(tenant), query)
            assert selected["ref"] == key and "content" in selected, query


def test_object_upsell_links_the_products():
    """У одной услуги «Passt gut dazu» ведёт на «Sortiment» (не на услугу), без «nur hier»."""
    tenant, service = _salon()
    code = object_structure.schema_code("service", service)
    part, _p, _s, _v = _inhalt(tenant, f"?seite={code}&block=upsell")
    assert link_of(part) == (reverse("sellable-manage"), "Inhalt bearbeiten: Sortiment")
    assert "data-inhalt-only-here" not in part and dd(part, "woher") == EXPECT["upsell"][3]


# --- №13: подписи полей есть на форме услуги ------------------------------------------------------


def test_field_label_on_cabinet_form():
    """A10: подписи полей в окне — те же строки (msgid), что на странице услуги; галочка
    «Empfohlen», о которой говорит «Passt gut dazu», есть на форме товара."""
    tenant, service = _salon()
    with translation.override("de"):
        html = cabinet_page(
            tenant, reverse("booking:service-edit", args=[service.pk]) + "?tab=text"
        )
        labels = {key: str(section("booking", key).source.field_label) for key in FIELD_LABELS}
    assert labels == FIELD_LABELS
    texts = [_text(m) for m in re.findall(r"<label\b[^>]*>(.*?)</label>", html, re.S)]
    for key, label in FIELD_LABELS.items():
        assert any(label in text for text in texts), (key, texts[:30])
    # номер WhatsApp, о котором говорит заметка, — поле экрана «Mein Geschäft»
    with translation.override("de"):
        assert "WhatsApp-Nummer" in cabinet_page(tenant, reverse("settings"))


# --- причина вместо ссылки -------------------------------------------------------------------------


def test_link_closed_screen_gives_a_reason(monkeypatch):
    from apps.core import packages

    tenant, _service = _salon()
    monkeypatch.setattr(packages, "view_allowed", lambda t, name: name != "booking:services")
    part, _panel_html, selected, _view = _inhalt(tenant, "?seite=service&block=description")
    assert link_of(part) is None and selected["content"]["screen"] == "Leistungen"
    para = re.search(r"<p\b[^>]*data-inhalt-reason[^>]*>(.*?)</p>", part, re.S)
    assert _text(para.group(1)) == "Inhalt bearbeiten: Leistungen — Nicht in Ihrem Paket enthalten"
    assert "<a" not in para.group(1)


# --- переводы --------------------------------------------------------------------------------------


def test_new_msgids_in_all_po():
    assert_msgids_in_all_po(source_msgids("booking", sorted(sources("booking"))))


def test_window_in_russian_has_no_german_texts():
    tenant, _service = _salon()
    with translation.override("ru"):
        for key in sorted(EXPECT):
            part, _panel_html, _selected, _view = _inhalt(tenant, f"?seite=service&block={key}")
            text = _text(part)
            for german in ("Dieser Block zeigt", "Woher:", "Erscheint nur", "Feld „", "Der Chat"):
                assert german not in text, (key, german)
            assert EXPECT[key][2] not in text, key


# --- Y8: без скриптов ------------------------------------------------------------------------------


def test_inhalt_nojs_column():
    tenant, service = _salon()
    code = object_structure.schema_code("service", service)
    for query in ("?seite=service&block=video", f"?seite={code}&block=upsell"):
        _part_html, panel, _selected, _view = _inhalt(tenant, query)
        sec = re.search(r'<section id="schema-tab-was"[^>]*>', panel)
        assert sec and " hidden" not in sec.group(0), query
        assert 'value="window_done"' in panel and 'value="revert"' in panel, query
        assert "tablist" not in panel, query


# --- №31: запросы ----------------------------------------------------------------------------------


def test_inhalt_queries_not_above_the_base(monkeypatch):
    tenant, service = _salon()
    code = object_structure.schema_code("service", service)
    queries = [f"?seite=service&block={key}" for key in ("description", "upsell")]
    queries += [f"?seite={code}&block={key}" for key in ("description", "video", "upsell")]
    b = Browser(tenant)
    with_part = {q: _warm_count(b, q) for q in queries}
    assert 'data-window-part="inhalt"' in b.get(queries[0])
    without_sources(monkeypatch, "booking")
    assert 'data-window-part="inhalt"' not in b.get(queries[0])
    for q in queries:
        assert with_part[q] <= _warm_count(b, q), q
