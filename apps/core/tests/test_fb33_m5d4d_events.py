"""FB-33 M5d-4d (G1d стопки 12): часть окна «Inhalt» у разделов детальной события и тура.

План — `docs/fb33-stack12-plan-2026-11-23.md` §3 (карта источников), §4 «G1a…e» и «G1d», правки
ревью §10 (A7б, A8, A10, Y8), ответы владельца §11. Срез правит ТОЛЬКО метаданные окна в
реестре (`detail_sections.DETAIL_SECTIONS["events"]`: `content_nav` и `source`): ключи, подписи,
порядок и флаги разделов — прежние (`test_registry_flags_as_on_the_base`), витрина не меняется.

Хост события и тура общий (`event_detail`), раздел реестра у них один: у типа «Veranstaltungen»
ссылка — на список событий; вид строки (`only`) задаёт слова («bei jeder Reise») только у
разделов одного вида. У строки объекта ссылка ведёт на его форму (событие или тур).

M5d-2b (доводка ядра, замки — `test_fb33_m5d2b_core.py`) осознанно меняет здесь три вещи: у
типа раздел обоих видов называет оба («bei jeder Veranstaltung und Reise») и даёт вторую ссылку
«Reisen»; «Zeitplan» — раздел только события (`kinds`, «ausgefüllt» по `Event.program`), у
строки одного тура окно говорит, что блока там нет.
"""

import dataclasses
import json
import re
from pathlib import Path

import polib
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.html import escape

from apps.core import detail_parts, detail_sections, nav_registry, object_structure, site_schema
from apps.core.models import Membership
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import _capture, _panel
from apps.core.tests.test_fb33_m5d1_inhalt import _part
from apps.core.tests.test_fb33_m5d_inventory import _script
from apps.core.tests.test_staff_walk import _open as walk_open
from apps.core.tests.test_staff_walk import _user
from apps.events import landing
from apps.events.models import Event, Tour
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
BASE_REGISTRY = Path(__file__).parent / "golden_fb33m5d2" / "registry.json"
MODULE = "events"
ANCHOR = "fb33-stack-anchor-m5d4d"

ONLY_IF_FILLED = "Erscheint nur, wenn das Feld ausgefüllt ist."
ACT_HIDE_MOVE = "Ausblenden und Verschieben über „⋯“."
ACT_HIDE = "Ausblenden über „⋯“."
FILLED = "— ausgefüllt."
EMPTY = "— leer."
NOTHING_TO_DO = "Nichts zu pflegen."

#: раздел → (вид источника, экран ссылки, имя поля формы `landing.form_fields`, что считать
#: «ausgefüllt»). Карта плана §3, сверена с `_event_thematic.html` и формами кабинета.
FIELDS = {
    "for_whom": ("for_whom_text", ("details.for_whom",)),
    "idea": ("idea", ("details.idea",)),
    "includes": ("includes_text", ("details.includes",)),
    "venue": ("venue", ("details.venue",)),
    "accommodation": ("accommodation_text", ("details.accommodation",)),
    "food": ("food", ("details.food",)),
    "price": (
        "price_includes_text",
        ("details.price_includes", "details.price_excludes", "details.price_note"),
    ),
    "bring": ("bring_text", ("details.bring",)),
    "before_after": ("before_after_text", ("details.before_after",)),
    "certifications": ("certifications_text", ("details.certifications",)),
}
#: «Ablauf» — поле самой формы события (`EventForm.program_text`), в `landing` его нет; у тура
#: программы нет вовсе — M5d-2b: источник только события (`kinds`), «ausgefüllt» — по
#: `Event.program`
PROGRAM_LABEL = "Ablauf / Programm (ein Punkt pro Zeile)"
AUTO = {"groups": "event", "more_dates": "event", "private_tour": "tour"}
#: окно у этих строк уже есть (FAQ, «Stimmen») — срез их не трогает
UNTOUCHED = ("faq", "testimonials")
TYPE_LIST = "events:list"
HOSTS_SCREEN = "events:teacher-list"


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    from apps.core import page_settings

    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr(page_settings, "_storefront_shows", lambda tenant, code: True)
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _tenant():
    tenant = TenantFactory(business_type="friseur", disabled_modules=[])
    connection.tenant = tenant
    return tenant


def _event(**kw):
    kw.setdefault("title", "Yoga am See")
    kw.setdefault("starts_at", timezone.now())
    return Event.objects.create(**kw)


def _tour(**kw):
    kw.setdefault("title", "Rheinsteig")
    kw.setdefault("slug", "rheinsteig")
    kw.setdefault("is_published", True)
    return Tour.objects.create(**kw)


def _section(key):
    return next(s for s in detail_sections.sections_for(MODULE) if s.key == key)


def _sources() -> dict:
    return {s.key: s.source for s in detail_sections.sections_for(MODULE) if s.source}


def _open(tenant, query):
    html, _view, selected = _capture(Browser(tenant), query)
    return html, selected


def _inhalt(tenant, query):
    html, selected = _open(tenant, query)
    assert selected and "content" in selected, query
    return _part(_panel(html), "inhalt"), selected["content"]


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def _msgids() -> list[str]:
    """Тексты источников среза — msgid (без языка ленивая строка отдаёт msgid)."""
    with translation.override(None):
        out = []
        for source in _sources().values():
            for text in (source.shows, source.woher, source.note, source.only_if):
                if text and str(text) not in out:
                    out.append(str(text))
    return out


# --- реестр: флаги прежние, источники — по карте -------------------------------------------------


def test_registry_flags_as_on_the_base():
    """Ключи, порядок, подписи и флаги разделов (`hideable`, `orderable`, `in_place`, `only`) —
    как на базе P0: витрина читает только их. Зелёный и до записей, и после."""
    base = [row[:7] for row in json.loads(BASE_REGISTRY.read_text()) if row[0] == MODULE]
    with translation.override(None):
        got = [
            [MODULE, s.key, str(s.label), s.hideable, s.orderable, s.in_place, s.only]
            for s in detail_sections.sections_for(MODULE)
        ]
    assert got == base


def test_sources_follow_the_map():
    """Поля `details` — `field` со ссылкой на список событий, подпись — по ИМЕНИ поля формы
    (A10); «Gastgeber» — экран; три раздела «на месте» — авто, без ссылки; FAQ и «Stimmen» не
    тронуты."""
    sources = _sources()
    assert set(sources) == {*FIELDS, "program", "hosts", *AUTO}
    for key, (field, fields) in FIELDS.items():
        section, source = _section(key), sources[key]
        assert (source.kind, section.content_nav) == ("field", TYPE_LIST), key
        assert (source.field, source.fields) == (field, fields), key
        assert not source.field_label, key  # подпись — из кода формы, копии нет
        assert field in landing.form_fields(), key
    program = sources["program"]
    assert (program.kind, _section("program").content_nav) == ("field", TYPE_LIST)
    assert not program.field and program.fields == ("program",)  # M5d-2b
    assert program.kinds == ("event",)
    with translation.override(None):
        assert str(program.field_label) == PROGRAM_LABEL
    assert (sources["hosts"].kind, _section("hosts").content_nav) == ("setting", HOSTS_SCREEN)
    for key in AUTO:
        assert (sources[key].kind, _section(key).content_nav) == ("auto", ""), key
    for key in UNTOUCHED:
        assert _section(key).source is None and not _section(key).content_nav, key
    assert not [k for k, s in sources.items() if s.object_only]


def test_source_texts_are_well_formed():
    """Тексты — ленивые; «zeigt» без точки в конце; «Woher» у экрана и авто — фразой с точкой;
    A7б: у каждого раздела с presence-гейтом (здесь — у всех) есть `only_if`."""
    sources = _sources()
    assert sources
    for key, source in sources.items():
        for text in (source.shows, source.woher, source.note, source.only_if, source.field_label):
            assert not text or type(text).__name__ == "__proxy__", key
        shows = str(source.shows)
        assert shows and not shows.endswith(".") and "%(" not in shows, key
        assert str(source.only_if).endswith("."), key
        if source.kind == "field":
            assert not source.woher, key  # собирается из подписи поля и слова вида
        else:
            assert str(source.woher).endswith("."), key
        if source.kind == "auto":
            assert str(source.woher).startswith("automatisch") and NOTHING_TO_DO in str(
                source.woher
            ), key
    simple = [k for k in FIELDS if k not in ("venue", "price")]
    with translation.override(None):
        assert all(str(sources[k].only_if) == ONLY_IF_FILLED for k in simple)


def test_event_tour_only_rows():
    """Свой замок G1d: разделы одного вида остаются «на месте» и своего вида; у события нет
    строки приватного выезда, у тура — групп и серии; часть «Inhalt» — у строки своего вида."""
    for key, only in AUTO.items():
        section = _section(key)
        assert (section.only, section.in_place, section.orderable) == (only, True, False), key
        assert section.source is not None and section.source.kind == "auto", key
    tenant = _tenant()
    event, tour = _event(), _tour()
    pages = {
        "event": ("event", set(AUTO)),
        "event_obj": (object_structure.schema_code("event", event), {"groups", "more_dates"}),
        "tour_obj": (object_structure.schema_code("tour", tour), {"private_tour"}),
    }
    for name, (code, want) in pages.items():
        host = site_schema.host_for(code)
        assert set(detail_parts.in_place_keys(host)) == want, name
        for key in sorted(want):
            part, ct = _inhalt(tenant, f"?seite={code}&block={key}")
            assert ct["link"] is None and not ct["reason"], (name, key)
            assert "data-inhalt-link" not in part and "<a " not in part, (name, key)
            assert ct["woher"].startswith("automatisch"), (name, key)
            # «на месте»: только скрывается
            assert ct["actions"] == ACT_HIDE, (name, key)
    # строки чужого вида у объекта нет вовсе
    html, selected = _open(tenant, f"?seite={pages['tour_obj'][0]}&block=groups")
    assert not selected or selected.get("key") != "groups"


def test_jobs_gate_names_the_module_as_the_cabinet_does():
    """«Gruppen» и приватный выезд появляются только при модуле заявок — имя модуля в тексте
    то же, что в кабинете (копия подписи сверяется с `modules`)."""
    from apps.core import modules

    with translation.override("de"):
        label = str(modules.get_module("jobs").label_de)
        for key in ("groups", "private_tour"):
            assert f"„{label}“" in str(_sources()[key].only_if), key


# --- №2: строк без окна нет -----------------------------------------------------------------------


@pytest.mark.parametrize("page", ["event", "event_obj", "tour_obj"])
def test_no_g1_row_without_window(page):
    """Логикой `scripts/fb33_m5d_inventory.py` (ответ — разметка вьюхи): у каждой строки
    раздела страницы события (тип, одно событие, один тур) окно есть; у разделов среза в нём
    часть «Inhalt». Y8: без JS — та же часть колонкой в панели (ответ сервера и есть она)."""
    tenant = _tenant()
    code = {
        "event": lambda: "event",
        "event_obj": lambda: object_structure.schema_code("event", _event()),
        "tour_obj": lambda: object_structure.schema_code("tour", _tour()),
    }[page]()
    window_tabs = _script().window_tabs
    keys = [s.key for s in detail_sections.sections_for(MODULE)]
    host = site_schema.host_for(code)
    kind = detail_parts.object_kind(host)
    seen = []
    for key in keys:
        only = detail_sections.only_of(MODULE, key)
        if kind and only and only != kind:
            continue
        html, selected = _open(tenant, f"?seite={code}&block={key}")
        assert selected and selected["ref"] == key, (page, key)
        assert window_tabs(html) is not None and 'value="window_done"' in html, (page, key)
        if key in UNTOUCHED:
            assert "content" not in selected, (page, key)
            continue
        assert 'data-window-part="inhalt"' in _panel(html), (page, key)
        seen.append(key)
    assert len(seen) >= 12, seen


# --- №12, №22: тексты и ссылка у типа и у объекта -------------------------------------------------


def test_type_row_field():
    """Строка типа: поле и слова обоих видов общего хоста (M5d-2b), видимость и действия — из
    флагов строки, ссылка — список событий («Veranstaltungen»), без «nur hier»."""
    tenant = _tenant()
    label = str(landing.form_fields()["idea"].label)
    part, ct = _inhalt(tenant, "?seite=event&block=idea")
    assert ct["woher"] == f"Feld „{label}“ bei jeder Veranstaltung und Reise. {ONLY_IF_FILLED}"
    assert ct["filled"] == ""
    assert ct["visibility"] == "sichtbar — bei allen Veranstaltungen und Reisen."
    assert ct["actions"] == ACT_HIDE_MOVE and ct["fixed"] is False
    assert ct["link"] == {"label": "Veranstaltungen", "url": reverse(TYPE_LIST), "only_here": False}
    text = _text(part)
    assert "Dieser Block zeigt: die Idee und die Atmosphäre." in text
    assert "Inhalt bearbeiten: Veranstaltungen" in text
    # M5d-2b: вторая ссылка — список туров (`ContentSource.more_nav`)
    assert "data-inhalt-only-here" not in part and part.count("<a ") == 2
    assert "Inhalt bearbeiten: Reisen" in text and reverse("events:tour-list") in part


def test_type_rows_of_special_sources():
    """«Gastgeber» — экран преподавателей; «Ort» и «Preis» — свой текст «когда появляется»;
    «Ablauf» — подпись поля формы события."""
    tenant = _tenant()
    part, ct = _inhalt(tenant, "?seite=event&block=hosts")
    assert ct["link"] == {
        "label": "Gastgeber",
        "url": reverse(HOSTS_SCREEN),
        "only_here": False,
    }
    assert ct["visibility"] == "sichtbar." and ct["actions"] == ACT_HIDE_MOVE
    assert "Inhalt bearbeiten: Gastgeber" in _text(part)
    for key in ("venue", "price"):
        _part_html, ct = _inhalt(tenant, f"?seite=event&block={key}")
        label = str(landing.form_fields()[FIELDS[key][0]].label)
        both = "bei jeder Veranstaltung und Reise"
        assert ct["woher"].startswith(f"Feld „{label}“ {both}. Erscheint"), key
        assert ONLY_IF_FILLED not in ct["woher"], key
    _part_html, ct = _inhalt(tenant, "?seite=event&block=program")
    assert ct["woher"] == f"Feld „{PROGRAM_LABEL}“ bei jeder Veranstaltung. {ONLY_IF_FILLED}"


@pytest.mark.parametrize(
    "details, filled",
    [
        ({"idea": "Ruhe und Weite"}, FILLED),
        ({"idea": "  "}, EMPTY),
        ({"idea": {"de": ""}}, EMPTY),
        ({}, EMPTY),
    ],
)
def test_object_filled_state(details, filled):
    """№6: строка одного события — поле ЭТОГО события и заполнено ли (пусто, пробелы, словарь
    i18n с пустым значением, `details` без ключа); ссылка — его форма, «nur hier»."""
    tenant = _tenant()
    event = _event(details=details)
    code = object_structure.schema_code("event", event)
    label = str(landing.form_fields()["idea"].label)
    part, ct = _inhalt(tenant, f"?seite={code}&block=idea")
    assert ct["woher"] == f"Feld „{label}“ dieser Veranstaltung {filled}"
    assert ct["filled"] == filled and ONLY_IF_FILLED not in ct["woher"]
    assert ct["visibility"] == "Standard: sichtbar."
    link = ct["link"]
    assert link["url"] == reverse("events:edit", args=[event.pk]) and link["only_here"] is True
    # правки ревью P0 (a11y M2): `lang` — только когда язык имени не совпадает с языком окна
    assert str(link["label"]) == "Yoga am See"
    # №22: «nur hier» — плашкой после ссылки, не в её имени
    assert re.search(r"</a>\s*<span[^>]*data-inhalt-only-here", part)
    assert "Inhalt bearbeiten: Yoga am See" in _text(part)


def test_object_filled_by_any_of_the_price_fields():
    """«Preis» появляется по любому из трёх полей — «ausgefüllt» тоже; списки и записи."""
    tenant = _tenant()
    cases = (
        ({"price_note": "Frühbucher bis März"}, FILLED),
        ({"price_excludes": ["Anreise"]}, FILLED),
        ({"price_includes": [], "price_note": ""}, EMPTY),
    )
    for details, filled in cases:
        event = _event(details=details)
        code = object_structure.schema_code("event", event)
        _part_html, ct = _inhalt(tenant, f"?seite={code}&block=price")
        assert ct["filled"] == filled, details
    event = _event(details={"includes": [{"title": "Yoga", "text": ""}]})
    code = object_structure.schema_code("event", event)
    assert _inhalt(tenant, f"?seite={code}&block=includes")[1]["filled"] == FILLED


def test_tour_object_row(caplog):
    """Строка одного тура: слова тура («dieser Reise»), ссылка — форма тура; «Ablauf» — у тура
    блока нет (M5d-2b: одна фраза, без «Feld …», без ссылки и без ошибки в журнале)."""
    import logging

    tenant = _tenant()
    tour = _tour(details={"for_whom": ["Wanderer"]})
    code = object_structure.schema_code("tour", tour)
    label = str(landing.form_fields()["for_whom_text"].label)
    part, ct = _inhalt(tenant, f"?seite={code}&block=for_whom")
    assert ct["woher"] == f"Feld „{label}“ dieser Reise {FILLED}"
    assert ct["link"]["url"] == reverse("events:tour-edit", args=[tour.pk])
    assert ct["link"]["only_here"] is True and "Inhalt bearbeiten: Rheinsteig" in _text(part)
    with caplog.at_level(logging.ERROR, logger="apps.core.window_parts"):
        _part_html, ct = _inhalt(tenant, f"?seite={code}&block=program")
    assert (ct["filled"], ct["woher"], ct["link"]) == ("", "", None)
    assert ct["visibility"] == "bei allen Reisen wird dieser Block nicht gezeigt."
    assert not caplog.records
    _part_html, ct = _inhalt(tenant, f"?seite={code}&block=hosts")
    assert ct["link"]["url"] == reverse(HOSTS_SCREEN) and ct["link"]["only_here"] is False


# --- №13: подпись поля реально есть на форме кабинета ---------------------------------------------


def _owner_page(tenant, url) -> str:
    resp = walk_open(url, tenant, _user(Membership.ROLE_OWNER))
    assert resp.status_code == 200, url
    if hasattr(resp, "render"):
        resp.render()
    return resp.content.decode()


def test_field_label_on_cabinet_form():
    """Подпись каждого поля, которую называет окно, есть на странице формы события (de, GET);
    поля `details` — и на форме тура; «Ablauf» — только у события."""
    tenant = _tenant()
    event, tour = _event(), _tour()
    with translation.override("de"):
        event_html = _owner_page(tenant, reverse("events:edit", args=[event.pk]))
        tour_html = _owner_page(tenant, reverse("events:tour-edit", args=[tour.pk]))
        sources = _sources()
        labels = {
            key: str(sources[key].field_label)
            or site_schema.object_field_label("event", sources[key].field)
            for key in (*FIELDS, "program")
        }
    assert all(labels.values()), labels
    for key, label in labels.items():
        assert escape(label) in event_html, (key, label)
        if key != "program":
            assert site_schema.object_field_label("tour", sources[key].field) == label, key
            assert escape(label) in tour_html, (key, label)
    assert escape(PROGRAM_LABEL) not in tour_html
    # «Gastgeber»: запасное поле формы, которое называет «Woher», на форме есть
    hosts_label = str(landing.form_fields()["hosts_text"].label)
    assert hosts_label.startswith("Leitung") and "„Leitung“" in str(sources["hosts"].woher)
    assert escape(hosts_label) in event_html and escape(hosts_label) in tour_html


# --- экраны ссылок: записи реестра ---------------------------------------------------------------


def test_content_nav_entries_are_unambiguous():
    """Каждый `content_nav` среза — имя URL однозначной записи `nav_registry`, экран открыт
    владельцу; подпись ссылки — подпись записи."""
    tenant = _tenant()
    from types import SimpleNamespace

    req = SimpleNamespace(tenant=tenant, user=SimpleNamespace(is_authenticated=True))
    navs = {s.content_nav for s in detail_sections.sections_for(MODULE) if s.content_nav}
    assert navs == {TYPE_LIST, HOSTS_SCREEN}
    for url_name in navs:
        entries = [e for e in nav_registry.ENTRIES if e.url_name == url_name]
        assert len([e for e in entries if not e.query]) == 1, url_name
        assert reverse(url_name)
        assert nav_registry.screen_closed(req, url_name) == "", url_name


# --- №31: запросов не больше базы ----------------------------------------------------------------


def _warm_count(browser, query) -> int:
    browser.get(query)
    with CaptureQueriesContext(connection) as q:
        browser.get(query)
    return len(q.captured_queries)


@pytest.mark.parametrize("key", ["idea", "hosts", "private_tour"])
def test_inhalt_queries_not_above_the_base(monkeypatch, key):
    """Окно с частью «Inhalt» стоит не больше запросов, чем экран той же строки без источников
    (тип и объект): видимость — из флагов строки, объект экран уже нашёл."""
    tenant = _tenant()
    event, tour = _event(details={"idea": "Ruhe"}), _tour()
    obj = tour if key == "private_tour" else event
    kind = "tour" if key == "private_tour" else "event"
    queries = ("?seite=event", f"?seite={object_structure.schema_code(kind, obj)}")
    b = Browser(tenant)
    assert _section(key).source is not None
    with_part = [_warm_count(b, f"{q}&block={key}") for q in queries]
    bare = tuple(
        dataclasses.replace(s, source=None, content_nav="")
        for s in detail_sections.sections_for(MODULE)
    )
    monkeypatch.setitem(detail_sections.DETAIL_SECTIONS, MODULE, bare)
    without = [_warm_count(b, f"{q}&block={key}") for q in queries]
    assert [a <= b_ for a, b_ in zip(with_part, without, strict=True)] == [True, True], (
        with_part,
        without,
    )


# --- №13, №16: строки `.po` -----------------------------------------------------------------------


def test_new_msgids_in_all_po():
    """Тексты источников среза есть во всех пяти каталогах, переведены (кроме de), без дублей
    пары msgctxt/msgid; новые записи — сразу после якоря среза."""
    msgids = _msgids()
    assert len(msgids) >= 15
    for lang in ("de", "en", "tr", "ru", "uk"):
        path = ROOT / f"locale/{lang}/LC_MESSAGES/django.po"
        entries = [e for e in polib.pofile(str(path)) if not e.obsolete]
        pairs = [(e.msgctxt, e.msgid) for e in entries]
        assert len(pairs) == len(set(pairs)), lang
        have = {e.msgid: e.msgstr for e in entries if e.msgctxt is None}
        for msgid in msgids:
            assert msgid in have, (lang, msgid)
            if lang != "de":
                assert have[msgid] and have[msgid] != msgid, (lang, msgid)
        text = path.read_text(encoding="utf-8")
        start = text.index(f"# {ANCHOR}\n")
        block = text[start : text.index("# fb33-stack-anchor-", start + 1)]
        own = set(re.findall(r'^msgid "(.+)"$', block, re.M))
        assert own and own <= {m.replace('"', '\\"') for m in msgids} | {ANCHOR}, (lang, own)


def test_window_in_russian_has_no_german_source_text():
    """№13: окно на русском — тексты источника переведены (слова вида, «Woher», «zeigt»)."""
    tenant = _tenant()
    with translation.override("de"):
        de = {k: (str(s.shows), str(s.woher), str(s.only_if)) for k, s in _sources().items()}
    with translation.override("ru"):
        for key in ("idea", "hosts", "groups", "private_tour", "venue", "price"):
            _part_html, ct = _inhalt(tenant, f"?seite=event&block={key}")
            shows, woher, only_if = de[key]
            assert ct["summary"] != shows, key
            assert only_if not in ct["woher"], key
            assert not woher or woher not in ct["woher"], key
            assert "Feld „" not in ct["woher"] and "bei jeder" not in ct["woher"], key
