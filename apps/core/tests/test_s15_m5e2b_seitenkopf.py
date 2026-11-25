"""FB-33 стопка 15 M5e-2b: «Seitenkopf», вариант A — H1 и «Einleitung» листингов на «Texte».

План — `docs/fb33-stack15-plan-2026-11-25.md` §0.2 M5eSeitenkopf (вариант A), §0.3 №3, §2
«M5e-2b», §4 «M5e-2b», §14.1 A4/A9/A10, §14.2 Y3/Y9. Замки первого коммита: где поведения ещё
нет — strict xfail.

- Один писатель шапки листинга — `page_title.head(config, host)` / `put_head(config, host,
  entry)`: `page_titles[host]` у `HEAD_HOSTS`, `catalog_title`/`catalog_intro` у каталога;
  черновик (`aufbau_draft._saved_state`, `_put_title`) зовёт его.
- Поля шапки ★-строки — на вкладке «Texte» у всех `HEAD_HOSTS` и каталога (одно правило
  `tab_of`); «Überschrift (H1)», «Einleitung», «Ausrichtung» — родные радио «Links»/«Mittig»
  в `fieldset`/`legend` (у каталога выравнивания нет — §0.3 №3).
- Вступление каталога хранит переносы строк (витрина — `whitespace-pre-line`), неизменённое
  старое значение не режется (A9).
- Перевод шапки каталога — как у блоков (`block_i18n.kinds`, A4).
- У категории — одна ссылка на её форму, «In der Kategorie bearbeiten →» (A10).
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.utils import translation

from apps.core import aufbau_draft, block_i18n, block_window, page_title, page_window, site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import _capture, _panel
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

PAGE = site_schema.PAGE_REF
WOPEN = "openK1"
#: замки первого коммита — поведения ещё нет (снимаются в коммите реализации)
RED = pytest.mark.xfail(strict=True, reason="M5e-2b: ещё нет")
LONG_TITLE = "Unser Sortiment " + "x" * 150  # 166 > TITLE_MAX
LONG_INTRO = "Zeile eins\nZeile zwei\n" + "y" * 450  # > INTRO_MAX, mit Umbrüchen


@pytest.fixture(autouse=True)
def _restore_connection_tenant():
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _tenant(bt="friseur", config=None, locales=None):
    tenant = TenantFactory(
        business_type=bt,
        disabled_modules=list(default_disabled_for(bt)),
        site_config=copy.deepcopy(config) if config is not None else {},
    )
    if locales is not None:
        tenant.enabled_locales = locales
        tenant.save()
    connection.tenant = tenant
    return tenant


def _section(panel: str, tab: str) -> str:
    start = panel.index(f'data-window-tab="{tab}"')
    end = panel.find("data-window-tab=", start + 20)
    return panel[start : end if end != -1 else len(panel)]


def _tabs(panel: str) -> list[str]:
    return re.findall(r'data-window-tab="([a-z]+)"', panel)


def _window(b, code, tab=""):
    return _panel(b.get(f"?seite={code}&block={PAGE}" + (f"&tab={tab}" if tab else "")))


def _saved(tenant) -> dict:
    return Tenant.objects.get(pk=tenant.pk).site_config or {}


def _post_head(b, code, **fields):
    data = {"seite": code, "ref": PAGE, "op": "update", "panel_present": "1", "wopen": WOPEN}
    data.update({f"f_{k}": v for k, v in fields.items()})
    return b.post(**data)


# ───────────── №1: один писатель шапки ─────────────


@RED
@pytest.mark.parametrize(
    ("host", "cfg", "entry"),
    [
        ("promos", {"page_titles": {"promos": {"title": "Deals"}}}, {"title": "Deals"}),
        (
            "services",
            {"page_titles": {"services": {"title": "Termine", "align": "center"}}},
            {"title": "Termine", "align": "center"},
        ),
        (
            "catalog",
            {"catalog_title": "Sortiment", "catalog_intro": "Frisch"},
            {"title": "Sortiment", "intro": "Frisch"},
        ),
    ],
)
def test_one_head_writer(host, cfg, entry):
    """`head` читает, `put_head` пишет; черновик зовёт их же (свой список не держит)."""
    assert page_title.head(cfg, host) == entry
    assert aufbau_draft._saved_state(cfg, False, host)["title"] == entry
    out = {}
    page_title.put_head(out, host, entry)
    assert page_title.head(out, host) == entry
    page_title.put_head(out, host, {})
    assert page_title.head(out, host) == {}
    assert "page_titles" not in out and not out.get("catalog_title")
    src = Path(aufbau_draft.__file__).read_text(encoding="utf-8")
    assert '"page_titles"' not in src and "catalog_title" not in src, "писатель — page_title"


@RED
def test_head_hosts_and_catalog_have_head():
    assert all(page_title.has_head(h) for h in page_title.HEAD_HOSTS)
    assert page_title.has_head("catalog")
    assert not page_title.has_head("category") and not page_title.has_head("catalog:brot")


# ───────────── №3: одно правило вкладки ─────────────


@RED
@pytest.mark.parametrize("host", [*page_title.HEAD_HOSTS, "catalog"])
def test_tab_rule_one_predicate(host):
    row = page_window.pseudo_row(PAGE, PAGE, host, {})
    assert site_schema.is_title_row(row, host)
    assert block_window.tab_of("fields", row) == "texte"
    assert "with_title" not in row


# ───────────── №14: H1 на «Texte» ─────────────


@RED
@pytest.mark.parametrize(("bt", "code"), [("friseur", "services"), ("online_shop", "catalog")])
def test_texte_tab_has_h1(bt, code):
    panel = _window(Browser(_tenant(bt)), code)
    assert _tabs(panel)[:2] == ["texte", "seite"], code
    texte = _section(panel, "texte")
    assert re.search(r'<label for="schema-f-title"[^>]*>Überschrift \(H1\)</label>', texte)
    assert re.search(r'<label for="schema-f-intro"[^>]*>Einleitung</label>', texte)
    assert 'id="schema-f-title"' not in _section(panel, "seite")


def test_page_window_still_opens_on_seite():
    panel = _window(Browser(_tenant()), "services")
    assert re.search(r'data-window-tab="seite"(?! hidden)', panel)


# ───────────── №22 / Y3: радио «Ausrichtung» ─────────────


@RED
def test_radio_group_named():
    texte = _section(_window(Browser(_tenant()), "services"), "texte")
    group = re.search(r"<fieldset[^>]*data-schema-align.*?</fieldset>", texte, re.S)
    assert group, "радио — своей группой"
    group = group.group(0)
    assert re.search(r"<legend[^>]*>Ausrichtung</legend>", group)
    radios = re.findall(r'<input type="radio"[^>]*>', group)
    assert len(radios) == 2
    assert all('name="f_align"' in r for r in radios)
    assert 'value=""' in radios[0] and "checked" in radios[0]
    assert 'value="center"' in radios[1]
    for rid, text in (("schema-f-align-left", "Links"), ("schema-f-align-center", "Mittig")):
        assert f'id="{rid}"' in group
        assert re.search(rf'<label for="{rid}"[^>]*min-h-\[44px\][^>]*>.*?{text}', group, re.S)
    assert "<select" not in texte and "Zentriert" not in texte


@RED
def test_catalog_has_no_align():
    """§0.3 №3: у каталога `catalog_title/intro` — верхние ключи, выравнивания нет."""
    texte = _section(_window(Browser(_tenant("online_shop")), "catalog"), "texte")
    assert "f_align" not in texte and "data-schema-align" not in texte


@RED
def test_radio_center_applies_without_js():
    b = Browser(_tenant())
    resp, _m = _post_head(b, "services", title="Termine", align="center")
    assert resp.status_code == 302 and "tab=texte" in resp["Location"]
    assert b.session[aufbau_draft.SESSION_KEY]["services"]["title"] == {
        "title": "Termine",
        "align": "center",
    }
    texte = _section(_window(b, "services", "texte"), "texte")
    assert re.search(r'<input type="radio"[^>]*value="center"[^>]*checked', texte)


# ───────────── Y9: на «Seite» нет пустой группы; легенда на «Texte» ─────────────


@RED
def test_no_empty_fieldset():
    panel = _window(Browser(_tenant()), "services")
    seite, texte = _section(panel, "seite"), _section(panel, "texte")
    assert "<fieldset" not in seite or "Überschrift der Seite" not in seite
    assert "Einstellungen dieser Seitenart" not in seite, "заголовок группы без соседа не нужен"
    assert re.search(r"<legend[^>]*>Überschrift der Seite</legend>", texte)
    for fs in re.findall(r"<fieldset[^>]*>(.*?)</fieldset>", seite, re.S):
        assert re.search(r"<(input|select|textarea|button)", fs), "пустой fieldset"


@RED
def test_no_aria_hidden_on_focusable():
    texte = _section(_window(Browser(_tenant(locales=["de", "ru"])), "services"), "texte")
    for tag in re.findall(r"<(?:a|button|input|select|textarea)\b[^>]*>", texte):
        if 'aria-hidden="true"' in tag:
            assert 'tabindex="-1"' in tag, tag


@RED
def test_default_button_comes_before_the_tab_buttons():
    panel = _window(Browser(_tenant()), "services", "texte")
    default = panel.index("data-window-default")
    first_tab_button = panel.index('name="zu_tab"')
    assert default < first_tab_button < panel.index('id="bw-form-fields"')
    tag = panel[panel.rindex("<button", 0, default) : panel.index(">", default) + 1]
    assert 'form="bw-form-fields" name="op" value="update"' in tag


# ───────────── №6 / A9: старые значения каталога ─────────────


@RED
def test_catalog_head_old_values():
    cfg = {"catalog_title": LONG_TITLE, "catalog_intro": LONG_INTRO}
    assert page_title.head(cfg, "catalog") == {"title": LONG_TITLE, "intro": LONG_INTRO}
    tenant = _tenant("online_shop", cfg)
    b = Browser(tenant)
    # неизменённое не режется: прислали то же самое (в т. ч. с \r\n из textarea)
    _post_head(b, "catalog", title=LONG_TITLE, intro=LONG_INTRO.replace("\n", "\r\n"))
    assert "catalog" not in (b.session.get(aufbau_draft.SESSION_KEY) or {}), "нет изменений"
    # правка вступления: переносы строк остаются, потолок — INTRO_MAX; заголовок не тронут
    _post_head(b, "catalog", title=LONG_TITLE, intro="Erste\r\nZweite  Zeile\n" + "z" * 500)
    draft = b.session[aufbau_draft.SESSION_KEY]["catalog"]
    assert draft["title"]["title"] == LONG_TITLE
    assert draft["title"]["intro"].startswith("Erste\nZweite  Zeile\n")
    assert len(draft["title"]["intro"]) == page_title.INTRO_MAX
    b.post(seite="catalog", op="save")
    saved = _saved(tenant)
    assert saved["catalog_title"] == LONG_TITLE
    assert saved["catalog_intro"].startswith("Erste\nZweite  Zeile\n")


# ───────────── №26: потолки ─────────────


@RED
@pytest.mark.parametrize(("bt", "code"), [("friseur", "services"), ("online_shop", "catalog")])
def test_caps(bt, code):
    b = Browser(_tenant(bt))
    texte = _section(_window(b, code), "texte")
    assert re.search(rf'id="schema-f-title"[^>]*maxlength="{page_title.TITLE_MAX}"', texte)
    assert re.search(rf'id="schema-f-intro"[^>]*maxlength="{page_title.INTRO_MAX}"', texte)
    _post_head(b, code, title="T" * 300, intro="I" * 900)
    draft = b.session[aufbau_draft.SESSION_KEY][code]["title"]
    assert len(draft["title"]) == page_title.TITLE_MAX
    assert len(draft["intro"]) == page_title.INTRO_MAX


# ───────────── №11: черновик до среза ─────────────


@RED
def test_old_draft_without_catalog_title_clean():
    """Черновик каталога, начатый до среза (в сохранённом состоянии не было `title`), — не
    конфликт: отпечаток без него."""
    cfg = siteconfig.normalize({"catalog_title": "Sortiment"})
    saved = aufbau_draft._saved_state(cfg, False, "catalog")
    assert saved["title"] == {"title": "Sortiment"}
    before = {k: v for k, v in saved.items() if k != "title"}
    old = {"host": "catalog", "home": False, "items": copy.deepcopy(saved["items"])}
    old["base"] = aufbau_draft._fingerprint(before)
    assert aufbau_draft._base_fingerprint(saved, cfg, old) == old["base"]


# ───────────── A4: перевод шапки каталога ─────────────


@RED
def test_catalog_title_translation_kind():
    assert "catalog_title" in siteconfig.TRANSLATABLE_KEYS
    assert "catalog_intro" in siteconfig.TRANSLATABLE_KEYS
    cfg = {"catalog_title": "Sortiment", "i18n": {"ru": {"catalog_title": "Ассортимент"}}}
    page = {"host": "catalog", "home": False, "items": [], "title": {"title": "Sortiment"}}
    assert block_i18n.kinds(page, PAGE) == ("title",)
    assert block_i18n.german(cfg, page, PAGE) == {"title": "Sortiment", "intro": ""}
    with override_settings(LANGUAGES=[("de", "Deutsch"), ("ru", "Русский")]):
        assert block_i18n.saved_for(cfg, page, PAGE).get("ru") == {"title": "Ассортимент"}
    out = copy.deepcopy(cfg)
    draft = {**page, "btr": {PAGE: {"ru": {"intro": "Свежее"}}}}
    block_i18n.apply(out, draft, False, "catalog")
    assert out["i18n"]["ru"]["catalog_intro"] == "Свежее"
    assert "page_titles" not in out["i18n"]["ru"]


@RED
def test_catalog_translation_in_window_and_storefront(settings):
    tenant = _tenant("online_shop", {"catalog_title": "Sortiment"}, locales=["de", "ru"])
    b = Browser(tenant)
    texte = _section(_window(b, "catalog"), "texte")
    assert "f_tr_title_ru" in texte
    _post_head(b, "catalog", title="Sortiment", tr_title_ru="Ассортимент")
    b.post(seite="catalog", op="save")
    saved = _saved(tenant)
    assert saved["catalog_title"] == "Sortiment"
    assert saved["i18n"]["ru"]["catalog_title"] == "Ассортимент"
    settings.ROOT_URLCONF = "config.urls_tenant"
    with translation.override("ru"):
        html = _products(saved)
    assert "Ассортимент" in html.split("</h1>")[0]


# ───────────── №13: витрина после «Speichern» с кэшем страниц ─────────────


def _products(cfg):
    from apps.core.tests.test_fb31p5_detail_golden import _req
    from apps.promotions import public_views

    req = _req("/sortiment/", cfg)
    req.tenant.business_type = "online_shop"
    return public_views.product_list(req).content.decode()


@RED
def test_catalog_h1_on_storefront(settings):
    from apps.core import pagecache

    with override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    ):
        cache.clear()
        tenant = _tenant("online_shop")
        b = Browser(tenant)
        _post_head(b, "catalog", title="Unser Brot", intro="Täglich\nfrisch")
        before = pagecache._sf_version(tenant.schema_name)
        b.post(seite="catalog", op="save")
        assert pagecache._sf_version(tenant.schema_name) > before
    saved = _saved(tenant)
    assert saved["catalog_title"] == "Unser Brot" and saved["catalog_intro"] == "Täglich\nfrisch"
    settings.ROOT_URLCONF = "config.urls_tenant"
    with translation.override("de"):
        html = _products(saved)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S).group(1)
    assert "Unser Brot" in h1
    assert "Täglich\nfrisch" in html


# ───────────── A10: одна ссылка на форму категории ─────────────


def _category_shop():
    from apps.catalog.models import Category

    tenant = _tenant("online_shop")
    cat = Category.objects.create(name={"de": "Brot"}, slug="brot")
    return tenant, cat


def test_category_link_to_form():
    from django.urls import reverse

    tenant, cat = _category_shop()
    panel = _window(Browser(tenant), "category@catalog:brot")
    url = reverse("catalog:category-edit", args=[cat.pk])
    assert panel.count(f'href="{url}"') == 1, "одна ссылка (A10)"
    texte = _section(panel, "texte")
    link = re.search(rf'<a href="{re.escape(url)}"[^>]*>(.*?)</a>', texte, re.S)
    assert link and link.group(1).strip() == "In der Kategorie bearbeiten →"
    assert "min-h-[44px]" in link.group(0)
    assert 'id="schema-f-title"' not in panel, "у категории своих полей шапки нет"


# ───────────── №16: строки во всех каталогах ─────────────


MSGIDS = (
    "Überschrift (H1)",
    "In der Kategorie bearbeiten →",
    "Ausrichtung",
    "Links",
    "Mittig",
    "Einleitung",
    "Überschrift der Seite",
)


@pytest.mark.parametrize("lang", ["de", "en", "tr", "ru", "uk"])
def test_m5e2b_msgids_in_all_po(lang):
    po = Path(f"locale/{lang}/LC_MESSAGES/django.po").read_text(encoding="utf-8")
    for msgid in MSGIDS:
        m = re.search(rf'^msgid "{re.escape(msgid)}"\nmsgstr "(.*)"$', po, re.M)
        assert m, (lang, msgid)
        assert lang == "de" or m.group(1), (lang, msgid)


@RED
def test_window_tabs_apply_fields_on_texte():
    """Без JS переход с «Texte» на «Seite» применяет форму шапки (кнопки вкладок)."""
    tenant = _tenant()
    html, view, selected = _capture(Browser(tenant), f"?seite=services&block={PAGE}&tab=texte")
    window = block_window.tabs(selected, view, "texte")
    form = block_window.apply_form(window)
    assert form and form["form"] == "bw-form-fields"
