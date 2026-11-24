"""FB-33 M5b-2 W1: окно ★-строки страницы (`__page`) — «Seitentitel und Seite».

План — `docs/fb33-stack10-plan-2026-11-22.md` §0 (M5bWindow), §2.A W1, §4 таблица A, §8.1
(architect: A-H1, A-H2, A-H3, A-M7) и §8.2 (a11y: Y-M1, Y-M2, Y-M5…M9); решения владельца
2026-11-22 (`project-memory.md` §1 «Решения владельца стопки 10»):

- на «Seite» сверху вниз: `fieldset` «Überschrift der Seite» (Seitentitel · Einleitung ·
  Ausrichtung — та же форма `bw-form-fields`, переводы заголовка в ней же), `h4` «Einstellungen
  dieser Seitenart», настройки типа (метки групп — `h5`), строка-ссылка на вид списка;
- «Liste/Raster» листингов — настройки типа на ★-строке; у окна списка без своего вида —
  строка-ссылка туда (окно не пустое); строка «Darstellung … im Block › Wie anordnen» — только
  у списков со своим видом;
- строка наследования вида категории — в окне ★ категории, вкладка «Wie anordnen»; ссылка на
  форму категории — у ★-строки;
- подпись ★: «Seitentitel und Seite» только у `page_title.HEAD_HOSTS`, иначе «Einstellungen der
  Seite».
"""

import copy
import re
from collections import Counter
from urllib.parse import parse_qs, urlsplit

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import translation

from apps.core import aufbau_draft, block_window, page_title, page_window, site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import CFG, _capture, _panel
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

PAGE = site_schema.PAGE_REF
TITLE = page_title.TITLE_REF
#: число SQL окон до среза (замер на W0 38adbe1, тот же тенант и тот же прогрев): у услуг окно
#: «Seitentitel» + окно ★ (настройки типа); у каталога — окно ★
QUERIES_BEFORE = {"services": 14 + 30, "catalog_main": 36}


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


def _tabs(panel: str) -> list[tuple[str, bool]]:
    return [(k, not h) for k, h in re.findall(r'data-window-tab="([a-z]+)"( hidden)?', panel)]


def _category_shop(own_view=False):
    from apps.catalog.models import Category

    Category.objects.create(name={"de": "Brot"}, slug="brot")
    cfg = copy.deepcopy(CFG)
    cfg["page_blocks"]["category"] = [{"key": "main", "style": "magazin"}]
    if own_view:
        cfg["page_blocks"]["catalog:brot"] = [{"key": "main", "style": "mosaik"}]
    return _tenant("online_shop", cfg)


CATEGORY = "category@catalog:brot"


# ───────────── шапка и вкладки окна ★-строки ─────────────


@pytest.mark.parametrize(("bt", "code", "label"), [
    ("friseur", "services", "Seitentitel und Seite"),
    ("friseur", "contact", "Seitentitel und Seite"),
    ("online_shop", "promos", "Seitentitel und Seite"),
    ("online_shop", "catalog", "Einstellungen der Seite"),
    ("online_shop", "product", "Einstellungen der Seite"),  # было и до W1
])  # fmt: skip
def test_page_window_opens_on_seite(bt, code, label):
    panel = _panel(Browser(_tenant(bt)).get(f"?seite={code}&block={PAGE}"))
    assert re.search(rf'<h2 id="schema-panel-title"[^>]*>{label}</h2>', panel), code
    assert ("seite", True) in _tabs(panel), code
    assert 'value="window_done"' in panel


def test_seite_tab_dom_order():
    """Y-M2: `fieldset`+`legend` «Überschrift der Seite» (Seitentitel / Einleitung /
    Ausrichtung) → `h4` «Einstellungen dieser Seitenart» → настройки типа (метки групп — `h5`)."""
    seite = _section(_panel(Browser(_tenant()).get(f"?seite=services&block={PAGE}")), "seite")
    order = [
        seite.index("<fieldset"),
        seite.index("<legend"),
        seite.index("Überschrift der Seite"),
        seite.index('id="schema-f-title"'),
        seite.index('id="schema-f-intro"'),
        seite.index('id="schema-f-align"'),
        seite.index("</fieldset>"),
        seite.index("<h4"),
        seite.index("Einstellungen dieser Seitenart"),
        seite.index("data-schema-settings"),
    ]
    assert order == sorted(order)
    assert '<h3 class="text-sm font-bold' not in seite[seite.index("data-schema-settings") :], (
        "метки групп настроек под h4 — h5"
    )


def test_seite_tab_apply_form_none():
    """Y-M1: на «Seite» несколько форм — кнопки вкладок не применяют ни одну (ссылки)."""
    tenant = _tenant("online_shop", CFG)
    html, view, selected = _capture(Browser(tenant), f"?seite=promos&block={PAGE}")
    window = block_window.tabs(selected, view)
    assert any(t["key"] == "seite" and t["active"] for t in window)
    assert block_window.apply_form(window) is None
    panel = _panel(html)
    assert "data-window-default" not in panel and 'name="zu_tab"' not in panel
    if len(window) > 1:
        assert "data-window-hint" in panel, "без JS — подсказка «erst übernehmen»"


def test_title_form_apply_button_named():
    """Y-M1: «Übernehmen» формы заголовка — с sr-суффиксом «: Seitentitel» (на «Seite» не одна
    кнопка «Übernehmen»)."""
    seite = _section(_panel(Browser(_tenant()).get(f"?seite=services&block={PAGE}")), "seite")
    form = re.search(r'<form [^>]*id="bw-form-fields".*?</form>', seite, re.S).group(0)
    assert re.search(
        r'<button name="op" value="update" class="[^"]*">Übernehmen'
        r'<span class="sr-only">: Seitentitel</span></button>',
        form,
    )


@pytest.mark.parametrize("code", ["services", "contact", "catalog", "text"])
def test_no_duplicate_ids_on_page_tab(code):
    """Y-M9: без JS все вкладки окна в DOM — ни одного повторного `id` (поля заголовка,
    переводы, формы настроек). Ревью раунд 2 №11: и у страницы с SEO на «Texte» («Info»);
    SEO и заголовок на «Seite» вместе не бывают (`test_seo_hosts_and_head_hosts_disjoint`)."""
    bt = "online_shop" if code == "catalog" else "friseur"
    html = Browser(_tenant(bt, locales=["de", "en", "ru"])).get(f"?seite={code}&block={PAGE}")
    assert 'value="window_done"' in _panel(html), "окно ★-строки открыто"
    if code == "text":
        assert "f_seo_title" in _panel(html), "SEO на «Texte»"
    elif code != "catalog":
        assert 'id="schema-f-title"' in html and "f_tr_title_en" in html
    ids = Counter(re.findall(r'\sid="([^"]+)"', html))
    assert [i for i, n in ids.items() if n > 1] == []


def test_page_ref_title_fields_on_real_row():
    """A-H3 на настоящей ★-строке: подписи полей, потолки 120/400, пункты «Ausrichtung»."""
    seite = _section(_panel(Browser(_tenant()).get(f"?seite=services&block={PAGE}")), "seite")
    assert re.search(r'<label for="schema-f-title"[^>]*>Überschrift</label>', seite)
    assert re.search(r'<label for="schema-f-intro"[^>]*>Einleitung</label>', seite)
    assert re.search(r'<label for="schema-f-align"[^>]*>Ausrichtung</label>', seite)
    assert re.search(r'id="schema-f-title"[^>]*maxlength="120"', seite)
    assert re.search(r'id="schema-f-intro"[^>]*maxlength="400"', seite)
    assert re.search(r'<option value=""( selected)?>Links</option>', seite)
    assert '<option value="center">Zentriert</option>' in seite


def test_title_translations_on_seite():
    """Решение владельца: переводы заголовка — той же формой, что немецкое поле, на «Seite»."""
    panel = _panel(Browser(_tenant(locales=["de", "en"])).get(f"?seite=services&block={PAGE}"))
    seite = _section(panel, "seite")
    assert "f_tr_title_en" in seite
    assert "f_tr_title_en" not in panel.replace(seite, "")
    one = _panel(Browser(_tenant(locales=["de"])).get(f"?seite=services&block={PAGE}"))
    assert "f_tr_title" not in one


def test_title_edit_and_revert_in_page_window():
    b = Browser(_tenant())
    resp, _m = b.post(seite="services", ref=PAGE, op="update", panel_present="1",
                      f_title="Termine", f_align="center", wopen="openA1")  # fmt: skip
    assert parse_qs(urlsplit(resp["Location"]).query)["block"] == [PAGE]
    draft = b.session[aufbau_draft.SESSION_KEY]["services"]
    assert draft["title"] == {"title": "Termine", "align": "center"}
    assert set(draft[aufbau_draft.WINDOW_KEY]) == {PAGE}
    html = b.get(f"?seite=services&block={PAGE}&wopen=openA1")
    assert 'value="Termine"' in _section(_panel(html), "seite")
    _resp, msgs = b.post(seite="services", ref=PAGE, op="revert", wopen="openA1")
    assert "Änderungen an diesem Block zurückgenommen." in msgs
    assert "services" not in (b.session.get(aufbau_draft.SESSION_KEY) or {})


def test_switch_removed():
    """W1 включает слияние насовсем: переключателя `ON_PAGE_ROW` больше нет."""
    assert not hasattr(page_title, "ON_PAGE_ROW")
    assert site_schema.title_op("services", {}, "update", {"title": "x"}) == PAGE


def test_star_row_labels_ru():
    tenant = _tenant()
    cfg = siteconfig.normalize(tenant.site_config)
    with translation.override("ru"):
        head = page_window.pseudo_row(PAGE, PAGE, "services", cfg)
        detail = page_window.pseudo_row(PAGE, PAGE, "product_detail", cfg)
    assert head["label"] == "Заголовок и страница"
    assert detail["label"] == "Настройки страницы"
    assert detail["summary"] == "Заголовок = название записи"


# ───────────── H1: окно ★ списка не пустое ─────────────


def _main_window(tenant, code):
    html = Browser(tenant).get(f"?seite={code}&block={siteconfig.MAIN_LIST_KEY}")
    return _panel(html)


@pytest.mark.parametrize("bt", ["online_shop", "friseur", "hotel", "events"])
def test_every_main_window_not_empty(bt):
    """A-H1: у каждой ★ из `MAIN_LIST_HOSTS` (что есть у бизнеса) окно не пустое: свой вид
    («Wie anordnen») или строка-ссылка на ★-строку страницы (вкладка «Seite»)."""
    tenant = _tenant(bt)
    saved = siteconfig.normalize(tenant.site_config)
    rows = [r for _l, items in site_schema.type_groups(tenant, saved) for r in items]
    seen = set()
    for row in rows:
        if row.host not in siteconfig.MAIN_LIST_HOSTS:
            continue
        seen.add(row.host)
        panel = _main_window(tenant, row.code)
        assert 'value="window_done"' in panel, (bt, row.code)
        blocks = site_schema.blocks_for(saved, row.code, host=row.host, tenant=None)
        main = next(b for b in blocks if b.get("main"))
        own_view = bool(main.get("mainview") or main.get("groupview"))
        link = re.search(
            r'<a [^>]*href="([^"]*block=__page[^"]*)"[^>]*data-schema-page-link', panel
        )
        if own_view:
            assert "data-schema-page-link" not in panel, row.code
        else:
            assert link, (bt, row.code)
            assert "tab=seite" in link.group(1)
            assert re.search(r"Wie die Liste aussieht: in <span aria-hidden=\"true\">★</span>",
                             panel), row.code  # fmt: skip
    assert seen, bt


def test_own_view_list_link_on_page_tab():
    """Строка «Darstellung … im Block „…“ › Wie anordnen» — на «Seite» у списков со своим видом;
    у прочих — нет (вид — в настройках типа здесь же)."""
    shop = _tenant("online_shop")
    seite = _section(_panel(Browser(shop).get(f"?seite=catalog&block={PAGE}")), "seite")
    link = re.search(
        r'<a [^>]*href="([^"]+)"[^>]*data-schema-list-link[^>]*>(.*?)</a>', seite, re.S
    )
    assert link, "у каталога вид товаров — в окне ★"
    query = parse_qs(urlsplit(link.group(1).replace("&amp;", "&")).query)
    assert query["block"] == [siteconfig.MAIN_LIST_KEY] and query["tab"] == ["wie"]
    assert "Darstellung der Liste" in link.group(2) and "Wie anordnen" in link.group(2)
    services = _section(_panel(Browser(_tenant()).get(f"?seite=services&block={PAGE}")), "seite")
    assert "data-schema-list-link" not in services


# ───────────── H2: наследование вида категории и SEO-ссылка ─────────────


def test_category_inherit_on_star_wie():
    """A-H2: строка наследования — у ★ категории, вкладка «Wie anordnen»; ссылка «für alle
    ändern» — на ★ общей схемы категорий, вкладка «Wie anordnen»; у ★-строки её нет."""
    tenant = _category_shop(own_view=True)
    panel = _main_window(tenant, CATEGORY)
    wie = _section(panel, "wie")
    assert "data-schema-page-inherit" in wie
    assert "Wie bei allen Kategorie-Seiten: Magazin" in wie
    href = re.search(r'<a href="([^"]+)"[^>]*data-schema-inherit-link', wie).group(1)
    query = parse_qs(urlsplit(href.replace("&amp;", "&")).query)
    assert query["block"] == [siteconfig.MAIN_LIST_KEY] and query["tab"] == ["wie"]
    assert query["seite"] == [site_schema.CATEGORY]
    page = _panel(Browser(tenant).get(f"?seite={CATEGORY}&block={PAGE}"))
    assert "data-schema-page-inherit" not in page


def test_category_seo_link_on_page_row():
    """A-H2: ссылка на форму категории (заголовок для поисковиков) — у ★-строки, не у ★."""
    from apps.catalog.models import Category

    tenant = _category_shop()
    cat = Category.objects.get(slug="brot")
    page = _panel(Browser(tenant).get(f"?seite={CATEGORY}&block={PAGE}"))
    assert f"/catalog/categories/{cat.pk}/edit/" in page
    assert f"/catalog/categories/{cat.pk}/edit/" not in _main_window(tenant, CATEGORY)


def test_category_view_reset_and_cancel_on_star():
    """A-H2: «zurücksetzen» — `ref=main`; «Abbrechen» окна ★ возвращает свой вид."""
    tenant = _category_shop(own_view=True)
    b = Browser(tenant)
    b.get(f"?seite={CATEGORY}&block=main&wopen=openA1")
    _resp, msgs = b.post(seite=CATEGORY, op="view_reset", ref="main", wopen="openA1")
    assert not any("nicht möglich" in m for m in msgs)
    items = b.session[aufbau_draft.SESSION_KEY][CATEGORY]["items"]
    marker = next(i for i in items if i.get("key") == "main" and not i.get("id"))
    assert "style" not in marker
    _resp, msgs = b.post(seite=CATEGORY, op="revert", ref="main", wopen="openA1")
    assert "Änderungen an diesem Block zurückgenommen." in msgs
    wie = _section(_panel(b.get(f"?seite={CATEGORY}&block=main")), "wie")
    assert "hier geändert gilt nur für „Brot“: Mosaik" in wie


# ───────────── A-M7: ссылки на правило ─────────────


def test_links_to_page_row_use_rule():
    from apps.core import page_templates
    from apps.core.block_views import list_view

    for url in (site_schema.settings_url("services"), page_templates.cabinet_url("services")):
        assert parse_qs(urlsplit(url).query)["block"] == [PAGE], url
    line = list_view({"catalog_layout": {"preset": "cols3"}}, {"list_data": {"source": "products"}})
    query = parse_qs(urlsplit(line["link"]).query)
    assert query["block"] == [PAGE] and query["tab"] == ["seite"], line["link"]
    assert site_schema.settings_url("home").find("block=hero") != -1


# ───────────── №3: запросы окна ─────────────


def test_page_window_queries():
    """SQL окна ★-строки у услуг ≤ суммы прежних окон «Seitentitel» и ★; у ★ каталога — не
    больше прежнего (замер W0 — `QUERIES_BEFORE`)."""
    for bt, query, limit in (
        ("friseur", f"?seite=services&block={PAGE}", QUERIES_BEFORE["services"]),
        ("online_shop", "?seite=catalog&block=main", QUERIES_BEFORE["catalog_main"]),
    ):
        b = Browser(_tenant(bt))
        b.get(query)
        with CaptureQueriesContext(connection) as ctx:
            html = b.get(query)
        assert 'value="window_done"' in _panel(html), query
        assert len(ctx.captured_queries) <= limit, (query, len(ctx.captured_queries))
