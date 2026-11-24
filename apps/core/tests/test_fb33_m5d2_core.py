"""FB-33 M5d-2 (P0 стопки 12): ядро части окна «Inhalt» — откуда содержимое блока и где оно
правится (тип страницы и один объект).

План — `docs/fb33-stack12-plan-2026-11-23.md` §2, §4 «P0», правки ревью §10 (A1–A13, Y1–Y8),
ответы владельца §11. Срез вводит только ядро: `detail_sections.ContentSource` и поле
`DetailSection.source`, `site_schema.OBJECT_WORDS` и `object_back(code, obj)`,
`nav_registry.screen_closed(…, target_url=)`, расширенную модель `window_parts.content_part` и
шаблон `_bw_inhalt.html`. Самих источников у разделов G1/G3/G4 здесь нет — тесты подставляют
`ContentSource` в реестр (`_with_source`).

Эталоны `golden_fb33m5d2/` сняты на базе `cf12834` ДО кода (пересъёмка — `FB33_M5D2_REGEN=1`,
только осознанно): восемь окон G2 и окно `product|related` типа — байт-в-байт до и после.
"""

import dataclasses
import json
import logging
import os
import re
import uuid
from pathlib import Path
from types import SimpleNamespace

import polib
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from apps.catalog.models import Product
from apps.core import (
    aufbau_draft,
    block_window,
    detail_parts,
    detail_sections,
    nav_registry,
    object_structure,
    site_schema,
    window_parts,
)
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import _capture, _panel
from apps.core.tests.test_fb33_m5d1_inhalt import G2, HINT, NO_RIGHT, _part
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = Path(__file__).parent / "golden_fb33m5d2"
REGEN = bool(os.environ.get("FB33_M5D2_REGEN"))

#: число SQL прогретого экрана объектной строки на базе `cf12834` (A6: после кода — не больше)
_QUERIES = GOLDEN / "queries.json"
BASE_OBJECT_QUERIES = json.loads(_QUERIES.read_text())["object_row"] if _QUERIES.exists() else 0

WOHER = "Woher:"
ON_PAGE = "Auf der Seite:"
ONLY_HERE = "nur hier"
FIXED = "Er gehört fest zur Seite und lässt sich nicht ausblenden oder verschieben."
ACT_HIDE_MOVE = "Ausblenden und Verschieben über „⋯“."
ACT_HIDE = "Ausblenden über „⋯“."
ACT_SHOW = "Schließen Sie das Fenster; dann „Einblenden“ unter „Ausgeblendet“."
VISIBLE = "sichtbar."
VISIBLE_ALL = "sichtbar — %(all)s."
HIDDEN = "ausgeblendet."
LMIV = "sichtbar — bei Lebensmitteln Pflicht (LMIV)."
FILLED = "— ausgefüllt."
EMPTY = "— leer."
ONLY_IF_FILLED = "Erscheint nur, wenn das Feld ausgefüllt ist."
FIELD_EVERY = "Feld „%(field)s“ %(every)s."
FIELD_THIS = "Feld „%(field)s“ %(this)s"
REASON_LINE = "Inhalt bearbeiten: %(screen)s — %(reason)s"
MSGIDS = (
    WOHER,
    ON_PAGE,
    ONLY_HERE,
    ACT_HIDE_MOVE,
    ACT_HIDE,
    ACT_SHOW,
    VISIBLE,
    VISIBLE_ALL,
    HIDDEN,
    LMIV,
    FILLED,
    EMPTY,
    ONLY_IF_FILLED,
    FIELD_EVERY,
    FIELD_THIS,
    REASON_LINE,
)
#: A11: слова вида объекта — формы и кто какую имеет («this» — только видам со своей схемой
#: объекта, `detail_parts.OBJECT_SHARED`)
WORD_FORMS = ("every", "this", "all")
EXTRA_KINDS = ("combo", "post")
#: якоря срезов стопки 12 в каждом `.po` (параллельные срезы пишут только после своего)
ANCHORS = ("m5d2", "m5d3", "m5d4a", "m5d4b", "m5d4c", "m5d4d", "m5d4e", "m5d5", "kinder")


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    from apps.core import page_settings

    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr(page_settings, "_storefront_shows", lambda tenant, code: True)
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _g2_tenant():
    tenant = TenantFactory(business_type="friseur", disabled_modules=[])
    connection.tenant = tenant
    return tenant


def _shop(bt="online_shop", description=None):
    tenant = TenantFactory(business_type=bt, disabled_modules=list(default_disabled_for(bt)))
    connection.tenant = tenant
    product = Product.objects.create(
        name={"de": "Darjeeling", "en": ""},
        base_price="9.90",
        description={"de": "Fein", "en": ""} if description is None else description,
    )
    return tenant, product


def _source(**kw):
    return detail_sections.ContentSource(**kw)


def _field_source(**kw):
    base = {
        "kind": "field",
        "shows": "die Beschreibung des Produkts",
        "field_label": "Beschreibung",
        "fields": ("description",),
        "only_if": ONLY_IF_FILLED,
    }
    return _source(**{**base, **kw})


def _with_source(monkeypatch, module, key, source, content_nav=None):
    """Подставить источник разделу реестра (самих записей срез P0 не добавляет)."""
    extra = {} if content_nav is None else {"content_nav": content_nav}
    sections = tuple(
        dataclasses.replace(s, source=source, **extra) if s.key == key else s
        for s in detail_sections.DETAIL_SECTIONS[module]
    )
    assert any(s.key == key for s in sections), (module, key)
    monkeypatch.setitem(detail_sections.DETAIL_SECTIONS, module, sections)


def _description(monkeypatch, **kw):
    _with_source(monkeypatch, "catalog", "description", _field_source(**kw), "sellable-manage")


def _req(tenant=None, user=None):
    return SimpleNamespace(tenant=tenant, user=user or SimpleNamespace(is_authenticated=True))


def _row(**kw):
    base = {
        "ref": "description",
        "key": "description",
        "label": "Beschreibung",
        "enabled": True,
        "pinned": False,
        "can_hide": True,
        "can_up": False,
        "can_down": False,
        "summary": "",
    }
    return {**base, **kw}


def _clean(panel: str) -> str:
    panel = re.sub(r'<input type="hidden" name="csrfmiddlewaretoken"[^>]*>', "", panel)
    panel = re.sub(r'<input type="hidden" name="wopen"[^>]*>', "", panel)
    return re.sub(r"&amp;wopen=[A-Za-z0-9_-]+", "", panel)


def _golden(name: str, got: str) -> None:
    path = GOLDEN / name
    if REGEN:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(got, encoding="utf-8")
    assert got == path.read_text(encoding="utf-8"), name


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def _inhalt(tenant, query):
    html, view, selected = _capture(Browser(tenant), query)
    return _part(_panel(html), "inhalt"), _panel(html), selected, view


# --- №15: G2 байт-в-байт; A1: окно «Seite» у `product|related` типа ----------------------------


@pytest.mark.parametrize("code", sorted(G2))
def test_g2_bytes_unchanged(code):
    """Восемь окон G2 — как на базе (зелёный и до кода, и после)."""
    html, _view, _selected = _capture(Browser(_g2_tenant()), f"?seite={code}&block={G2[code][0]}")
    _golden(f"g2/{code}.html", _clean(_panel(html)))


def test_product_related_on_type_as_before():
    """Окно «Ähnliche Produkte» типа (вкладка «Seite») — как на базе."""
    tenant, _product = _shop()
    html, _view, _selected = _capture(Browser(tenant), "?seite=product&block=related")
    _golden("product_related.html", _clean(_panel(html)))


def test_object_only_source_skips_the_type_row(monkeypatch):
    """A1: источник `object_only` — только строке объекта; у типа окно «Seite» байт-в-байт,
    части «Inhalt» нет."""
    tenant, product = _shop()
    _with_source(
        monkeypatch,
        "catalog",
        "related",
        _source(kind="auto", shows="ähnliche Produkte", woher="automatisch.", object_only=True),
    )
    html, _view, selected = _capture(Browser(tenant), "?seite=product&block=related")
    assert "content" not in selected
    _golden("product_related.html", _clean(_panel(html)))
    code = object_structure.schema_code("product", product)
    part, _panel_html, selected, _view = _inhalt(tenant, f"?seite={code}&block=related")
    assert selected["content"]["link"] is None and "Dieser Block zeigt" in part


# --- A3: реестр равен прежнему -------------------------------------------------------------------


def _registry() -> list:
    with translation.override(None):
        return [
            [module, s.key, str(s.label), s.hideable, s.orderable, s.in_place, s.only,
             s.content_nav]
            for module, sections in detail_sections.DETAIL_SECTIONS.items()
            for s in sections
        ]  # fmt: skip


def test_registry_equals_the_base():
    """A3: раскрытие генератора events и якоря модулей не меняют реестр — модули, порядок,
    ключи, подписи (msgid) и флаги как на базе."""
    got = json.dumps(_registry(), ensure_ascii=False, indent=1) + "\n"
    _golden("registry.json", got)


def test_registry_is_written_out_for_parallel_slices():
    """A3: у каждого модуля — свой комментарий-якорь, генератора events нет (срезы правят
    непересекающиеся куски); новых импортов в модуле нет. Источники разделов заводят срезы
    стопки 12 (ревью M5d-2, DJ-M2: условия «источников нет» здесь больше нет — их проверяют
    замки реестра `test_fb33_m5d2_review.py`)."""
    import ast

    src = (ROOT / "apps/core/detail_sections.py").read_text(encoding="utf-8")
    for module in detail_sections.DETAIL_SECTIONS:
        assert f"# --- {module} ---" in src, module
    tree = ast.parse(src)
    registry = next(
        n.value
        for n in tree.body
        if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "DETAIL_SECTIONS"
    )
    assert not [n for n in ast.walk(registry) if isinstance(n, ast.GeneratorExp | ast.BinOp)]
    imports = sorted(
        ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.Import | ast.ImportFrom)
    )
    assert imports == [
        "from dataclasses import dataclass",
        "from django.utils.translation import gettext_lazy as _",
    ]


# --- A11: слова вида объекта ---------------------------------------------------------------------


def test_object_words_keys():
    words = site_schema.OBJECT_WORDS
    assert set(words) == set(site_schema.OBJECT_KINDS) | set(EXTRA_KINDS)
    for kind, forms in words.items():
        own_schema = kind in detail_parts.OBJECT_SHARED
        assert set(forms) == set(WORD_FORMS if own_schema else ("every", "all")), kind
        for form, text in forms.items():
            assert type(text).__name__ == "__proxy__", (kind, form)  # gettext_lazy
            assert str(text).strip(), (kind, form)


# --- A4/A5/A12: `screen_closed(…, target_url=)` -------------------------------------------------


def test_screen_closed_checks_the_target_url(monkeypatch):
    """Видимость модуля — по записи экрана; пакет и право — по адресу цели (готовыми
    `packages.view_allowed` и `view_perms.url_allowed`); без цели — прежнее поведение."""
    from apps.core import packages, view_perms

    tenant, product = _shop()
    req = _req(tenant)
    target = reverse("catalog:product-edit", args=[product.pk])
    assert nav_registry.screen_closed(req, "sellable-manage", target_url=target) == ""
    seen = []
    monkeypatch.setattr(
        packages,
        "view_allowed",
        lambda t, name: seen.append(name) or name != "catalog:product-edit",
    )
    assert nav_registry.screen_closed(req, "sellable-manage", target_url=target) == "package"
    assert seen == ["catalog:product-edit"]  # пакет — по цели, не по записи
    assert nav_registry.screen_closed(req, "sellable-manage") == ""
    monkeypatch.setattr(packages, "view_allowed", lambda t, name: True)
    urls = []
    monkeypatch.setattr(
        view_perms, "url_allowed", lambda user, url, method="GET": urls.append(url) or False
    )
    assert nav_registry.screen_closed(req, "sellable-manage", target_url=target) == "perm"
    assert urls == [target]
    # запись не видна тенанту — «module», цель не спрашиваем
    assert nav_registry.screen_closed(req, "nope:missing", target_url=target) == "module"


def test_package_aktionen_opens_the_object_form_not_the_list():
    """A12: пакет «Aktionen» пускает к форме товара (`catalog:product-edit`), но не к списку
    «Sortiment» — ответ по цели и по записи расходится."""
    tenant, product = _shop()
    tenant.site_config = {**(tenant.site_config or {}), "profile": "aktionen"}
    req = _req(tenant)
    target = reverse("catalog:product-edit", args=[product.pk])
    assert nav_registry.screen_closed(req, "sellable-manage") == "package"
    assert nav_registry.screen_closed(req, "sellable-manage", target_url=target) == ""


# --- модель части: тип -----------------------------------------------------------------------------


def test_type_row_model(monkeypatch):
    """Строка типа: «zeigt» — из источника, «Woher» — поле и слово вида, видимость и действия —
    из флагов строки (без запросов), ссылка — запись списка."""
    tenant, _product = _shop()
    _description(monkeypatch)
    row = _row(can_up=True)
    with CaptureQueriesContext(connection) as q:
        window_parts.content_part(row, "product_detail", _req(tenant), code="product")
    assert len(q.captured_queries) == 0
    ct = row["content"]
    assert ct["summary"] == "die Beschreibung des Produkts"
    assert ct["woher"] == f"Feld „Beschreibung“ bei jedem Produkt. {ONLY_IF_FILLED}"
    assert ct["filled"] == ""
    assert ct["visibility"] == "sichtbar — bei allen Produkten."
    assert ct["actions"] == ACT_HIDE_MOVE
    assert ct["fixed"] is False and ct["note"] == "" and ct["reason"] == ""
    assert ct["link"] == {
        "label": "Sortiment",
        "url": reverse("sellable-manage"),
        "only_here": False,
    }


@pytest.mark.parametrize(
    "flags, visibility, actions",
    [
        ({"can_up": True}, "sichtbar — bei allen Produkten.", ACT_HIDE_MOVE),
        ({"can_down": True}, "sichtbar — bei allen Produkten.", ACT_HIDE_MOVE),
        ({}, "sichtbar — bei allen Produkten.", ACT_HIDE),
        ({"enabled": False}, HIDDEN, ACT_SHOW),
        ({"can_hide": False}, "sichtbar — bei allen Produkten.", ""),
        ({"pinned": True, "can_hide": False}, "", ""),
    ],
)
def test_visibility_and_actions_follow_the_row_flags(monkeypatch, flags, visibility, actions):
    """A13/Y4: тексты — из флагов строки; «Verschieben» только там, где строка двигается;
    «in der Liste» в действиях нет (список под окном инертен)."""
    tenant, _product = _shop()
    _description(monkeypatch)
    row = _row(**flags)
    window_parts.content_part(row, "product_detail", _req(tenant), code="product")
    ct = row["content"]
    assert (ct["visibility"], ct["actions"]) == (visibility, actions)
    assert ct["fixed"] is bool(flags.get("pinned"))
    assert "in der Liste" not in ct["actions"]


def test_auto_and_setting_sources(monkeypatch):
    """`auto` — без ссылки и без слова вида в видимости; `setting` — запись реестра с
    `query` и «› sub»; `note` — рядом со сводкой."""
    tenant, _product = _shop()
    _with_source(
        monkeypatch,
        "catalog",
        "recent",
        _source(kind="auto", shows="zuletzt angesehene Produkte", woher="automatisch."),
    )
    row = _row(ref="recent", key="recent")
    window_parts.content_part(row, "product_detail", _req(tenant), code="product")
    ct = row["content"]
    assert ct["link"] is None and ct["reason"] == ""
    assert (ct["woher"], ct["visibility"]) == ("automatisch.", VISIBLE)
    _with_source(
        monkeypatch,
        "catalog",
        "instore",
        _source(
            kind="setting",
            shows="Ihr Geschäft",
            woher="Ihre Geschäftsdaten.",
            query="?tab=lieferung",
            sub="Lieferung",
            note="Hinweis.",
        ),
        "settings",
    )
    row = _row(ref="instore", key="instore")
    window_parts.content_part(row, "product_detail", _req(tenant), code="product")
    ct = row["content"]
    entry = nav_registry.entry_by_url("settings")
    assert ct["link"]["label"] == f"{entry.label} › Lieferung"
    assert ct["link"]["url"] == reverse("settings") + "?tab=lieferung"
    assert ct["note"] == "Hinweis." and ct["link"]["only_here"] is False


def test_food_locked_info_says_lmiv(monkeypatch):
    """A7a: у еды «Zutaten/Allergene» не скрывается — текст LMIV, и у типа, и раньше сводки
    объекта."""
    tenant, product = _shop("bakery")
    _with_source(
        monkeypatch,
        "catalog",
        "info",
        _field_source(shows="Zutaten und Allergene", field_label="Zutaten"),
        "sellable-manage",
    )
    row = _row(ref="info", key="info", can_hide=False)
    window_parts.content_part(row, "product_detail", _req(tenant), code="product")
    assert row["content"]["visibility"] == LMIV and row["content"]["actions"] == ""
    host = object_structure.object_host("product", product)
    code = object_structure.schema_code("product", product)
    row = _row(ref="info", key="info", can_hide=False, summary="Standard: sichtbar")
    window_parts.content_part(row, host, _req(tenant), code=code)
    assert row["content"]["visibility"] == LMIV
    # не еда — обычный текст
    shop, _p = _shop()
    row = _row(ref="info", key="info")
    window_parts.content_part(row, "product_detail", _req(shop), code="product")
    assert row["content"]["visibility"] == "sichtbar — bei allen Produkten."


# --- модель части: объект --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "description, filled",
    [
        ({"de": "Fein", "en": ""}, FILLED),
        ({"de": "", "en": ""}, EMPTY),
        ({"de": "  "}, EMPTY),
        ({}, EMPTY),
    ],
)
def test_object_row_model(monkeypatch, description, filled):
    """Строка объекта: «Woher» — поле ЭТОГО объекта и заполнено ли; видимость — сводка строки;
    ссылка — форма объекта, подпись — его имя, «nur hier». Интерфейс на языке содержимого —
    имя без `lang` (ревью M5d-2, a11y M2; с `lang` — `test_fb33_m5d2_review.py`)."""
    tenant, product = _shop(description=description)
    _description(monkeypatch)
    host = object_structure.object_host("product", product)
    code = object_structure.schema_code("product", product)
    row = _row(summary="nur hier ausgeblendet", enabled=False)
    window_parts.content_part(row, host, _req(tenant), code=code)
    ct = row["content"]
    assert ct["woher"] == f"Feld „Beschreibung“ dieses Produkts {filled}"
    assert ct["filled"] == filled
    assert ct["visibility"] == "nur hier ausgeblendet." and ct["actions"] == ACT_SHOW
    assert ONLY_IF_FILLED not in ct["woher"]
    link = ct["link"]
    assert link["url"] == reverse("catalog:product-edit", args=[product.pk])
    assert link["only_here"] is True
    assert str(link["label"]) == "Darjeeling"


def test_details_field_path_and_missing_attribute(monkeypatch, caplog):
    """`fields` — путь через словарь поля модели (`description.idea`): нет ключа — «leer»; нет
    такого поля у модели объекта — в журнал, «заполнено ли» не утверждаем (окно живо).
    Ревью M5d-2 (DJ-M1): путь — только поле модели, не произвольный атрибут."""
    tenant, product = _shop()
    product.description = {"idea": "Ruhe", "empty": []}
    host = object_structure.object_host("product", product)
    code = object_structure.schema_code("product", product)
    back = {"url": "/x/", "label": "Darjeeling"}

    def filled(fields):
        _description(monkeypatch, fields=fields)
        row = _row()
        window_parts.content_part(row, host, _req(tenant), code=code, obj=product, back=back)
        return row["content"]["filled"]

    assert filled(("description.idea",)) == FILLED
    assert filled(("description.nope",)) == EMPTY
    assert filled(("description.empty", "description.idea")) == FILLED  # хватает одного
    with caplog.at_level(logging.ERROR, logger="apps.core.window_parts"):
        assert filled(("no_such_attribute",)) == ""
    assert any("no_such_attribute" in r.getMessage() for r in caplog.records)


def test_object_back_takes_the_resolved_object():
    """A6: `object_back(code, obj)` не ходит в базу; объект не от этого кода — резолв заново
    (ответ тот же, что без объекта)."""
    tenant, product = _shop()
    other = Product.objects.create(name={"de": "Assam", "en": ""}, base_price="5.00")
    code = object_structure.schema_code("product", product)
    plain = site_schema.object_back(code)
    with CaptureQueriesContext(connection) as q:
        assert site_schema.object_back(code, product) == plain
    assert len(q.captured_queries) == 0
    assert site_schema.object_back(code, other) == plain  # чужой объект не подменяет ссылку
    assert site_schema.object_back("product", product) is None
    assert plain["label"] == "Darjeeling"


def _warm_count(browser, query) -> int:
    browser.get(query)  # прогрев сессии и кэшей
    with CaptureQueriesContext(connection) as q:
        browser.get(query)
    return len(q.captured_queries)


def test_object_row_queries_as_on_the_base():
    """A6 / №3: экран объектной строки (без источника) — запросов не больше базы."""
    tenant, product = _shop()
    code = object_structure.schema_code("product", product)
    count = _warm_count(Browser(tenant), f"?seite={code}&block=description")
    if REGEN:
        _QUERIES.write_text(json.dumps({"object_row": count}) + "\n")
        return
    assert count <= BASE_OBJECT_QUERIES, count


def test_object_resolved_once(monkeypatch):
    """A6 / №3: с частью «Inhalt» на объектной строке — запросов не больше, чем на базе без
    неё: объект резолвится один раз (`object_back(code, obj)`), видимость — из флагов."""
    tenant, product = _shop()
    _description(monkeypatch)
    code = object_structure.schema_code("product", product)
    b = Browser(tenant)
    count = _warm_count(b, f"?seite={code}&block=description")
    assert "data-inhalt-link" in b.get(f"?seite={code}&block=description")
    assert count <= BASE_OBJECT_QUERIES, count


def test_inhalt_queries_on_the_type_row(monkeypatch):
    """№31: часть «Inhalt» строки типа стоит не больше одного запроса поверх экрана без неё."""
    tenant, _product = _shop()
    b = Browser(tenant)
    without = _warm_count(b, "?seite=product&block=description")
    _description(monkeypatch)
    assert _warm_count(b, "?seite=product&block=description") - without <= 1


# --- №5, №6: точный ref, чужой и пропавший объект -------------------------------------------------


def test_ref_exact(monkeypatch):
    """Часть получает только строка раздела с `ref == key`: общий блок объекта
    (`shared:<id>`), свой блок с тем же ключом и строка с похожим ref — нет."""
    tenant, _product = _shop()
    _description(monkeypatch)
    req = _req(tenant)
    for row in (
        _row(ref="shared:description"),
        _row(ref="description_2"),
        _row(ref="b1", cblock=True),
        _row(cblock=True),
    ):
        window_parts.content_part(row, "product_detail", req, code="product")
        assert "content" not in row, row["ref"]
    own = _row()
    window_parts.content_part(own, "product_detail", req, code="product")
    assert "content" in own


@pytest.mark.parametrize("ghost", ["missing", "wrong_kind", "garbage", "deleted"])
def test_foreign_or_missing_object_no_link(monkeypatch, ghost):
    """Мусорный hex, вид не совпал, удалённый объект: экран отвечает 200 (главной), ссылки на
    форму объекта нет."""
    tenant, product = _shop()
    _description(monkeypatch)
    code = {
        "missing": f"product@product:{uuid.uuid4().hex}",
        "wrong_kind": f"product@service:{product.pk.hex}",
        "garbage": "product@product:zzz",
        "deleted": object_structure.schema_code("product", product),
    }[ghost]
    if ghost == "deleted":
        product.delete()
    html = Browser(tenant).get(f"?seite={code}&block=description")
    assert "data-schema-block" in html  # экран построен
    assert "data-inhalt-link" not in html and "data-schema-object-back" not in html


def test_object_host_without_object_no_link(monkeypatch, caplog):
    """Модель: хост объекта есть, объекта нет — часть без ссылки и причины, запись в журнале."""
    tenant, _product = _shop()
    _description(monkeypatch)
    host = f"product:{uuid.uuid4().hex}"
    row = _row(summary="Standard: sichtbar")
    with caplog.at_level(logging.ERROR, logger="apps.core.window_parts"):
        window_parts.content_part(row, host, _req(tenant), code=f"product@{host}")
    ct = row["content"]
    assert ct["link"] is None and ct["reason"] == "" and ct["filled"] == ""
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


# --- №8: ошибки построения ссылки — в журнал ------------------------------------------------------


def test_link_errors_logged(monkeypatch, caplog):
    """Нет записи реестра у источника; адрес цели не строится; сбой проверки доступа — окно
    без ссылки и причины, запись в журнале (не молча)."""
    tenant, _product = _shop()
    req = _req(tenant)

    def part():
        row = _row()
        caplog.clear()
        with caplog.at_level(logging.ERROR, logger="apps.core.window_parts"):
            window_parts.content_part(row, "product_detail", req, code="product")
        ct = row["content"]
        assert ct["link"] is None and ct["reason"] == "" and ct["summary"]
        return [r for r in caplog.records if r.levelno >= logging.ERROR]

    _with_source(monkeypatch, "catalog", "description", _field_source(), "nope:missing")
    assert any("nope:missing" in r.getMessage() for r in part())
    _with_source(monkeypatch, "catalog", "description", _field_source(), "")
    assert part()  # у поля нет списка — ошибка конфигурации
    _description(monkeypatch)

    def boom(request, url_name, target_url=""):
        raise RuntimeError("boom")

    monkeypatch.setattr(nav_registry, "screen_closed", boom)
    assert any(r.exc_info for r in part())


def test_page_source_links_the_page_editor(monkeypatch, caplog):
    """`page`: адрес — `content_pages.edit_url_for_code(code)`, подпись «Seiten › <имя>»
    (имя страницы в `lang` — только при другом языке интерфейса, ревью M5d-2); страницы нет —
    без ссылки, с журналом."""
    from apps.core import content_pages

    tenant, _product = _shop()
    _with_source(
        monkeypatch,
        "info",
        "pagetext",
        _source(kind="page", shows="den Text der Seite „%(page)s“"),
        "content-pages",
    )
    entry = nav_registry.entry_by_url("content-pages")
    row = _row(ref="pagetext", key="pagetext", pinned=True, can_hide=False)
    window_parts.content_part(row, "info", _req(tenant), code="text", page_label="Über uns")
    ct = row["content"]
    assert ct["summary"] == "den Text der Seite „Über uns“"
    assert ct["link"]["url"] == content_pages.edit_url_for_code("text")
    assert str(ct["link"]["label"]) == f"{entry.label} › Über uns"
    assert ct["fixed"] is True and ct["visibility"] == "" and ct["link"]["only_here"] is False
    monkeypatch.setattr(content_pages, "edit_url_for_code", lambda code: "")
    row = _row(ref="pagetext", key="pagetext", pinned=True, can_hide=False)
    with caplog.at_level(logging.ERROR, logger="apps.core.window_parts"):
        window_parts.content_part(row, "info", _req(tenant), code="text", page_label="Über uns")
    assert row["content"]["link"] is None and row["content"]["reason"] == ""
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


# --- A2 / №28: право ссылки — открыть экран (GET) -------------------------------------------------


def _staff(remove, add=()):
    from apps.core.models import Membership
    from apps.core.tests.test_staff_walk import _user

    staff = _user(Membership.ROLE_STAFF)
    Membership.objects.filter(user=staff).update(
        permissions={"add": ["website.view", "website.edit", *add], "remove": list(remove)}
    )
    return staff


def _staff_part(tenant, user, query):
    from apps.core.tests.test_staff_walk import _open as walk_open

    resp = walk_open(f"/dashboard/site/aufbau/{query}", tenant, user)
    assert resp.status_code == 200
    return _part(_panel(resp.content.decode()), "inhalt")


def test_link_right_is_the_right_to_open_the_screen(monkeypatch):
    """A2 (ответ владельца §11): право ссылки — как у G2, открыть экран. Сотрудник без
    просмотра ассортимента — причина без ссылки; с просмотром, но без правки — ссылка."""
    tenant, product = _shop()
    _description(monkeypatch)
    code = object_structure.schema_code("product", product)
    blind = _staff(["sortiment.view", "sortiment.edit", "sortiment.delete"])
    reader = _staff(["sortiment.edit", "sortiment.delete"])
    for query in ("?seite=product&block=description", f"?seite={code}&block=description"):
        part = _staff_part(tenant, blind, query)
        assert "data-inhalt-link" not in part and "<a " not in part, query
        assert NO_RIGHT in part and "data-inhalt-reason" in part, query
        part = _staff_part(tenant, reader, query)
        assert "data-inhalt-link" in part and NO_RIGHT not in part, query


def test_page_link_right_follows_the_target(monkeypatch):
    """A5 / §9 №6: у текстовой страницы право — по адресу цели (`seiten.edit`), не только по
    пункту «Seiten»."""
    tenant, _product = _shop()
    _with_source(
        monkeypatch,
        "info",
        "pagetext",
        _source(kind="page", shows="den Text der Seite „%(page)s“"),
        "content-pages",
    )
    part = _staff_part(tenant, _staff(["seiten.edit"]), "?seite=text&block=pagetext")
    assert "data-inhalt-link" not in part and NO_RIGHT in part
    editor = _staff([], add=["seiten.edit"])
    part = _staff_part(tenant, editor, "?seite=text&block=pagetext")
    assert "data-inhalt-link" in part and NO_RIGHT not in part


# --- Y1–Y6: разметка -------------------------------------------------------------------------------


def test_inhalt_dom_order(monkeypatch):
    """Y1: «Dieser Block zeigt» → `<dl>` («Woher», «Auf der Seite») → ссылка → подсказка; обе
    строки — в одном `<dl>`, подпись — `<dt>`."""
    tenant, _product = _shop()
    _description(monkeypatch)
    part, _panel_html, selected, _view = _inhalt(tenant, "?seite=product&block=description")
    order = [
        part.index("data-inhalt-summary"),
        part.index("<dl"),
        part.index("data-inhalt-woher"),
        part.index("data-inhalt-visibility"),
        part.index("</dl>"),
        part.index("data-inhalt-link"),
        part.index("data-inhalt-hint"),
    ]
    assert order == sorted(order)
    assert part.count("<dl") == 1
    dts = [_text(d) for d in re.findall(r"<dt\b[^>]*>(.*?)</dt>", part, re.S)]
    assert dts == [WOHER, ON_PAGE]
    woher = re.search(r"<dd\b[^>]*data-inhalt-woher[^>]*>(.*?)</dd>", part, re.S)
    assert _text(woher.group(1)) == f"Feld „Beschreibung“ bei jedem Produkt. {ONLY_IF_FILLED}"
    vis = re.search(r"<dd\b[^>]*data-inhalt-visibility[^>]*>(.*?)</dd>", part, re.S)
    # действия — по флагам строки: раздел товара в этой схеме двигается
    moves = selected["can_up"] or selected["can_down"]
    assert selected["can_hide"]
    actions = ACT_HIDE_MOVE if moves else ACT_HIDE
    assert _text(vis.group(1)) == f"sichtbar — bei allen Produkten. {actions}"
    assert selected["content"]["actions"] == actions
    assert "break-words" in re.search(r"<dl\b[^>]*>", part).group(0)  # Y7
    assert "Dieser Block zeigt: die Beschreibung des Produkts." in _text(part)
    assert HINT in part


def test_g2_has_no_dl():
    """Y1: у G2 `<dl>` не выводится (вывод прежний)."""
    html, _view, _selected = _capture(Browser(_g2_tenant()), "?seite=loyalty&block=programs")
    part = _part(_panel(html), "inhalt")
    assert "<dl" not in part and "data-inhalt-woher" not in part


def test_window_without_tabs_has_no_empty_tablist(monkeypatch):
    """Y2: окно из одной части — без полосы вкладок и без пустого `role=tablist`; «Fertig» и
    «Abbrechen» есть; без скриптов раздел виден колонкой (Y8)."""
    tenant, _product = _shop()
    _description(monkeypatch)
    _part_html, panel, selected, view = _inhalt(tenant, "?seite=product&block=description")
    assert [t["parts"] for t in block_window.tabs(selected, view)] == [["inhalt"]]
    assert "data-window-tabs" not in panel and "tablist" not in panel
    assert 'value="window_done"' in panel and 'value="revert"' in panel
    sec = re.search(r'<section id="schema-tab-was"[^>]*>', panel)
    assert sec and " hidden" not in sec.group(0)
    assert "data-bw-preview" not in panel


@pytest.mark.parametrize("lang", ["de", "ru"])
def test_only_here_badge_after_the_link(monkeypatch, lang):
    """Y3: «nur hier» — отдельный `<span class="ui-badge">` ПОСЛЕ ссылки, не в её имени; у
    ссылки нет `aria-hidden` и `aria-label`; имя объекта — в `<span lang="de">`, когда
    интерфейс не на языке содержимого (ревью M5d-2, a11y M2)."""
    tenant, product = _shop()
    _description(monkeypatch)
    code = object_structure.schema_code("product", product)
    with translation.override(lang):
        part, _panel_html, _selected, _view = _inhalt(tenant, f"?seite={code}&block=description")
        badge_text = str(translation.gettext(ONLY_HERE))
    a = re.search(r"<a\b([^>]*)>(.*?)</a>", part, re.S)
    assert a and "data-inhalt-link" in a.group(1)
    assert "aria-hidden" not in a.group(1) and "aria-label" not in a.group(1)
    assert ('<span lang="de">Darjeeling</span>' in a.group(2)) is (lang == "ru")
    assert _text(a.group(2)).endswith("Darjeeling")
    assert "ui-badge" not in a.group(2) and badge_text not in _text(a.group(2))
    after = part[a.end() :]
    badge = re.search(r'<span class="ui-badge"([^>]*)>(.*?)</span>', after, re.S)
    assert badge and "data-inhalt-only-here" in badge.group(1)
    assert "aria-hidden" not in badge.group(1)
    assert _text(badge.group(2)) == badge_text
    assert after.index(badge.group(0)) < after.index("data-inhalt-hint")
    if lang == "ru":
        assert badge_text != ONLY_HERE and "Inhalt bearbeiten" not in part
    # у строки типа плашки нет
    part, _p, _s, _v = _inhalt(tenant, "?seite=product&block=description")
    assert "data-inhalt-only-here" not in part and 'lang="de"' not in part


def test_fest_only_when_pinned(monkeypatch):
    """Y5: «🔒 fest» и фраза «Er gehört fest…» — только у закреплённой строки, по одному
    разу; у обычной строки раздела их нет."""
    tenant, _product = _shop()
    _description(monkeypatch)
    part, _p, selected, _v = _inhalt(tenant, "?seite=product&block=description")
    assert not selected["pinned"]
    assert "data-inhalt-fixed" not in part and FIXED not in part and "🔒" not in part
    html, _view, selected = _capture(Browser(_g2_tenant()), "?seite=loyalty&block=programs")
    part = _part(_panel(html), "inhalt")
    assert selected["pinned"]
    assert part.count("data-inhalt-fixed") == 1 and part.count(FIXED) == 1


def test_reason_is_one_paragraph_without_a_link(monkeypatch):
    """Y6: причина при источнике — одним абзацем с контекстом «Inhalt bearbeiten: <Bildschirm>
    — <Grund>», без `<a>` и без `aria-disabled`; у G2 вывод прежний (только причина)."""
    from apps.core import packages

    tenant, _product = _shop()
    _description(monkeypatch)
    monkeypatch.setattr(packages, "view_allowed", lambda t, name: name != "sellable-manage")
    part, _p, selected, _v = _inhalt(tenant, "?seite=product&block=description")
    ct = selected["content"]
    assert ct["link"] is None and ct["screen"] == "Sortiment"
    para = re.search(r"<p\b[^>]*data-inhalt-reason[^>]*>(.*?)</p>", part, re.S)
    assert para and part.count("data-inhalt-reason") == 1
    assert _text(para.group(1)) == "Inhalt bearbeiten: Sortiment — Nicht in Ihrem Paket enthalten"
    assert "<a" not in para.group(1) and "aria-disabled" not in part
    assert "data-inhalt-link" not in part
    # G2: причина прежняя, без «Inhalt bearbeiten:»
    monkeypatch.setattr(packages, "view_allowed", lambda t, name: name != "promotions:loyalty-list")
    html, _view, selected = _capture(Browser(_g2_tenant()), "?seite=loyalty&block=programs")
    para = re.search(
        r"<p\b[^>]*data-inhalt-reason[^>]*>(.*?)</p>", _part(_panel(html), "inhalt"), re.S
    )
    assert _text(para.group(1)) == "Nicht in Ihrem Paket enthalten"
    assert selected["content"]["screen"] == ""


def test_hidden_row_window_says_how_to_show(monkeypatch):
    """Ответ владельца §11: у скрытой строки — текст, кнопки «Einblenden» в окне нет."""
    tenant, _product = _shop()
    _description(monkeypatch)
    b = Browser(tenant)
    b.post(seite="product", ref="description", op="toggle", zeile="1")
    html = b.get("?seite=product&block=description")
    part = _part(_panel(html), "inhalt")
    vis = re.search(r"<dd\b[^>]*data-inhalt-visibility[^>]*>(.*?)</dd>", part, re.S)
    assert _text(vis.group(1)) == f"{HIDDEN} {ACT_SHOW}"
    assert 'value="toggle"' not in part


# --- A8: окно без правок не оставляет черновика ---------------------------------------------------


@pytest.mark.parametrize("close", ["window_done", "revert"])
def test_open_and_close_without_edits_leaves_no_draft(monkeypatch, close):
    """Открыл окно «Inhalt» и закрыл («Fertig» или «Abbrechen») без правок — ни черновика, ни
    снимка окна в сессии."""
    tenant, _product = _shop()
    _description(monkeypatch)
    b = Browser(tenant)
    token = aufbau_draft.new_token()
    html = b.get(f"?seite=product&block=description&wopen={token}")
    assert 'data-window-part="inhalt"' in html
    resp, _msgs = b.post(seite="product", ref="description", op=close, wopen=token)
    assert resp.status_code == 302
    assert not b.session.get(aufbau_draft.SESSION_KEY)
    assert "data-schema-draft" not in b.get("?seite=product")


# --- №16: строки и якоря `.po` --------------------------------------------------------------------


def test_new_msgids_in_all_po():
    """Строки P0 и слова вида объекта есть во всех пяти каталогах (без дублей пары
    msgctxt/msgid), плейсхолдеры совпадают."""
    with translation.override(None):  # без языка ленивая строка отдаёт msgid
        words = [str(t) for f in site_schema.OBJECT_WORDS.values() for t in f.values()]
    assert "bei jedem Produkt" in words and len(words) == len(set(words)) == 21
    for lang in ("de", "en", "tr", "ru", "uk"):
        po = polib.pofile(str(ROOT / f"locale/{lang}/LC_MESSAGES/django.po"))
        entries = [e for e in po if not e.obsolete]
        pairs = [(e.msgctxt, e.msgid) for e in entries]
        assert len(pairs) == len(set(pairs)), lang
        have = {(e.msgctxt, e.msgid): e.msgstr for e in entries}
        for msgid in (*MSGIDS, *words):
            assert (None, msgid) in have, (lang, msgid)
            if lang != "de":
                assert have[(None, msgid)], (lang, msgid)
            got = have[(None, msgid)] or msgid
            names = sorted(re.findall(r"%\((\w+)\)s", msgid))
            assert sorted(re.findall(r"%\((\w+)\)s", got)) == names, (lang, msgid)


def test_po_anchors_for_parallel_slices():
    """У каждого среза стопки 12 — свой якорь-комментарий в каждом `.po`, по порядку, между
    якорями — пустая строка (срезы пишут только после своего)."""
    for lang in ("de", "en", "tr", "ru", "uk"):
        text = (ROOT / f"locale/{lang}/LC_MESSAGES/django.po").read_text(encoding="utf-8")
        at = [text.find(f"\n# fb33-stack-anchor-{name}\n") for name in ANCHORS]
        assert all(i >= 0 for i in at), (lang, at)
        assert at == sorted(at), lang
        for name in ANCHORS:
            assert text.count(f"# fb33-stack-anchor-{name}\n") == 1, (lang, name)
            assert f"\n\n# fb33-stack-anchor-{name}\n" in text, (lang, name)


# --- A10, A11: подпись поля из кода формы, вид объекта по хосту -----------------------------------


def test_field_label_comes_from_the_form_code(monkeypatch):
    """A10: где подпись поля есть в коде формы (блоки события и тура — `landing.form_fields`),
    источник хранит ИМЯ поля, а не копию подписи."""
    from apps.events import landing

    label = str(landing.form_fields()["idea"].label)
    assert site_schema.object_field_label("event", "idea") == label
    assert site_schema.object_field_label("tour", "idea") == label
    assert site_schema.object_field_label("event", "nope") == ""
    assert site_schema.object_field_label("product", "description") == ""
    tenant, _product = _shop()
    _with_source(monkeypatch, "events", "idea", _source(kind="field", field="idea"), "events:list")
    row = _row(ref="idea", key="idea")
    window_parts.content_part(row, "event_detail", _req(tenant), code="event")
    # M5d-2b: раздел обоих видов на общем типе событий и туров называет оба
    assert row["content"]["woher"] == f"Feld „{label}“ bei jeder Veranstaltung und Reise."


def test_word_kind_by_host():
    assert site_schema.word_kind("product_detail") == "product"
    assert site_schema.word_kind(f"product:{uuid.uuid4().hex}") == "product"
    assert site_schema.word_kind("event_detail") == "event"
    assert site_schema.word_kind("event_detail", "tour") == "tour"
    assert site_schema.word_kind(f"tour:{uuid.uuid4().hex}") == "tour"
    assert site_schema.word_kind("blog_post") == "post"
    assert site_schema.word_kind("combo_detail") == "combo"
    assert site_schema.word_kind("promo_detail") == "promo"
    assert site_schema.word_kind("cart") == "" and site_schema.word_kind("") == ""


def test_broken_source_leaves_the_row_without_the_part(monkeypatch, caplog):
    """Сбой сборки модели по источнику (битая строка формата) — экран 200, части нет, исключение
    в журнале."""
    tenant, _product = _shop()
    _description(monkeypatch, shows="%(nope)s und %(page)s")
    with caplog.at_level(logging.ERROR, logger="apps.core.window_parts"):
        html, _view, selected = _capture(Browser(tenant), "?seite=product&block=description")
    assert "content" not in selected and "data-schema-block" in html
    assert 'data-window-part="inhalt"' not in html
    assert any(r.exc_info for r in caplog.records)
