"""FB-33 M5d-2: замки правок ревью диффа P0 (часть окна «Inhalt», ядро).

Задание — `docs/wip/fb33-stack12-p0-review-fixes.md` (номера пунктов — в докстрингах). Замки
реестра (`_source_errors`, `_field_errors`) читают ВЕСЬ `detail_sections.DETAIL_SECTIONS`:
источники разделов заводят срезы стопки 12, ядро их только проверяет.
"""

import logging
import re
import uuid
from urllib.parse import urlsplit

import pytest
from django.core.exceptions import FieldDoesNotExist
from django.db import connection
from django.urls import reverse
from django.utils import translation

from apps.catalog.models import Product
from apps.core import (
    aufbau_draft,
    content_pages,
    detail_parts,
    detail_sections,
    nav_registry,
    object_structure,
    site_schema,
    view_perms,
    window_parts,
)
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m5d1_inhalt import NO_RIGHT
from apps.core.tests.test_fb33_m5d2_core import (
    EMPTY,
    FILLED,
    VISIBLE,
    _description,
    _field_source,
    _inhalt,
    _req,
    _row,
    _shop,
    _source,
    _staff,
    _staff_part,
    _text,
    _with_source,
)

pytestmark = pytest.mark.django_db

KINDS = ("field", "setting", "page", "auto")
CORE = "apps.core.window_parts"


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    from apps.core import page_settings

    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr(page_settings, "_storefront_shows", lambda tenant, code: True)
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _object(product):
    return (
        object_structure.object_host("product", product),
        object_structure.schema_code("product", product),
    )


def _errors(caplog, logger=CORE):
    return [r for r in caplog.records if r.levelno >= logging.ERROR and r.name == logger]


# --- п. 1: сводка строки с источником — не статус строки ------------------------------------------


@pytest.mark.parametrize("status", ["Standard: sichtbar", "nur hier ausgeblendet"])
def test_summary_of_a_sourced_row_is_not_the_row_status(monkeypatch, status):
    """SFH-H1: у строки объекта `summary` — её статус («Standard: sichtbar»); в «Dieser Block
    zeigt» он не попадает: `source.shows`, иначе подпись раздела."""
    tenant, product = _shop()
    host, code = _object(product)
    _description(monkeypatch, shows="")
    section = next(s for s in detail_sections.sections_for("catalog") if s.key == "description")
    row = _row(summary=status)
    window_parts.content_part(row, host, _req(tenant), code=code)
    assert row["content"]["summary"] == str(section.label)
    assert "Standard:" not in row["content"]["summary"]
    assert "nur hier" not in row["content"]["summary"]
    # у типа — то же правило (сводка строки типа источнику не указ)
    row = _row(summary="3 Einträge")
    window_parts.content_part(row, "product_detail", _req(tenant), code="product")
    assert row["content"]["summary"] == str(section.label)
    _description(monkeypatch)
    row = _row(summary=status)
    window_parts.content_part(row, host, _req(tenant), code=code)
    assert row["content"]["summary"] == "die Beschreibung des Produkts"


# --- п. 1, 5: замки реестра источников ------------------------------------------------------------


def _sourced() -> list:
    return [
        (module, s)
        for module, sections in detail_sections.DETAIL_SECTIONS.items()
        for s in sections
        if s.source is not None
    ]


def _source_errors() -> list:
    """Что не так у источников реестра: вид, «zeigt», экран."""
    bad = []
    for module, s in _sourced():
        at = f"{module}/{s.key}"
        if s.source.kind not in KINDS:
            bad.append(f"{at}: kind {s.source.kind!r}")
        if not str(s.source.shows or "").strip():
            bad.append(f"{at}: shows is empty")
        if s.source.kind == "auto":
            continue
        if not s.content_nav:
            bad.append(f"{at}: {s.source.kind} without content_nav")
        elif nav_registry.entry_by_url(s.content_nav) is None:
            bad.append(f"{at}: no nav entry {s.content_nav!r}")
    return bad


def test_every_source_says_what_it_shows_and_where_it_is_edited():
    """SFH-H1, SFH-M4: у каждого `ContentSource` задан `shows`; у вида кроме `auto` есть
    `content_nav`, и `nav_registry.entry_by_url` его находит."""
    assert _source_errors() == []


def test_source_lock_sees_a_broken_registry(monkeypatch):
    """Замок реестра не пустой: битые источники он называет."""
    _with_source(monkeypatch, "catalog", "description", _field_source(shows=""), "")
    _with_source(monkeypatch, "catalog", "info", _field_source(), "nope:missing")
    _with_source(monkeypatch, "catalog", "recent", _source(kind="auto", shows="zuletzt"))
    assert _source_errors() == [
        "catalog/description: shows is empty",
        "catalog/description: field without content_nav",
        "catalog/info: no nav entry 'nope:missing'",
    ]


# --- п. 2: `_filled` — только поля модели и ключи словаря -----------------------------------------


def _kinds_of(module: str, section) -> list:
    kinds = [
        kind
        for kind, host in detail_parts.OBJECT_SHARED.items()
        if detail_parts.module_of(host) == module
    ]
    kinds = [k for k in kinds if not section.only or k == section.only]
    # M5d-2b: источник одного вида (`ContentSource.kinds`) — поля сверяем только у него
    only = section.source.kinds if section.source is not None else ()
    return [k for k in kinds if not only or k in only]


def _field_errors() -> list:
    """Пути `ContentSource.fields`, которых нет у модели вида (или это связь, а не поле)."""
    bad = []
    for module, s in _sourced():
        for kind in _kinds_of(module, s):
            meta = site_schema.object_model(kind)._meta
            for path in s.source.fields:
                head = str(path).split(".")[0]
                try:
                    field = meta.get_field(head)
                except FieldDoesNotExist:
                    bad.append(f"{module}/{s.key}: {kind} has no field {head!r}")
                    continue
                if field.is_relation:
                    bad.append(f"{module}/{s.key}: {kind}.{head} is a relation")
    return bad


def test_every_filled_path_is_a_model_field():
    """DJ-M1: каждый путь `fields` — поле модели вида (`_meta.get_field`), не связь, не метод."""
    assert _field_errors() == []


def test_field_lock_sees_a_broken_registry(monkeypatch):
    _description(monkeypatch, fields=("description.de", "get_absolute_url", "category"))
    assert _field_errors() == [
        "catalog/description: product has no field 'get_absolute_url'",
        "catalog/description: product.category is a relation",
    ]


def _filled_of(monkeypatch, tenant, product, fields):
    host, code = _object(product)
    _description(monkeypatch, fields=fields)
    row = _row()
    back = {"url": "/x/", "label": "Darjeeling"}
    window_parts.content_part(row, host, _req(tenant), code=code, obj=product, back=back)
    return row["content"]["filled"]


def test_filled_never_calls_a_callable(monkeypatch, caplog):
    """DJ-M1: метод объекта не вызывается (и свойство не читается) — путь не поле модели:
    в журнал, «заполнено ли» не утверждаем."""
    tenant, product = _shop()
    calls = []
    monkeypatch.setattr(Product, "boom", lambda self: calls.append(1) or "x", raising=False)
    with caplog.at_level(logging.ERROR, logger=CORE):
        assert _filled_of(monkeypatch, tenant, product, ("boom",)) == ""
    assert calls == []
    assert any("boom" in r.getMessage() for r in _errors(caplog))


def test_filled_relation_and_non_dict_are_configuration_errors(monkeypatch, caplog):
    """SFH-M1: связь вместо поля и ключ у значения, которое не словарь, — ошибка конфигурации:
    в журнал и пустое `filled` (раньше — молчаливое «leer»)."""
    tenant, product = _shop()
    for fields, word in ((("category",), "category"), (("base_price.de",), "base_price")):
        caplog.clear()
        with caplog.at_level(logging.ERROR, logger=CORE):
            assert _filled_of(monkeypatch, tenant, product, fields) == ""
        assert any(word in r.getMessage() for r in _errors(caplog)), fields


def test_filled_paths_of_model_fields(monkeypatch, caplog):
    """Поле модели и ключи словаря: нет ключа и пустое значение — «leer» без записи в журнале;
    хватает одного заполненного."""
    tenant, product = _shop(description={"de": "Fein", "en": "", "more": {"a": None}})
    with caplog.at_level(logging.ERROR, logger=CORE):
        assert _filled_of(monkeypatch, tenant, product, ("description.de",)) == FILLED
        assert _filled_of(monkeypatch, tenant, product, ("description.en",)) == EMPTY
        assert _filled_of(monkeypatch, tenant, product, ("description.nope",)) == EMPTY
        assert _filled_of(monkeypatch, tenant, product, ("description.nope.deeper",)) == EMPTY
        assert _filled_of(monkeypatch, tenant, product, ("description.more.a.b",)) == EMPTY
        assert _filled_of(monkeypatch, tenant, product, ("description.en", "name")) == FILLED
    assert not _errors(caplog)


# --- п. 3: цель без правила `view_perms` — закрыто ------------------------------------------------


def test_every_link_target_has_a_permission_rule():
    """SEC: у каждой цели ссылки «Inhalt» есть правило `view_perms` — формы объектов
    (`site_schema._OBJECT_EDIT_URLS`) и редакторы страниц (`content_pages.edit_url_for_code`)."""
    tenant, _product = _shop()
    from django.urls import resolve

    page_views = {resolve(urlsplit(content_pages.edit_url_for_code("text")).path).view_name}
    page_views |= {"content-page-edit", "content-page-system"}
    for name in (*site_schema._OBJECT_EDIT_URLS.values(), *sorted(page_views)):
        assert view_perms.rule_for(name) is not None, name


def test_target_without_a_rule_is_closed(monkeypatch, caplog):
    """SEC, SFH-L2: у цели нет правила (`rule_for` → None) — `view_perms.url_allowed` пускает
    любого; `screen_closed` отвечает «module» и пишет в журнал."""
    tenant, product = _shop()
    target = reverse("catalog:product-edit", args=[product.pk])
    real = view_perms.rule_for
    monkeypatch.setattr(
        view_perms, "rule_for", lambda name: None if name == "catalog:product-edit" else real(name)
    )
    with caplog.at_level(logging.ERROR, logger="apps.core.nav_registry"):
        closed = nav_registry.screen_closed(_req(tenant), "sellable-manage", target_url=target)
    assert closed == "module"
    assert any(
        "catalog:product-edit" in r.getMessage() for r in _errors(caplog, "apps.core.nav_registry")
    )


# --- п. 4: журнал там, где раньше было молча ------------------------------------------------------


def test_object_back_logs_a_route_that_does_not_reverse(monkeypatch, caplog):
    """SFH-M2: адрес формы объекта не строится — None и запись в журнале."""
    tenant, product = _shop()
    code = object_structure.schema_code("product", product)
    monkeypatch.setitem(site_schema._OBJECT_EDIT_URLS, "product", "nope:missing")
    with caplog.at_level(logging.ERROR, logger="apps.core.site_schema"):
        assert site_schema.object_back(code, product) is None
    assert any("nope:missing" in r.getMessage() for r in _errors(caplog, "apps.core.site_schema"))


def test_screen_closed_logs_a_target_that_does_not_resolve(caplog):
    """SFH-M3: цель не разбирается в экран — «module» и запись в журнале."""
    tenant, _product = _shop()
    with caplog.at_level(logging.ERROR, logger="apps.core.nav_registry"):
        closed = nav_registry.screen_closed(
            _req(tenant), "sellable-manage", target_url="/no/such/screen/"
        )
    assert closed == "module"
    assert any(
        "/no/such/screen/" in r.getMessage() for r in _errors(caplog, "apps.core.nav_registry")
    )


def test_object_without_a_back_link_is_logged(monkeypatch, caplog):
    """DJ-L1: объект есть, ссылки на его форму нет — без ссылки, но не молча."""
    tenant, product = _shop()
    host, code = _object(product)
    _description(monkeypatch)
    monkeypatch.setattr(site_schema, "object_back", lambda code, obj=None: None)
    row = _row()
    with caplog.at_level(logging.ERROR, logger=CORE):
        window_parts.content_part(row, host, _req(tenant), code=code, obj=product)
    assert row["content"]["link"] is None and row["content"]["reason"] == ""
    assert any("no form link" in r.getMessage() for r in _errors(caplog))


def test_unknown_closed_reason_is_logged(monkeypatch, caplog):
    """SFH-L3: `screen_closed` ответил кодом, для которого нет текста, — ссылки нет (экран
    закрыт), пустая причина — с записью в журнале."""
    tenant, _product = _shop()
    _description(monkeypatch)
    monkeypatch.setattr(nav_registry, "screen_closed", lambda request, name, target_url="": "odd")
    row = _row()
    with caplog.at_level(logging.ERROR, logger=CORE):
        window_parts.content_part(row, "product_detail", _req(tenant), code="product")
    assert row["content"]["link"] is None and row["content"]["reason"] == ""
    assert any("'odd'" in r.getMessage() for r in _errors(caplog))


# --- п. 6: «sichtbar — bei allen …» — только у типа -----------------------------------------------


def test_object_row_without_summary_is_just_visible(monkeypatch):
    """DJ-L2: у строки объекта без сводки — «sichtbar.»: «bei allen Produkten» говорит про тип."""
    tenant, product = _shop()
    host, code = _object(product)
    _description(monkeypatch)
    row = _row(summary="")
    window_parts.content_part(row, host, _req(tenant), code=code)
    assert row["content"]["visibility"] == VISIBLE
    row = _row(summary="")
    window_parts.content_part(row, "product_detail", _req(tenant), code="product")
    assert row["content"]["visibility"] == "sichtbar — bei allen Produkten."


# --- п. 7: подписи полей формы — один раз на процесс ----------------------------------------------


def test_field_labels_are_built_once(monkeypatch):
    """DJ-L3: форму объекта не строим на каждый показ окна — словарь подписей кэшируется на
    процесс; подпись остаётся ленивой (язык — в момент показа)."""
    from apps.events import landing

    real, calls = landing.form_fields, []
    monkeypatch.setattr(landing, "form_fields", lambda: calls.append(1) or real())
    site_schema._form_field_labels.cache_clear()
    try:
        with translation.override("de"):
            de = site_schema.object_field_label("event", "idea")
        with translation.override("ru"):
            ru = site_schema.object_field_label("tour", "idea")
            assert site_schema.object_field_label("event", "nope") == ""
        assert len(calls) == 1
        assert de == "Idee / Atmosphäre"
        with translation.override("ru"):
            assert ru == str(real()["idea"].label)
    finally:
        site_schema._form_field_labels.cache_clear()


# --- п. 10: `lang` — только когда язык содержимого не язык интерфейса ----------------------------


def test_lang_only_when_the_content_language_differs(monkeypatch):
    """a11y M2: имя объекта и страницы — на языке содержимого (`settings.LANGUAGE_CODE`):
    de-интерфейс — без `lang`, ru — `lang="de"`."""
    tenant, product = _shop()
    host, code = _object(product)
    _description(monkeypatch)
    _with_source(
        monkeypatch,
        "page",
        "pagetext",
        _source(kind="page", shows="den Text der Seite „%(page)s“"),
        "content-pages",
    )
    entry = nav_registry.entry_by_url("content-pages")
    from apps.core.models import ContentPage

    ContentPage.objects.create(slug="ab", title="A&B")  # своя страница: заголовок — содержимое

    def labels():
        row = _row()
        window_parts.content_part(row, host, _req(tenant), code=code)
        page = _row(ref="pagetext", key="pagetext", pinned=True, can_hide=False)
        window_parts.content_part(
            page, "seite:ab", _req(tenant), code="text@seite:ab", page_label="A&B"
        )
        return str(row["content"]["link"]["label"]), str(page["content"]["link"]["label"])

    with translation.override("de"):
        assert labels() == ("Darjeeling", f"{entry.label} › A&B")
    with translation.override("ru"):
        obj_label, page_label = labels()
        assert obj_label == '<span lang="de">Darjeeling</span>'
        assert page_label == f'{entry.label} › <span lang="de">A&amp;B</span>'


@pytest.mark.parametrize("lang, attr", [("de", False), ("ru", True)])
def test_lang_attribute_in_the_window(monkeypatch, lang, attr):
    tenant, product = _shop()
    _host, code = _object(product)
    _description(monkeypatch)
    with translation.override(lang):
        part, _panel, _selected, _view = _inhalt(tenant, f"?seite={code}&block=description")
    a = re.search(r"<a\b[^>]*data-inhalt-link[^>]*>(.*?)</a>", part, re.S)
    assert a and "Darjeeling" in a.group(1)
    assert ('lang="de"' in a.group(1)) is attr


# --- п. 11: подпись ссылки — одним `<span>`, перенос длинных слов ---------------------------------


def test_link_label_is_one_span_and_long_words_wrap(monkeypatch):
    """a11y M3, M4: подпись ссылки при источнике — один `<span>` внутри `<a>` (у `inline-flex`
    текст и вложенный `<span lang>` — разные flex-элементы, пробел между ними пропадает);
    абзац ссылки и абзац причины — `break-words`."""
    from apps.core import packages

    tenant, product = _shop()
    _host, code = _object(product)
    _description(monkeypatch)
    with translation.override("ru"):
        part, _panel, _selected, _view = _inhalt(tenant, f"?seite={code}&block=description")
    p = re.search(r"<p\b([^>]*)>\s*<a\b[^>]*data-inhalt-link[^>]*>(.*?)</a>", part, re.S)
    assert p and "break-words" in p.group(1)
    inner = p.group(2).strip()
    assert inner.startswith("<span>") and inner.endswith("</span></span>")
    assert _text(inner).endswith("Darjeeling")
    part, _panel, _selected, _view = _inhalt(tenant, "?seite=product&block=description")
    a = re.search(r"<a\b[^>]*data-inhalt-link[^>]*>(.*?)</a>", part, re.S)
    assert a.group(1).strip() == "<span>Inhalt bearbeiten: Sortiment</span>"
    monkeypatch.setattr(packages, "view_allowed", lambda t, name: name != "sellable-manage")
    part, _panel, _selected, _view = _inhalt(tenant, "?seite=product&block=description")
    reason = re.search(r"<p\b([^>]*data-inhalt-reason[^>]*)>", part)
    assert reason and "break-words" in reason.group(1)


def test_reason_of_a_reader_without_right_wraps(monkeypatch):
    """Причина «нет права» при источнике — тот же абзац с `break-words`."""
    tenant, _product = _shop()
    _description(monkeypatch)
    blind = _staff(["sortiment.view", "sortiment.edit", "sortiment.delete"])
    part = _staff_part(tenant, blind, "?seite=product&block=description")
    reason = re.search(r"<p\b([^>]*data-inhalt-reason[^>]*)>", part)
    assert NO_RIGHT in part and "break-words" in reason.group(1)


# --- п. 12: окно скрытой строки закрыто без правок — «Ausgeblendet» раскрыт ----------------------


@pytest.mark.parametrize("hide_first", [True, False])
def test_done_on_a_hidden_row_leaves_the_hidden_list_open(monkeypatch, hide_first):
    """a11y H1: окно открыто из «Ausgeblendet» и закрыто «Fertig» (Esc шлёт ту же операцию) без
    правок — адрес ведёт к ссылке строки, `details[data-schema-hidden]` раскрыт, ссылка строки
    в нём есть (фокус на неё ставит `aufbau.js`, без скриптов — якорь). Видимая строка
    «Ausgeblendet» не раскрывает."""
    tenant, _product = _shop()
    _description(monkeypatch)
    b = Browser(tenant)
    b.post(seite="product", ref="related", op="toggle", zeile="1")  # список скрытых не пуст
    if hide_first:
        b.post(seite="product", ref="description", op="toggle", zeile="1")
    token = aufbau_draft.new_token()
    html = b.get(f"?seite=product&block=description&wopen={token}")
    assert 'data-window-part="inhalt"' in html
    resp, _msgs = b.post(seite="product", ref="description", op="window_done", wopen=token)
    assert resp.status_code == 302
    target = urlsplit(resp["Location"])
    assert target.fragment == "schema-row-description"
    html = b.get(f"?{target.query}")
    assert 'data-window-part="inhalt"' not in html  # окно закрыто
    details = re.search(r"<details\b([^>]*data-schema-hidden[^>]*)>(.*?)</details>", html, re.S)
    assert details
    assert (" open" in details.group(1)) is hide_first
    assert ('id="schema-row-description"' in details.group(2)) is hide_first
    assert html.count('id="schema-row-description"') == 1


def test_module_anchor_stands_above_its_own_paragraph():
    """DJ-L4: якорь `# --- <module> ---` — прямо над абзацем своего модуля: между якорем и
    ключом `"<module>": (` только комментарии. Абзацы про номера, корзину и «Versand» стоят
    под своими якорями (раньше — под чужими)."""
    from pathlib import Path

    src = Path(detail_sections.__file__).read_text(encoding="utf-8").splitlines()
    for module in detail_sections.DETAIL_SECTIONS:
        at = src.index(f"    # --- {module} ---")
        own = next(i for i in range(at + 1, len(src)) if not src[i].strip().startswith("#"))
        assert src[own].strip().startswith(f'"{module}": ('), module
    where = {
        "stays.StayUnit": "stays",
        "cart_show_upsell": "cart",
        "Список снимается только галочкой": "versand",
    }
    for word, module in where.items():
        line = next(i for i, text in enumerate(src) if word in text and text.strip()[0] == "#")
        anchor = next(i for i in range(line, -1, -1) if src[i].startswith("    # --- "))
        assert src[anchor] == f"    # --- {module} ---", (word, src[anchor])


def test_ghost_object_host_still_has_no_link(monkeypatch):
    """Объекта нет — как и раньше: без ссылки, причины и «заполнено ли»."""
    tenant, _product = _shop()
    _description(monkeypatch)
    host = f"product:{uuid.uuid4().hex}"
    row = _row(summary="")
    window_parts.content_part(row, host, _req(tenant), code=f"product@{host}")
    ct = row["content"]
    assert ct["link"] is None and ct["reason"] == "" and ct["filled"] == ""
