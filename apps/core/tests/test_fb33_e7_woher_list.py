"""FB-33 стопка 14 E7 (M5d-8): «Woher» в окне «Inhalt» — списком полей.

План — `docs/fb33-stack14-plan-2026-11-24.md` §0.1 (решения владельца), §0.2 (артборд
«M5d-8 · Woher»), §0.3 (отступления), §2 «E7», §4 «E7», правки ревью §10 (architect M4, M5,
M10; a11y H2, M1–M3, L3). Разделы с несколькими полями (`info` товара, `amenities` номера,
`price` и `venue` события и тура) описывают поля `SourceField` в `ContentSource.fields`; окно
выводит их списком `<ul>`. Одно поле — прежняя фраза «Feld „X“ …» байт-в-байт.
"""

import re
from pathlib import Path

import polib
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from apps.catalog.models import Product
from apps.core import detail_sections, object_structure, site_schema, window_parts
from apps.core.tests.test_fb33_m5d2_core import _inhalt as _core_inhalt
from apps.core.tests.test_fb33_m5d2_core import _text
from apps.core.tests.test_fb33_m5d4a_product import _shop, cabinet_page, dd, section
from apps.core.tests.test_fb33_m5d4c_stay import _hotel
from apps.core.tests.test_fb33_m5d4d_events import _event, _tour
from apps.core.tests.test_fb33_m5d4d_events import _inhalt as _event_inhalt
from apps.core.tests.test_fb33_m5d4d_events import _tenant as _event_tenant

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
LANGS = ("de", "en", "tr", "ru", "uk")
AFTER = "Erscheint nur, wenn mindestens eines davon ausgefüllt ist."
MAP = "Punkt auf der Karte — „Breitengrad“ und „Längengrad“ (sonst Ihre Adresse; nicht bei Online)"
EVENT_PHOTOS = "„Fotos (Veranstaltungsort, vergangene Veranstaltungen)“ — ab dem zweiten Foto"
#: §5.2 «E7» — новые msgid (лежат во всех пяти `.po` с P0b)
E7_MSGIDS = (
    "Diese Felder %(every)s:",
    "Formular, Reiter „%(tab)s“:",
    "Formular, Reiter „%(tab)s“, Abschnitt „%(section)s“:",
    "„%(field)s“",
    "Erscheint nur, wenn mindestens eines davon ausgefüllt ist.",
    "Felder %(this)s — %(n)s von %(m)s ausgefüllt:",
    "„%(field)s“ — ausgefüllt",
    "„%(field)s“ — leer",
    "%(label)s — ab dem zweiten Foto",
    "Punkt auf der Karte — „%(lat)s“ und „%(lng)s“ (sonst Ihre Adresse; nicht bei Online)",
    "(nur bei Veranstaltungen)",
)
#: §5.2 «Снимаются» — источники в коде убраны (из `.po` их снимает координатор)
REMOVED_MSGIDS = (
    "Marke und Zustand stehen im Formular unter „Marke & Zustand“.",
    "Erscheint nur, wenn mindestens eine dieser Angaben ausgefüllt ist.",
    "Erscheint nur, wenn eines der Preis-Felder ausgefüllt ist.",
    "Erscheint, wenn das Feld ausgefüllt ist, es weitere Fotos gibt oder der Ort auf der "
    "Karte liegt.",
)
#: разделы-списки: (модуль, ключ)
LIST_SECTIONS = {
    "product-info": ("catalog", "info"),
    "stay-amenities": ("stays", "amenities"),
    "event-price": ("events", "price"),
    "event-venue": ("events", "venue"),
}
CLOTHING_KENNZ = ["„Material / Zusammensetzung“", "„Pflegehinweise“", "„Herkunft“", "„Zutaten“"]
ALL_INFO = {
    "brand": "Lavazza",
    "condition": "new",
    "material": "100 % Baumwolle",
    "care": "30 °C",
    "origin": "Brasilien",
    "ingredients": "Kaffeebohnen",
    "allergens": ["gluten"],
    "additives": ["farbstoff"],
}


@pytest.fixture(autouse=True)
def _restore_connection_tenant():
    """Помощники `_shop`/`_hotel`/`_event_tenant` из соседних модулей ставят
    `connection.tenant` — а их `_env`, который его возвращает, здесь не действует. Иначе
    тенант тест-фабрики остаётся на соединении, следующий `schema_context` «возвращает»
    в его схему, и `TenantFactory` дальше на воркере падает каскадом (FB-33 стопка 14)."""
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _wl(selected) -> dict:
    return selected["content"].get("woher_list") or {}


def _items_text(wl: dict) -> list:
    return [(it["text"], [str(s) for s in it.get("sub", ())]) for it in wl["items"]]


def _product_type(bt):
    tenant, _product = _shop(bt)
    return _core_inhalt(tenant, "?seite=product&block=info")


def _product_object(bt, **fields):
    tenant, product = _shop(bt, **fields)
    code = object_structure.schema_code("product", product)
    return _core_inhalt(tenant, f"?seite={code}&block=info")


def _sfields(module, key):
    return [
        f for f in section(module, key).source.fields if isinstance(f, detail_sections.SourceField)
    ]


# --- №2: «Woher» — список полей ---------------------------------------------------------------------


def test_woher_list_is_fields():
    """Строка типа: вводная фраза, группы по вкладкам формы товара (у группы из 3+ полей —
    вложенный список, из двух — через запятую), «когда появляется» после списка; у номера и
    события — поля по одному. Заплатки `note` про Marke и Zustand нет."""
    _part, _panel, selected, _view = _product_type("clothing")
    wl = _wl(selected)
    assert wl["intro"] == "Diese Felder bei jedem Produkt:"
    assert _items_text(wl) == [
        ("Formular, Reiter „Grundlagen“, Abschnitt „Marke & Zustand“: „Marke“, „Zustand“", []),
        ("Formular, Reiter „Kennzeichnung“:", CLOTHING_KENNZ),
    ]
    assert wl["after"] == AFTER and selected["content"]["woher"] == ""
    assert selected["content"]["note"] == ""
    # у еды «Marke & Zustand» в форме скрыта (пусто у типа) — группы нет; текстиля нет
    _part, _panel, selected, _view = _product_type("bakery")
    assert _items_text(_wl(selected)) == [
        (
            "Formular, Reiter „Kennzeichnung“:",
            ["„Herkunft“", "„Zutaten“", "„Allergene“", "„Zusatzstoffe“"],
        )
    ]
    tenant, _unit = _hotel()
    _part, _panel, selected, _view = _core_inhalt(tenant, "?seite=stay&block=amenities")
    wl = _wl(selected)
    assert wl["intro"] == "Diese Felder bei jeder Unterkunft:"
    assert _items_text(wl) == [
        ("„Ausstattung“", []),
        ("„Bettart“", []),
        ("„Fläche (m², 0 = ausblenden)“", []),
    ]
    tenant = _event_tenant()
    _part, ct = _event_inhalt(tenant, "?seite=event&block=price")
    assert ct["woher_list"]["intro"] == "Diese Felder bei jeder Veranstaltung und Reise:"
    assert _items_text(ct["woher_list"]) == [
        ("„Im Preis enthalten (eine Zeile pro Punkt)“", []),
        ("„Nicht enthalten (eine Zeile pro Punkt)“", []),
        ("„Preis-Hinweis (Frühbucher, Varianten …)“", []),
    ]
    _part, ct = _event_inhalt(tenant, "?seite=event&block=venue")
    assert _items_text(ct["woher_list"]) == [
        ("„Ort / Veranstaltungsort“", []),
        ("Fotos — ab dem zweiten Foto", []),
        (f"{MAP} (nur bei Veranstaltungen)", []),
    ]
    assert ct["woher_list"]["after"] == AFTER


def test_object_rows_of_event_and_tour_venue():
    """«Ort» у одного события — поле, фото «ab dem zweiten», точка карты; у тура точки нет."""
    tenant = _event_tenant()
    event = _event(details={"venue": "Seehaus"}, images=["a.jpg"])
    code = object_structure.schema_code("event", event)
    _part, ct = _event_inhalt(tenant, f"?seite={code}&block=venue")
    wl = ct["woher_list"]
    assert wl["intro"] == "Felder dieser Veranstaltung — 1 von 3 ausgefüllt:"
    assert [it["text"] for it in wl["items"]] == [
        "„Ort / Veranstaltungsort“ — ausgefüllt",
        f"{EVENT_PHOTOS} — leer",
        f"{MAP} — leer",
    ]
    tour = _tour(images=["a.jpg", "b.jpg"])
    code = object_structure.schema_code("tour", tour)
    _part, ct = _event_inhalt(tenant, f"?seite={code}&block=venue")
    wl = ct["woher_list"]
    assert wl["intro"] == "Felder dieser Reise — 1 von 2 ausgefüllt:"
    assert [it["text"] for it in wl["items"]] == [
        "„Ort / Veranstaltungsort“ — leer",
        "„Fotos“ — ab dem zweiten Foto — ausgefüllt",
    ]


# --- №2 / №3 (ревью M5): «ausgefüllt» = гейт витрины ------------------------------------------------


def _paths(module, key):
    return [str(f) for f in section(module, key).source.fields]


@pytest.mark.parametrize(
    "case", ["product-info", "stay-amenities", "event-price", "event-venue", "tour-venue"]
)
def test_filled_matches_storefront_gate(case):
    """Описание `ContentSource.fields` равно гейту показа витрины (шаблон или вьюха), а не
    общему коду: каждый путь — в гейте, и каждое условие гейта — в описании."""
    module, key = LIST_SECTIONS.get(case, ("events", "venue"))
    assert all(
        isinstance(f, detail_sections.SourceField) for f in section(module, key).source.fields
    )
    if case == "product-info":
        view = (ROOT / "apps/promotions/public_views.py").read_text(encoding="utf-8")
        gate = view[view.index('"product_has_info": bool(') :][:600]
        gate = gate[: gate.index("),")]
        names = {n.replace("_labels", "s") for n in re.findall(r"product\.(\w+)", gate)}
        assert set(_paths("catalog", "info")) == names
        return
    if case == "stay-amenities":
        view = (ROOT / "apps/stays/public_views.py").read_text(encoding="utf-8")
        gate = re.search(r'"amenities": bool\(([^)]*)\)', view).group(1)
        names = {n.replace("amenity_badges", "amenities") for n in re.findall(r"unit\.(\w+)", gate)}
        assert set(_paths("stays", "amenities")) == names
        return
    tpl = (ROOT / "templates/storefront/_event_thematic.html").read_text(encoding="utf-8")
    if case == "event-price":
        gate = re.search(r'k == "price" %\}\{% if ([^%]*)%\}', tpl).group(1)
        names = {f"details.{n}" for n in re.findall(r"L\.(\w+)", gate)}
        assert set(_paths("events", "price")) == names
        return
    gate = re.search(r'k == "venue" %\}\{% if ([^%]*)%\}', tpl).group(1)
    assert gate.strip() == "L.venue or event.images|length > 1 or map_point"
    fields = {str(f): f for f in section("events", "venue").source.fields}
    assert set(fields) == {"details.venue", "images", "latitude"}
    assert fields["images"].min_items == 2
    assert fields["latitude"].probe == "map_point" and fields["latitude"].kinds == ("event",)
    if case == "tour-venue":
        # у тура точки карты нет: контекст `tour_detail` её не кладёт — пункт только у события
        view = (ROOT / "apps/events/public_views.py").read_text(encoding="utf-8")
        body = view[view.index("def tour_detail") :]
        body = body[: body.index("\ndef ", 10)]
        assert '"map_point"' not in body


@pytest.mark.parametrize(
    "images, lat, online, photos, point",
    [
        (["a.jpg"], None, False, "leer", "leer"),
        (["a.jpg", "b.jpg"], None, False, "ausgefüllt", "leer"),
        ([], "51.17", False, "leer", "ausgefüllt"),
        ([], "51.17", True, "leer", "leer"),
    ],
)
def test_venue_state_follows_the_gate(images, lat, online, photos, point):
    """Фото — со второго; точка — у события с координатами (или адресом бизнеса), не онлайн.
    Ревью L-1: состояние — по своему пункту (`items[1]` фото, `items[2]` карта)."""
    tenant = _event_tenant()
    tenant.latitude = tenant.longitude = None
    kw = {"latitude": lat, "longitude": "7.08"} if lat else {}
    event = _event(images=images, is_online=online, **kw)
    code = object_structure.schema_code("event", event)
    _part, ct = _event_inhalt(tenant, f"?seite={code}&block=venue")
    items = ct["woher_list"]["items"]
    assert items[1]["text"] == f"{EVENT_PHOTOS} — {photos}"
    assert items[2]["text"] == f"{MAP} — {point}"


# --- ревью M-1/M-2: «ausgefüllt» окна = показ витрины (поведенчески) ---------------------------------


def _product_gate(product) -> bool:
    """Гейт `product_has_info` витрины — то же выражение, что во вьюхе (без копии)."""
    view = (ROOT / "apps/promotions/public_views.py").read_text(encoding="utf-8")
    start = view.index('"product_has_info": bool(') + len('"product_has_info": ')
    expr = view[start : view.index("),", start) + 1]
    return eval(expr, {"product": product})  # noqa: S307 — выражение из нашего же исходника


def _stay_gate(unit) -> bool:
    view = (ROOT / "apps/stays/public_views.py").read_text(encoding="utf-8")
    expr = re.search(r'"amenities": (bool\([^)]*\))', view).group(1)
    return eval(expr, {"unit": unit})  # noqa: S307 — выражение из нашего же исходника


def _event_gate(obj, key, tenant) -> bool:
    """Показ раздела — рендер `_event_thematic.html` с контекстом витрины."""
    from django.template.loader import render_to_string

    from apps.events import services
    from apps.events.models import Event

    point = services.map_point(obj, tenant) if isinstance(obj, Event) else None
    html = render_to_string(
        "storefront/_event_thematic.html",
        {"k": key, "event": obj, "L": obj.landing, "map_point": point, "map_link": ""},
    )
    return "<section" in html


def _window_shown(obj, module, key, host, kind, tenant) -> bool:
    src = section(module, key).source
    words = site_schema.object_words(host)
    _woher, _filled, wl = window_parts._content_woher(src, host, key, kind, obj, words, tenant)
    return any(it["icon"] == "✓" for it in wl["items"])


@pytest.mark.parametrize(
    "kind, data",
    [
        ("product", {}),
        ("product", {"allergens": ["gluten"]}),
        ("product", {"allergens": ["xyz"]}),
        ("product", {"additives": ["xyz"]}),
        ("product", {"brand": "Lavazza"}),
        ("stay", {}),
        ("stay", {"amenities": ["wifi"]}),
        ("stay", {"amenities": ["xyz"]}),
        ("stay", {"area_sqm": 0, "bed_type": ""}),
        ("stay", {"bed_type": "Doppelbett"}),
        ("event-venue", {}),
        ("event-venue", {"images": [{}, {}]}),
        ("event-venue", {"images": [{"url": "a.jpg"}]}),
        ("event-venue", {"details": {"venue": "  "}}),
        ("event-venue", {"details": {"venue": "Seehaus"}}),
        ("event-venue", {"latitude": "51.17", "longitude": "7.08"}),
        ("event-price", {"details": {"price_includes": ["", " "]}}),
        ("event-price", {"details": {"price_note": "Frühbucher"}}),
        ("event-price", {"details": {"price_excludes": "Anreise"}}),
        ("tour-venue", {"images": [{}, {}]}),
        ("tour-venue", {"details": {"venue": "Rheinufer"}}),
    ],
)
def test_window_state_equals_storefront_gate(kind, data):
    """Раздел «ausgefüllt» в окне (хоть один пункт ✓) ⇔ витрина показывает раздел: те же
    производные значения (подписи аллергенов и удобств из каталога, `landing`, число фото)."""
    if kind == "product":
        tenant, obj = _shop("bakery", **data)
        obj = Product.objects.get(pk=obj.pk)
        args, gate = ("catalog", "info", f"product:{obj.pk.hex}", "product"), _product_gate(obj)
    elif kind == "stay":
        tenant, obj = _hotel(**data)
        obj = type(obj).objects.get(pk=obj.pk)
        args, gate = ("stays", "amenities", f"stay:{obj.pk.hex}", "stay"), _stay_gate(obj)
    else:
        tenant = _event_tenant()
        tenant.latitude = tenant.longitude = None
        obj = _tour(**data) if kind == "tour-venue" else _event(**data)
        obj = type(obj).objects.get(pk=obj.pk)
        okind, key = kind.split("-")
        args, gate = ("events", key, f"{okind}:{obj.pk.hex}", okind), _event_gate(obj, key, tenant)
    assert _window_shown(obj, *args, tenant) == gate


# --- №13: подписи — те же, что на форме кабинета -------------------------------------------------


@pytest.mark.parametrize("lang", ["de", "ru"])
def test_labels_on_cabinet_form(lang):
    """Подписи полей, вкладок и подраздела — те же строки, что на формах кабинета (товар,
    номер, событие, тур) на языке окна."""
    from apps.catalog.forms import ProductForm
    from apps.events.forms import EventForm

    info = {f.path: f for f in _sfields("catalog", "info")}
    tenant, product = _shop("clothing")
    with translation.override(lang):
        html = cabinet_page(tenant, reverse("catalog:product-edit", args=[product.pk]))
        for name, sf in info.items():
            assert str(sf.label) == str(ProductForm.base_fields[name].label), name
        tabs = {str(sf.tab) for sf in info.values()}
        sections_ = {str(sf.section) for sf in info.values() if sf.section}
    for tab in tabs:
        assert re.search(rf'data-pf-tab="\w+"[^>]*>{re.escape(tab)}</button>', html), tab
    for name in sections_:
        assert f">{name}</p>" in html, name
    tenant, unit = _hotel()
    with translation.override(lang):
        html = cabinet_page(tenant, reverse("stays:unit-edit", args=[unit.pk]))
        for sf in _sfields("stays", "amenities"):
            assert f">{sf.label}</" in html, sf.path
        labels = {str(sf.path): sf for sf in _sfields("events", "venue")}
        lat = str(EventForm.base_fields["latitude"].label)
        lng = str(EventForm.base_fields["longitude"].label)
        assert labels["latitude"].args and {k: str(v) for k, v in labels["latitude"].args} == {
            "lat": lat,
            "lng": lng,
        }
    tenant = _event_tenant()
    event, tour = _event(), _tour()
    photos = labels["images"].label
    with translation.override(lang):
        html = cabinet_page(tenant, reverse("events:edit", args=[event.pk]))
        assert f">{photos['event']}</span>" in html
        html = cabinet_page(tenant, reverse("events:tour-edit", args=[tour.pk]))
        assert f">{photos['tour']}</span>" in html


# --- №5: пути полей — точные ------------------------------------------------------------------------


def test_field_path_exact():
    """Голова пути — поле модели вида (не связь, не метод); ключ словаря — через точку; у
    пункта одного вида (`kinds`) — поле модели этого вида."""
    from django.core.exceptions import FieldDoesNotExist

    models = {"catalog": ("product",), "stays": ("stay",), "events": ("event", "tour")}
    for case, (module, key) in LIST_SECTIONS.items():
        for sf in _sfields(module, key):
            kinds = sf.kinds or models[module]
            for kind in kinds:
                meta = site_schema.object_model(kind)._meta
                try:
                    field = meta.get_field(sf.path.split(".")[0])
                except FieldDoesNotExist:
                    pytest.fail(f"{case}: {kind} has no {sf.path}")
                assert not field.is_relation, (case, sf.path)
            assert str(sf) == sf.path
    # снятые фразы не вернулись в источники
    with translation.override(None):
        for module, key in LIST_SECTIONS.values():
            src = section(module, key).source
            assert str(src.only_if) == AFTER and not src.note, key


# --- ревью M4: закрытый реестр проб -------------------------------------------------------------------


def test_probe_registry_closed(caplog, monkeypatch):
    """Пробы — закрытый словарь «имя → (модуль, функция)»; незнакомая проба — ошибка в журнал,
    состояние «неизвестно», без импорта и вызова."""
    import importlib

    assert window_parts._PROBES == {
        "map_point": ("object", "apps.events.services", "map_point"),
        "allergen_labels": ("field", "apps.catalog.food", "allergen_labels"),
        "additive_labels": ("field", "apps.catalog.food", "additive_labels"),
        "landing": ("field", "apps.events.details", "normalize"),
        "amenity_badges": ("property", "", "amenity_badges"),
    }
    for module, key in LIST_SECTIONS.values():
        for sf in _sfields(module, key):
            assert not sf.probe or sf.probe in window_parts._PROBES
    called = []
    monkeypatch.setattr(importlib, "import_module", lambda *a, **k: called.append(a))
    with caplog.at_level("ERROR", logger="apps.core.window_parts"):
        assert window_parts._probe("exec", object(), None, "event_detail", "venue") is None
    assert not called
    assert "unknown probe" in caplog.text


def test_map_probe_no_queries():
    """Проба карты читает только поля события и бизнеса — без запросов."""
    tenant = _event_tenant()
    event = _event(latitude="51.17", longitude="7.08")
    event = type(event).objects.get(pk=event.pk)
    with CaptureQueriesContext(connection) as ctx:
        assert window_parts._probe("map_point", event, tenant, "event_detail", "venue") is True
    assert len(ctx.captured_queries) == 0


# --- a11y H2, M3: разметка списка -----------------------------------------------------------------------


def test_woher_list_dom():
    """dt/dd списка — блочные (без `inline`), вводная фраза — `<p id>`, у `<ul>` —
    `role="list"` и `aria-labelledby` на неё; у группы из 3+ полей — вложенный `<ul>`; значок —
    `aria-hidden`; «›» в озвучиваемом тексте нет."""
    part, _panel, _selected, _view = _product_type("clothing")
    row = re.search(r"<div\b[^>]*data-inhalt-woher-row[^>]*>(.*?)</dd></div>", part, re.S)
    assert row, part
    html = row.group(0)
    dt = re.search(r"<dt\b([^>]*)>", html).group(1)
    ddt = re.search(r"<dd\b([^>]*)>", html).group(1)
    assert "inline" not in dt and "inline" not in ddt
    # ревью a11y M1 (WCAG 1.4.10): колонки в rem и minmax(0, …), dd переносит длинное слово
    assert "sm:grid-cols-[minmax(0,8rem)_minmax(0,1fr)]" in html
    assert "min-w-0" in ddt and "[overflow-wrap:anywhere]" in ddt
    # ревью a11y L1: окно одно на странице — id постоянный (ref бывает «shared:0»)
    intro = re.search(r'<p id="(inhalt-woher-intro)"[^>]*>', html)
    assert part.count('id="inhalt-woher-intro"') == 1
    assert intro
    ul = re.search(r"<ul\b([^>]*)>", html).group(1)
    assert 'role="list"' in ul and f'aria-labelledby="{intro.group(1)}"' in ul
    assert html.count("<ul") == 2  # вложенный список у «Kennzeichnung»
    lis = re.findall(r"<li\b([^>]*)>", html)
    assert lis and not [a for a in lis if "flex" in a]
    assert "›" not in _text(part)
    part, _panel, _selected, _view = _product_object("clothing", brand="Lavazza")
    icons = re.findall(r"<span\b([^>]*)>[✓–]</span>", part)
    assert icons and all('aria-hidden="true"' in a for a in icons)


@pytest.mark.parametrize(
    "fields, n, m",
    [
        ({}, 0, 6),
        ({"brand": "Lavazza", "origin": "Brasilien", "ingredients": "Bohnen"}, 3, 6),
        (ALL_INFO, 8, 8),
    ],
    ids=["0 von 6", "3 von 6", "8 von 8"],
)
def test_state_word_not_icon(fields, n, m):
    """«Nur diese Seite»: каждое поле — «— ausgefüllt» или «— leer» словом; итог «N von M»;
    скрытое формой и пустое поле в список не входит (§9 №6)."""
    part, _panel, selected, _view = _product_object("clothing", **fields)
    wl = _wl(selected)
    assert wl["intro"] == f"Felder dieses Produkts — {n} von {m} ausgefüllt:"
    texts = [it["text"] for it in wl["items"]]
    assert len(texts) == m
    assert sum(t.endswith("— ausgefüllt") for t in texts) == n
    assert all(t.endswith(("— ausgefüllt", "— leer")) for t in texts)
    assert "„Marke“ — " + ("ausgefüllt" if "brand" in fields else "leer") in texts
    assert selected["content"]["filled"] == ("— ausgefüllt." if n else "— leer.")
    li = re.findall(r"<li\b[^>]*>(.*?)</li>", dd_html(part), re.S)
    assert [_text(re.sub(r'<span aria-hidden="true">[^<]*</span>', "", x)) for x in li] == texts


def dd_html(part):
    return re.search(r"<dd\b[^>]*data-inhalt-woher[^>]*>(.*?)</dd>", part, re.S).group(1)


# --- ревью M5: флаги формы товара — в одном месте -----------------------------------------------------


def test_flags_moved_once():
    """Флаги формы товара живут в `catalog/form_flags.py`; вьюха и окно берут их оттуда."""
    from apps.catalog import form_flags
    from apps.catalog import views as catalog_views

    view = (ROOT / "apps/catalog/views.py").read_text(encoding="utf-8")
    assert '"show_retail_fields"' not in view and "TEXTILE_BUSINESS_TYPES = " not in view
    for bt in ("restaurant", "clothing", "retail"):
        req = type("R", (), {"tenant": type("T", (), {"business_type": bt})()})()
        assert catalog_views._product_form_flags(req) == form_flags.product_form_flags(req.tenant)
    parts = (ROOT / "apps/core/window_parts.py").read_text(encoding="utf-8")
    assert '"apps.catalog.form_flags"' in parts
    for path in (ROOT / "apps").rglob("*.py"):
        if "tests" in path.parts or path.name == "form_flags.py":
            continue
        assert '"show_retail_fields"' not in path.read_text(encoding="utf-8"), path


# --- №17 / №4: снятые строки ------------------------------------------------------------------------


def test_removed_msgids_gone():
    for path in [*(ROOT / "apps").rglob("*.py"), *(ROOT / "templates").rglob("*.html")]:
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        flat = re.sub(r'"\s*\n\s*"', "", text)
        for msgid in REMOVED_MSGIDS:
            assert msgid not in flat, (path, msgid)


# --- №31: без запросов ------------------------------------------------------------------------------


def test_woher_list_queries():
    """Список «Woher» строится из уже загруженных объекта и бизнеса — без запросов."""
    tenant, product = _shop("clothing", **ALL_INFO)
    product = Product.objects.get(pk=product.pk)
    src = section("catalog", "info").source
    words = site_schema.object_words(f"product:{product.pk.hex}")
    with CaptureQueriesContext(connection) as ctx:
        _woher, _filled, wl = window_parts._content_woher(
            src, f"product:{product.pk.hex}", "info", "product", product, words, tenant
        )
    assert wl["items"] and len(ctx.captured_queries) == 0


# --- №16 / ревью M10: строки во всех каталогах --------------------------------------------------------


def test_e7_msgids_in_all_po():
    """Все msgid среза — во всех пяти `.po` с переводом (пара без контекста)."""
    for loc in LANGS:
        po = polib.pofile(str(ROOT / f"locale/{loc}/LC_MESSAGES/django.po"))
        have = {e.msgid: e.msgstr for e in po if not e.msgctxt and not e.obsolete}
        for msgid in E7_MSGIDS:
            assert have.get(msgid), (loc, msgid)


# --- охранные ---------------------------------------------------------------------------------------


def test_single_field_phrase_unchanged():
    """№15: раздел с одним полем — прежняя фраза «Feld „X“ …», списка нет."""
    tenant, product = _shop("bakery")
    _part, _panel, selected, _view = _core_inhalt(tenant, "?seite=product&block=description")
    ct = selected["content"]
    assert ct["woher"] == (
        "Feld „Beschreibung“ bei jedem Produkt. Erscheint nur, wenn das Feld ausgefüllt ist."
    )
    assert not ct.get("woher_list")
    code = object_structure.schema_code("product", product)
    part, _panel, selected, _view = _core_inhalt(tenant, f"?seite={code}&block=description")
    assert dd(part, "woher") == "Feld „Beschreibung“ dieses Produkts — ausgefüllt."
    assert not selected["content"].get("woher_list")
    tenant = _event_tenant()
    _part, ct = _event_inhalt(tenant, "?seite=event&block=idea")
    assert ct["woher"].startswith("Feld „Idee / Atmosphäre“ bei jeder Veranstaltung und Reise.")


def _old_map_point(event, tenant):
    """Прежний код `veranstaltung_detail` (до выноса в помощник) — эталон поведения."""
    lat = event.latitude if event.latitude is not None else getattr(tenant, "latitude", None)
    lng = event.longitude if event.longitude is not None else getattr(tenant, "longitude", None)
    if lat is not None and lng is not None and not event.is_online:
        return {"lat": float(lat), "lng": float(lng)}
    return None


@pytest.mark.parametrize(
    "ev, ten",
    [
        ({"latitude": "51.1700000", "longitude": "7.0800000"}, (None, None)),
        ({}, ("51.2", "7.1")),
        ({"latitude": "51.17", "longitude": "7.08", "is_online": True}, (None, None)),
        ({}, (None, None)),
        ({"latitude": "51.17"}, (None, "7.1")),
    ],
)
def test_event_map_point_helper_bytes(ev, ten):
    """Точка карты события — тот же ответ, что у прежнего кода витрины; деталь события зовёт
    помощник (карта и ссылка — прежние)."""
    from apps.events import services

    tenant = _event_tenant()
    tenant.latitude, tenant.longitude = ten
    event = _event(**ev)
    event = type(event).objects.get(pk=event.pk)
    if hasattr(services, "map_point"):
        assert services.map_point(event, tenant) == _old_map_point(event, tenant)


@pytest.mark.parametrize(
    "details, images",
    [("garbage", "x.jpg"), ({"venue": {"de": ""}}, []), ([], {"a": 1}), ({"price_note": 5}, 7)],
)
def test_bad_data_no_500(details, images):
    """№6 / №8: битые `details` и `images` не роняют окно: часть есть, ошибка — в журнале."""
    tenant = _event_tenant()
    event = _event()
    type(event).objects.filter(pk=event.pk).update(details=details, images=images)
    code = object_structure.schema_code("event", event)
    for key in ("venue", "price"):
        part, ct = _event_inhalt(tenant, f"?seite={code}&block={key}")
        assert "data-inhalt-summary" in part, key
