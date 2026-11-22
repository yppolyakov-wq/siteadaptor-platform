"""FB-33 M5b-1: одно правило строки «Einstellungen der Seite» (`__page`) — `site_schema.page_row_ref`.

Замки C0 (план стопки 9 §1.B, §2 «B»), вид экрана не меняется:

L1 характеризация — по всем строкам «Seitentyp» (`type_groups`) и строке объекта (`object_row`)
у пяти типов бизнеса (de+en) правило экрана = оракул (правило вьюхи до среза, вписано сюда);
`data-schema-block="__page"` на экране ⇔ правило даёт `PAGE_REF`; новая функция = оракул; код
объекта → ""; мусорный `seite` → главная без окна.
L2 `window_links._refs` не считает `__page` строкой на главной и на странице без настроек.
L3 решение «есть ли `__page`» — только в `site_schema` (вьюха, окно, ссылки, стенд владельца не
повторяют правило; в `block_window` нет литерала).
L4 число запросов окна `__page` и ⚙ Студии — не больше замера до среза.
L5 строка `__page` открыта ⇒ окно (выбранная строка) есть — ветка шаблона без окна снесена.
L6 `block=__page` у страницы без настроек — «Block wählen» (детерминированный код, не skip).
"""

import copy
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

from apps.catalog.models import Product
from apps.core import site_schema, window_links
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import CFG, _panel
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
PAGE = site_schema.PAGE_REF
#: пять типов бизнеса стенда владельца (магазин, ресторан, салон, отель, ретрит)
TYPES = ("online_shop", "restaurant", "friseur", "hotel", "events")
#: страница без настроек типа и без «Design» — у всех пяти типов (замер плана, 2026-11-22)
NO_SETTINGS = "confirmation"
#: L4 — число запросов до среза (замер 2026-11-22 на коммите P0 4adb4e4)
QUERIES_PAGE_WINDOW = 27
QUERIES_STUDIO = {("home", "hero"): 0, ("text", "info"): 0}  # после прогрева — без запросов


@pytest.fixture(autouse=True)
def _restore_connection_tenant():
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _tenant(bt="online_shop", config=None):
    tenant = TenantFactory(
        business_type=bt,
        disabled_modules=list(default_disabled_for(bt)),
        site_config=copy.deepcopy(config) if config is not None else {},
    )
    connection.tenant = tenant
    return tenant


def _oracle(tenant, code: str, blocks: list[dict]) -> str:
    """Правило вьюхи `site_schema_views` до среза (FB-27 R4/V3, FB-31 P2), дословно."""
    try:
        has = bool(site_schema.setting_codes(tenant, code))
        has_design = bool(site_schema.design_codes(tenant, code))
    except site_schema.SchemaError:
        has = has_design = False
    if not (has or has_design):
        return ""
    carrier = next((b for b in blocks if b["main"]), None) or next(
        (b for b in blocks if b["ref"] == site_schema.settings_carrier(code)), None
    )
    return PAGE if carrier is None else carrier["ref"]


def _rows(tenant):
    """Все строки выбора «Seitentyp» и строка «Nur diese Seite» товара."""
    product = Product.objects.create(name={"de": "Darjeeling", "en": ""}, base_price="9.90")
    saved = siteconfig.normalize(tenant.site_config)
    rows = [r for _l, items in site_schema.type_groups(tenant, saved) for r in items]
    own = site_schema.object_row(saved, f"product@product:{product.pk.hex}")
    assert own is not None
    return saved, [*rows, own]


def _req(tenant):
    req = RequestFactory().get("/dashboard/site/aufbau/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


# ───────────── L1 / L5: характеризация правила по пяти типам бизнеса ─────────────


@pytest.mark.parametrize("bt", TYPES)
def test_screen_row_follows_the_view_rule(bt):
    """Экран: строка `__page` ⇔ оракул даёт `PAGE_REF`; открытая строка — с окном (L5);
    без строки адрес `block=__page` окна не открывает."""
    tenant = _tenant(bt)
    saved, rows = _rows(tenant)
    browser = Browser(tenant)
    kinds = set()
    for row in rows:
        blocks = site_schema.blocks_for(saved, row.code, host=row.host or None)
        want = _oracle(tenant, row.code, blocks)
        kinds.add("page" if want == PAGE else want and "carrier" or "none")
        html = browser.get(f"?seite={row.code}&block={PAGE}")
        panel = _panel(html)
        shown = 'data-schema-block="__page"' in html
        assert shown == (want == PAGE), (bt, row.code, want)
        if shown:
            assert 'data-schema-block="__page" aria-current="true"' in html, row.code
            assert 'value="window_done"' in panel, f"{row.code}: строка открыта — окно есть (L5)"
            assert re.search(r'id="schema-panel-title"[^>]*>Einstellungen der Seite<', panel)
        else:
            assert 'value="window_done"' not in panel, f"{row.code}: окна `__page` нет"
        if site_schema.is_object_code(row.code):
            assert want == "", "у объекта настроек типа нет"
    assert kinds == {"page", "carrier", "none"}, "все три исхода правила встречаются"


@pytest.mark.parametrize("bt", TYPES)
def test_page_row_ref_is_the_view_rule(bt):
    tenant = _tenant(bt)
    saved, rows = _rows(tenant)
    req = _req(tenant)
    for row in rows:
        blocks = site_schema.blocks_for(saved, row.code, host=row.host or None)
        want = _oracle(tenant, row.code, blocks)
        assert site_schema.page_row_ref(tenant, row.code, blocks) == want, (bt, row.code)
        # ⚙ Студии видит те же строки, что экран (L2 по всем страницам)
        host = row.host or ""
        assert (PAGE in window_links._refs(req, row.code, host)) == (want == PAGE), row.code
        # адрес настроек типа (без тенанта и строк) ведёт на ту же строку
        if want and not site_schema.is_object_code(row.code):
            static = site_schema.page_row_ref(None, row.code)
            assert static == want, (bt, row.code)


def test_page_row_ref_edges():
    tenant = _tenant()
    saved = siteconfig.normalize(tenant.site_config)
    ghost = "product@product:" + "0" * 32
    assert site_schema.page_row_ref(tenant, ghost, []) == ""
    assert site_schema.page_row_ref(tenant, "gibtsnicht", []) == "", "SchemaError — строки нет"
    assert site_schema.page_row_ref(tenant, NO_SETTINGS, []) == ""
    home = site_schema.blocks_for(saved, "home")
    assert site_schema.page_row_ref(tenant, "home", home) == "hero"
    assert site_schema.page_row_ref(tenant, "home", []) == PAGE, "нет «Banner» — строка `__page`"


def test_garbage_seite_opens_home_without_window():
    html = Browser(_tenant()).get(f"?seite=gibtsnicht&block={PAGE}")
    assert 'data-schema-block="__page"' not in html
    assert 'value="window_done"' not in _panel(html)


# ───────────── L2: `__page` у ⚙ Студии только там, где строка есть ─────────────


@pytest.mark.parametrize("code", ["home", NO_SETTINGS])
def test_window_links_refs_have_no_page_row_without_it(code):
    tenant = _tenant()
    host = "" if code == "home" else site_schema.host_for(code)
    assert PAGE not in window_links._refs(_req(tenant), code, host)


def test_window_links_refs_keep_the_page_row_where_it_is():
    tenant = _tenant()
    assert PAGE in window_links._refs(_req(tenant), "text", "info")


# ───────────── L3: правило — только в site_schema ─────────────


def test_rule_lives_only_in_site_schema():
    callers = (
        "apps/core/site_schema_views.py",
        "apps/core/page_window.py",
        "apps/core/window_links.py",
        "scripts/fb33_m3_9_owner_stand.py",
    )
    for rel in callers:
        src = (ROOT / rel).read_text()
        for name in ("settings_carrier(", "setting_codes(", "design_codes("):
            assert name not in src, f"{rel}: {name} — правило `__page` повторено"
    assert '"__page"' not in (ROOT / "apps/core/block_window.py").read_text()
    tpl = (ROOT / "templates/tenant/site_schema.html").read_text()
    assert "elif page_row.active" not in tpl, "недостижимая ветка панели без окна"


# ───────────── L4: запросов не больше, чем до среза ─────────────


def _shop():
    tenant = _tenant(config=CFG)
    Product.objects.create(name={"de": "Darjeeling", "en": ""}, base_price="9.90")
    return tenant


def test_page_window_queries_do_not_grow():
    browser = Browser(_shop())
    browser.get(f"?seite=text&block={PAGE}")  # сессия и кэши — до замера
    with CaptureQueriesContext(connection) as ctx:
        browser.get(f"?seite=text&block={PAGE}")
    assert len(ctx.captured_queries) <= QUERIES_PAGE_WINDOW


@pytest.mark.parametrize(("code", "ref"), sorted(QUERIES_STUDIO))
def test_studio_gear_queries_do_not_grow(code, ref):
    tenant = _shop()
    saved = siteconfig.normalize(tenant.site_config)
    rows = [r for _l, items in site_schema.type_groups(tenant, saved) for r in items]
    path = next(r for r in rows if r.code == code).preview_url
    req = _req(tenant)
    window_links.studio_settings_url(req, path, ref)
    with CaptureQueriesContext(connection) as ctx:
        url = window_links.studio_settings_url(_req(tenant), path, ref)
    assert "seite=" in url
    assert len(ctx.captured_queries) <= QUERIES_STUDIO[(code, ref)]


# ───────────── L6: страница без настроек — без строки и без окна ─────────────


def test_page_window_without_settings_has_no_row():
    tenant = _shop()
    try:
        has = site_schema.setting_codes(tenant, NO_SETTINGS) or site_schema.design_codes(
            tenant, NO_SETTINGS
        )
    except site_schema.SchemaError:
        has = True
    assert not has, f"у «{NO_SETTINGS}» появились настройки — взять другой код"
    html = Browser(tenant).get(f"?seite={NO_SETTINGS}&block={PAGE}")
    assert f'<option value="{NO_SETTINGS}" selected' in html, "страница открыта, не главная"
    assert 'data-schema-block="__page"' not in html
    assert 'value="window_done"' not in _panel(html)
