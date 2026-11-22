"""FB-33 M5b-2 W3: Студия после слияния ★-строк.

План — `docs/fb33-stack10-plan-2026-11-22.md` §2.A W3, §4 таблица A (№2, №3), §8.1 (A-M3,
A-M5) и §8.2 (a11y Y-M4). Решение владельца 2026-11-22: имя главного списка — как у блока
«Liste» той же сущности + пометка «Hauptliste».

- строка главного списка панели Студии (`_cb_row.html`): имя `site_schema.main_list_name` и
  плашка «Hauptliste» (без ★); «wie die Liste aussieht» — ссылка на окно ★-строки страницы
  (`__page`, вкладка «Seite»), цель ≥ 24 px, подчёркнута, текст `text-gray-700` (контраст);
- ⚙ ключа страницы ведёт на ★-строку `__page` (`site_schema.settings_url`);
- `site-schema-open?block=__title` (Студия до деплоя) — окно `__page` на вкладке «Seite»;
- панель Студии не дороже по запросам, чем до среза (база 54c5961).
"""

import copy
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core import page_title, site_schema, views, window_links
from apps.core.tests.test_fb33_m4_window_links import _req as _open_req
from apps.core.tests.test_fb33_m4b_studio_dupes import _req
from apps.core.window_link_views import site_schema_open
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
ROW_TPL = ROOT / "templates" / "tenant" / "_cb_row.html"
PAGE = site_schema.PAGE_REF
#: страницы с основным списком среди своих блоков (Студия рисует строку «Hauptliste»)
CFG = {
    "page_blocks": {
        "services": [
            {"key": "text", "id": "s1", "enabled": True, "data": {"title": "Vorher"}},
            {"key": "main"},
        ],
        "catalog": [
            {"key": "main"},
            {"key": "text", "id": "c1", "enabled": True, "data": {"title": "Danach"}},
        ],
        "combos": [
            {"key": "main"},
            {"key": "text", "id": "m1", "enabled": True, "data": {"title": "Danach"}},
        ],
    }
}
#: число SQL GET панели Студии на базе 54c5961 (до M5b-2) — тот же тенант и CFG, замер
#: `test_studio_main_row_no_extra_queries` на копии `git archive 54c5961`
QUERIES_BASE = {"online_shop": 43, "restaurant": 51}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture(autouse=True)
def _restore_connection_tenant():
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _tenant(bt="online_shop", cfg=None):
    from apps.core.modules import default_disabled_for

    tenant = TenantFactory(business_type=bt, disabled_modules=list(default_disabled_for(bt)))
    tenant.site_config = copy.deepcopy(CFG if cfg is None else cfg)
    tenant.save()
    connection.tenant = tenant
    return tenant


def _studio(tenant) -> str:
    return views.home_builder_view(_req("get", "/dashboard/site/home/", tenant)).content.decode()


def _main_rows(html: str) -> dict[str, str]:
    """Строки «Hauptliste» панели Студии по хосту (`data-pb-page`): от строки до следующей
    строки или конца блока страницы."""
    out = {}
    for m in re.finditer(r'<div class="cb-row[^"]*"[^>]*data-pb-main-row[^>]*>', html):
        end = min(
            (i for i in (html.find('<div class="cb-row', m.end()),
                         html.find('class="page-block"', m.end()),
                         html.find("</fieldset>", m.end())) if i != -1),
            default=len(html),
        )  # fmt: skip
        host = re.search(r'data-pb-page="([^"]*)"', m.group(0)).group(1)
        out[host] = html[m.start() : end]
    return out


@pytest.mark.parametrize(("bt", "host", "name", "code"), [
    ("online_shop", "services", "Leistungen", "services"),
    ("online_shop", "catalog", "Produkte", "catalog"),
    ("online_shop", "combos", "Sets &amp; Pakete", "combos"),
    ("restaurant", "combos", "Menü-Pakete", "combos"),
])  # fmt: skip
def test_studio_main_row_name_and_badge(bt, host, name, code):
    rows = _main_rows(_studio(_tenant(bt)))
    assert host in rows, sorted(rows)
    row = rows[host]
    assert re.search(rf'<span class="font-medium">{re.escape(name)}</span>', row), row
    assert re.search(r'<span class="ui-badge ui-tone-run"[^>]*>Hauptliste</span>', row), row
    assert "★" not in row.replace('<span aria-hidden="true">★</span>', "")
    assert "text-gray-500" not in row


@pytest.mark.parametrize(("bt", "host", "code"), [
    ("friseur", "services", "services"),
    ("online_shop", "catalog", "catalog"),
])  # fmt: skip
def test_studio_main_row_links_to_page_window(bt, host, code):
    """«Wie die Liste aussieht» — ссылка на окно ★-строки страницы, вкладка «Seite»; цель
    ≥ 24 px, подчёркнута; ★ в имени окна скрыт от чтения. Ревью раунд 2 №2 (осознанно): у
    магазина ★-строки «Leistungen» нет (модуль записи выключен) — услуги берём у салона."""
    row = _main_rows(_studio(_tenant(bt)))[host]
    links = re.findall(r"<a [^>]*>.*?</a>", row, re.S)
    assert len(links) == 1, links
    link = links[0]
    href = re.search(r'href="([^"]+)"', link).group(1).replace("&amp;", "&")
    url = urlsplit(href)
    assert url.path == "/dashboard/site/aufbau/"
    assert parse_qs(url.query) == {"seite": [code], "block": [PAGE], "tab": ["seite"]}
    assert url.fragment == "schema-panel"
    cls = re.search(r'class="([^"]+)"', link).group(1).split()
    assert "underline" in cls
    assert {"min-h-[24px]", "min-h-[44px]"} & set(cls)
    assert '<span aria-hidden="true">★</span>' in link
    assert "Wie die Liste aussieht" in link
    assert "Blöcke davor stehen über der Liste, danach unter ihr." in row
    assert "text-gray-700" in row


def test_studio_row_template_has_no_bare_star():
    src = ROW_TPL.read_text(encoding="utf-8")
    assert "★ {% trans" not in src
    assert "stellen Sie oben bei dieser Seite ein" not in src


@pytest.mark.parametrize(("bt", "code", "key"), [
    ("friseur", "services", "services"),
    ("online_shop", "catalog", "pbhost:catalog"),
])  # fmt: skip
def test_studio_page_key_gear_opens_page_row(bt, code, key):
    """⚙ ключа самой страницы — ★-строка `__page` (через `settings_url`, W1)."""
    tenant = _tenant(bt)
    path = site_schema_path(tenant, code)
    assert path, code
    got = window_links.studio_settings_url(_open_req(tenant), path, key)
    assert got == site_schema.settings_url(code), got
    assert parse_qs(urlsplit(got).query)["block"] == [PAGE], got


def site_schema_path(tenant, code: str) -> str:
    from apps.tenants import siteconfig

    saved = siteconfig.normalize(tenant.site_config)
    rows = [r for _l, items in site_schema.type_groups(tenant, saved) for r in items]
    return next((r.preview_url for r in rows if r.code == code), "")


@pytest.mark.parametrize("tab", ["", "texte", "wie"])
def test_studio_open_title_alias_lands_on_seite(tab):
    """A-M5: `site-schema-open?block=__title` (Студия до деплоя) — окно `__page`, вкладка
    «Seite», какую бы вкладку ни прислали."""
    tenant = _tenant("friseur")
    path = site_schema_path(tenant, "services")
    query = {"page": path, "block": page_title.TITLE_REF}
    if tab:
        query["tab"] = tab
    resp = site_schema_open(_open_req(tenant, query))
    assert resp.status_code == 302
    url = urlsplit(resp["Location"])
    assert parse_qs(url.query) == {"seite": ["services"], "block": [PAGE], "tab": ["seite"]}


@pytest.mark.parametrize("bt", ["online_shop", "restaurant"])
def test_studio_main_row_no_extra_queries(bt):
    """№3: имя и ссылка главного списка — без новых запросов (≤ база 54c5961)."""
    tenant = _tenant(bt)
    _studio(tenant)  # прогрев кэшей
    with CaptureQueriesContext(connection) as ctx:
        _studio(tenant)
    assert len(ctx.captured_queries) <= QUERIES_BASE[bt], len(ctx.captured_queries)
