"""FB-33 M5d-2b (стопка 12): доводка ядра части окна «Inhalt».

План — `docs/fb33-stack12-plan-2026-11-23.md` §2, §9 №5, §10, §11. Четыре правки ядра:
1. общий тип «Veranstaltungen» (хост событий и туров) — вторая ссылка «Inhalt bearbeiten:
   Reisen» (`ContentSource.more_nav`): только у строки ТИПА, только у раздела обоих видов и
   только если экран открыт этому пользователю;
2. слова вида у такого раздела на строке типа — «bei jeder Veranstaltung und Reise»;
3. источник одного вида (`ContentSource.kinds`): «Zeitplan» есть только у события — у строки
   одного тура окно честно говорит, что блока там нет (без ссылки и без «Feld …»);
4. «Abbrechen» в окне скрытой строки — список «Ausgeblendet» остаётся раскрытым.
"""

import logging
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import polib
import pytest
from django.urls import reverse
from django.utils import translation

from apps.core import aufbau_draft, detail_sections, nav_registry, object_structure, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m5d2_core import _description, _shop
from apps.core.tests.test_fb33_m5d4d_events import (  # noqa: F401 — `_env` — общая фикстура
    FIELDS,
    _env,
    _event,
    _inhalt,
    _section,
    _sources,
    _tenant,
    _text,
    _tour,
)
from apps.events import landing
from apps.events.models import Event, Tour

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
TOUR_LIST = "events:tour-list"
EVERY_BOTH = "bei jeder Veranstaltung und Reise"
ALL_BOTH = "bei allen Veranstaltungen und Reisen"
NOT_FOR_KIND = "%(all)s wird dieser Block nicht gezeigt."
ONLY_IF_FILLED = "Erscheint nur, wenn das Feld ausgefüllt ist."
PROGRAM_LABEL = "Ablauf / Programm (ein Punkt pro Zeile)"
MSGIDS = (EVERY_BOTH, ALL_BOTH, NOT_FOR_KIND)
ANCHOR = "fb33-stack-anchor-m5d2"


def _all_sources():
    return [
        (module, s)
        for module, sections in detail_sections.DETAIL_SECTIONS.items()
        for s in sections
        if s.source is not None
    ]


# --- 1. вторая ссылка общего типа -----------------------------------------------------------------


def test_more_nav_only_at_shared_field_sections_of_events():
    """`more_nav` — у разделов-полей обоих видов (`only == ""`, без `kinds`) модуля событий;
    у остальных источников реестра его нет; каждое имя — запись `nav_registry`."""
    for module, s in _all_sources():
        at = f"{module}/{s.key}"
        both = module == "events" and s.source.kind == "field" and not s.only
        both = both and not s.source.kinds
        assert s.source.more_nav == ((TOUR_LIST,) if both else ()), at
        for url_name in s.source.more_nav:
            assert nav_registry.entry_by_url(url_name) is not None, at
            assert url_name != s.content_nav, at
    assert {k for k, s in _sources().items() if s.more_nav} == set(FIELDS)


def test_type_row_has_the_second_link():
    """Строка типа «Veranstaltungen»: две ссылки — список событий и список туров; вторая —
    тем же видом, имя = видимый текст, без «nur hier»."""
    tenant = _tenant()
    part, ct = _inhalt(tenant, "?seite=event&block=idea")
    assert ct["link"] == {
        "label": "Veranstaltungen",
        "url": reverse("events:list"),
        "only_here": False,
    }
    assert ct["more_links"] == [{"label": "Reisen", "url": reverse(TOUR_LIST)}]
    links = re.findall(r"<p\b([^>]*)>\s*<a\b([^>]*)>(.*?)</a>", part, re.S)
    assert [_text(inner) for _p, _a, inner in links] == [
        "Inhalt bearbeiten: Veranstaltungen",
        "Inhalt bearbeiten: Reisen",
    ]
    first, second = (re.search(r'class="([^"]*)"', a).group(1) for _p, a, _inner in links)
    assert first == second
    (_p1, a1, _i1), (p2, a2, inner2) = links
    assert "data-inhalt-link" in a1 and "data-inhalt-more" not in a1
    assert "data-inhalt-link" in a2 and "data-inhalt-more" in a2
    assert f'href="{reverse(TOUR_LIST)}"' in a2 and "break-words" in p2
    assert "aria-" not in a2 and inner2.strip() == "<span>Inhalt bearbeiten: Reisen</span>"
    assert "data-inhalt-only-here" not in part
    # порядок (Y1): ссылки — между dl и подсказкой
    assert (
        part.index("data-inhalt-dl")
        < part.index("data-inhalt-more")
        < part.index("data-inhalt-hint")
    )


def test_second_link_not_at_object_rows_and_other_sources():
    """У строки одного объекта — только его форма; у «Gastgeber» (экран) и авто — без второй."""
    tenant = _tenant()
    event, tour = _event(), _tour()
    for kind, obj in (("event", event), ("tour", tour)):
        code = object_structure.schema_code(kind, obj)
        part, ct = _inhalt(tenant, f"?seite={code}&block=idea")
        assert ct["more_links"] == [] and part.count("<a ") == 1, kind
    for key in ("hosts", "groups", "private_tour"):
        part, ct = _inhalt(tenant, f"?seite=event&block={key}")
        assert ct["more_links"] == [] and "data-inhalt-more" not in part, key


def test_second_link_only_when_the_screen_is_open(monkeypatch, caplog):
    """Экран туров закрыт этому пользователю (модуль, пакет, право) — второй ссылки нет, и
    причины тоже: первая ссылка остаётся как была."""
    tenant = _tenant()
    real = nav_registry.screen_closed

    def closed(request, url_name, **kw):
        return "perm" if url_name == TOUR_LIST else real(request, url_name, **kw)

    monkeypatch.setattr(nav_registry, "screen_closed", closed)
    with caplog.at_level(logging.ERROR, logger="apps.core.window_parts"):
        part, ct = _inhalt(tenant, "?seite=event&block=idea")
    assert ct["more_links"] == [] and ct["link"]["label"] == "Veranstaltungen"
    assert not ct["reason"] and "data-inhalt-reason" not in part and part.count("<a ") == 1
    assert not caplog.records


def test_second_link_without_a_nav_entry_is_logged(monkeypatch, caplog):
    """Имени нет в `nav_registry` — ссылки нет, ошибка в журнале (окно не падает)."""
    import dataclasses

    tenant = _tenant()
    broken = tuple(
        dataclasses.replace(s, source=dataclasses.replace(s.source, more_nav=("nope:missing",)))
        if s.key == "idea"
        else s
        for s in detail_sections.sections_for("events")
    )
    monkeypatch.setitem(detail_sections.DETAIL_SECTIONS, "events", broken)
    with caplog.at_level(logging.ERROR, logger="apps.core.window_parts"):
        _part_html, ct = _inhalt(tenant, "?seite=event&block=idea")
    assert ct["more_links"] == [] and ct["link"] is not None
    assert any("nope:missing" in r.getMessage() for r in caplog.records)


# --- 2. слова вида у раздела обоих видов ----------------------------------------------------------


def test_object_words_of_a_row():
    """Слова строки раздела: общий тип событий и туров у раздела обоих видов — «… und Reise»;
    раздел одного вида (`only` или `kinds`) и строка объекта — слова своего вида."""
    words = site_schema.OBJECT_WORDS
    with translation.override(None):
        both = site_schema.object_words("event_detail")
        assert {k: str(v) for k, v in both.items()} == {"every": EVERY_BOTH, "all": ALL_BOTH}
    assert all(type(v).__name__ == "__proxy__" for v in both.values())
    assert site_schema.object_words("event_detail", "tour") is words["tour"]
    assert site_schema.object_words("event_detail", "event") is words["event"]
    assert site_schema.object_words("event_detail", "", ("event",)) is words["event"]
    assert site_schema.object_words("event_detail", "", ("tour",)) is words["tour"]
    assert site_schema.object_words("event_detail", "", ("event", "tour")) is both
    assert site_schema.object_words("event:0123456789abcdef0123456789abcdef") is words["event"]
    assert site_schema.object_words("tour:0123456789abcdef0123456789abcdef") is words["tour"]
    assert site_schema.object_words("product_detail") is words["product"]
    assert site_schema.object_words("cart") == {}


def test_type_row_words_name_both_kinds():
    tenant = _tenant()
    label = str(landing.form_fields()["idea"].label)
    _part_html, ct = _inhalt(tenant, "?seite=event&block=idea")
    assert ct["woher"] == f"Feld „{label}“ {EVERY_BOTH}. {ONLY_IF_FILLED}"
    assert ct["visibility"] == f"sichtbar — {ALL_BOTH}."
    event, tour = _event(), _tour()
    for kind, obj, this in (
        ("event", event, "dieser Veranstaltung"),
        ("tour", tour, "dieser Reise"),
    ):
        code = object_structure.schema_code(kind, obj)
        _part_html, ct = _inhalt(tenant, f"?seite={code}&block=idea")
        assert ct["woher"].startswith(f"Feld „{label}“ {this} "), kind
        assert "und Reise" not in ct["woher"] + ct["visibility"], kind


def test_new_msgids_in_all_po():
    """Новые строки ядра — во всех пяти каталогах, после якоря ядра, переведены (кроме de), с
    теми же плейсхолдерами, без дублей пары msgctxt/msgid."""
    for lang in ("de", "en", "tr", "ru", "uk"):
        path = ROOT / f"locale/{lang}/LC_MESSAGES/django.po"
        entries = [e for e in polib.pofile(str(path)) if not e.obsolete]
        pairs = [(e.msgctxt, e.msgid) for e in entries]
        assert len(pairs) == len(set(pairs)), lang
        have = {e.msgid: e.msgstr for e in entries if e.msgctxt is None}
        text = path.read_text(encoding="utf-8")
        start = text.index(f"# {ANCHOR}\n")
        block = text[start : text.index("# fb33-stack-anchor-", start + 1)]
        for msgid in MSGIDS:
            assert msgid in have, (lang, msgid)
            assert f'msgid "{msgid}"' in block, (lang, msgid)
            got = have[msgid]
            if lang != "de":
                assert got and got != msgid, (lang, msgid)
            names = sorted(re.findall(r"%\((\w+)\)s", msgid))
            assert sorted(re.findall(r"%\((\w+)\)s", got or msgid)) == names, (lang, msgid)


def test_russian_window_has_no_german_words():
    tenant = _tenant()
    tour = _tour()
    with translation.override("ru"):
        _part_html, ct = _inhalt(tenant, "?seite=event&block=idea")
        assert "Veranstaltung" not in ct["woher"] + ct["visibility"]
        code = object_structure.schema_code("tour", tour)
        _part_html, ct = _inhalt(tenant, f"?seite={code}&block=program")
        assert "Block" not in ct["visibility"] and "Reisen" not in ct["visibility"]


# --- 3. «Zeitplan» — раздел только события --------------------------------------------------------


def test_program_is_drawn_for_events_only():
    """Факт витрины, на котором стоит `kinds`: программу (`agenda`) собирает только страница
    события; у тура нет ни поля модели, ни поля формы."""
    src = (ROOT / "apps/events/public_views.py").read_text(encoding="utf-8")
    assert src.count('"agenda":') == 1 and "event.program_localized()" in src
    assert {f.name for f in Event._meta.get_fields()} >= {"program"}
    assert "program" not in {f.name for f in Tour._meta.get_fields()}
    program = _sources()["program"]
    assert program.kinds == ("event",) and program.fields == ("program",)
    assert not program.more_nav
    # у остальных источников реестра вид не ограничен
    assert [f"{m}/{s.key}" for m, s in _all_sources() if s.source.kinds] == ["events/program"]


def test_program_at_the_type_row_speaks_of_events_only():
    tenant = _tenant()
    part, ct = _inhalt(tenant, "?seite=event&block=program")
    assert ct["woher"] == f"Feld „{PROGRAM_LABEL}“ bei jeder Veranstaltung. {ONLY_IF_FILLED}"
    assert ct["visibility"] == "sichtbar — bei allen Veranstaltungen."
    assert ct["link"]["label"] == "Veranstaltungen" and ct["more_links"] == []
    assert part.count("<a ") == 1


@pytest.mark.parametrize("program, filled", [(["09:00 — Yoga"], "— ausgefüllt."), ([], "— leer.")])
def test_program_at_an_event_says_filled(program, filled):
    tenant = _tenant()
    event = _event(program=program)
    code = object_structure.schema_code("event", event)
    _part_html, ct = _inhalt(tenant, f"?seite={code}&block=program")
    assert ct["woher"] == f"Feld „{PROGRAM_LABEL}“ dieser Veranstaltung {filled}"
    assert ct["filled"] == filled
    assert ct["link"]["url"] == reverse("events:edit", args=[event.pk])


def test_program_at_a_tour_says_the_block_is_not_shown(caplog):
    """Строка одного тура: одна фраза «у туров блок не показывается» — без ссылки, без причины,
    без «Feld …», без «ausgefüllt» и без совета про «⋯»; в журнале чисто."""
    tenant = _tenant()
    tour = _tour()
    code = object_structure.schema_code("tour", tour)
    with caplog.at_level(logging.ERROR, logger="apps.core.window_parts"):
        part, ct = _inhalt(tenant, f"?seite={code}&block=program")
    assert ct["visibility"] == "bei allen Reisen wird dieser Block nicht gezeigt."
    assert (ct["woher"], ct["filled"], ct["actions"], ct["reason"]) == ("", "", "", "")
    assert ct["link"] is None and ct["more_links"] == []
    assert ct["summary"] == "den Ablauf als Zeitleiste"
    text = _text(part)
    assert "Feld „" not in text and "Woher:" not in text and "⋯" not in text
    assert "<a " not in part and "data-inhalt-reason" not in part
    assert "Auf der Seite: bei allen Reisen wird dieser Block nicht gezeigt." in text
    assert "Standard:" not in text and "sichtbar" not in text
    assert not caplog.records


# --- 4. «Abbrechen» в окне скрытой строки ---------------------------------------------------------


@pytest.mark.parametrize("hide_first", [True, False])
def test_cancel_on_a_hidden_row_leaves_the_hidden_list_open(monkeypatch, hide_first):
    """Окно открыто из «Ausgeblendet» и закрыто «Abbrechen» — адрес помнит строку (`zuletzt`,
    как у «Fertig»), `details[data-schema-hidden]` раскрыт, ссылка строки в нём (фокус на неё
    ставит `aufbau.js`). Видимая строка «Ausgeblendet» не раскрывает.

    FB-33 стопка 14 E9 (решение владельца 2026-11-24, осознанная правка): прежнее «якоря нет —
    сообщение вверху» отменено — адрес ведёт к якорю строки (`#schema-row-<ref>`) с итогом
    `abbruch`, сообщение стоит у строки (`test_fb33_e9_cancel_anchor.py`)."""
    tenant, _product = _shop()
    _description(monkeypatch)
    b = Browser(tenant)
    b.post(seite="product", ref="related", op="toggle", zeile="1")  # список скрытых не пуст
    if hide_first:
        b.post(seite="product", ref="description", op="toggle", zeile="1")
    token = aufbau_draft.new_token()
    html = b.get(f"?seite=product&block=description&wopen={token}")
    assert 'data-window-part="inhalt"' in html
    resp, _msgs = b.post(seite="product", ref="description", op="revert", wopen=token)
    assert resp.status_code == 302
    target = urlsplit(resp["Location"])
    query = parse_qs(target.query)
    assert query.get("zuletzt") == ["description"] and "block" not in query
    assert query.get("abbruch") == ["same"]  # в окне правок не было
    assert target.fragment == "schema-row-description"
    html = b.get(f"?{target.query}")
    assert 'data-window-part="inhalt"' not in html  # окно закрыто
    details = re.search(r"<details\b([^>]*data-schema-hidden[^>]*)>(.*?)</details>", html, re.S)
    assert details
    assert (" open" in details.group(1)) is hide_first
    assert ('id="schema-row-description"' in details.group(2)) is hide_first
    assert html.count('id="schema-row-description"') == 1
    assert html.count('id="schema-cancel-msg"') == 1


# --- 5. длинное имя объекта в ссылке переносится --------------------------------------------------


@pytest.mark.parametrize("path", ["static/src/app.css", "static/css/app.css"])
def test_long_object_name_wraps_inside_the_link(path):
    """Ссылка «Inhalt bearbeiten» — `inline-flex`: её подпись (один `<span>`) — flex-элемент,
    и без `min-width: 0` длинное имя объекта без пробелов не переносится (стенд
    `fb33_m5d_inhalt_stand`, 320×568: ссылка шире окна). Правило — в исходнике и в сборке."""
    css = re.sub(r"\s+", "", (ROOT / path).read_text(encoding="utf-8"))
    for root in ("[data-schema-panel]", ".ui-bwin"):
        link = re.search(re.escape(f"{root}a[data-inhalt-link]") + r"[^{]*\{([^}]*)\}", css)
        assert link and "max-width:100%" in link.group(1), (path, root)
        span = re.search(re.escape(f"{root}a[data-inhalt-link]>span") + r"[^{]*\{([^}]*)\}", css)
        assert span, (path, root)
        assert "min-width:0" in span.group(1) and "overflow-wrap:anywhere" in span.group(1)
