"""FB-33 стопка 16 E10: ⚙ Студии на `/versand/` и на своих страницах с любым слагом
(`docs/fb33-stack16-plan-2026-11-26.md` §2 «E10», §4 «E10»; roadmap S15-versand,
S15-versand-gear, S15-upper-slug).

- `/versand/` рисует блоки хоста `versand` (`orders.public_views._versand_flow`) — ⚙ ведёт на
  `text@versand`, а не на общий `text` («Über uns», хост `info`);
- своя страница со слагом `versand` без заказов открывается старым адресом `/seite/versand/`
  и рисует блоки `seite:versand` (`content_page_views.storefront_page`) — ⚙ её строки;
- слаг страницы — алфавит `SlugField` (A–Z, «_»): хост `seite:<slug>` принимается
  нормализацией (решение владельца 2026-11-26 — расширить регэксп, адреса не менять), и все
  читатели хоста своей страницы зовут ОДИН регэксп.
"""

import ast
import pathlib
from urllib.parse import parse_qs, urlsplit

import pytest

from apps.core import site_schema, studio_pages, window_links
from apps.core.tests.test_fb27_r2_draft import _tenant
from apps.core.tests.test_fb33_e1_von import OWN_BLOCK, _req
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _shop(blocks: dict, *slugs: str, orders: bool = True):
    from apps.core.models import ContentPage

    tenant = _tenant()
    if not orders:
        tenant.disabled_modules = [*tenant.disabled_modules, "orders"]
    tenant.site_config = {"page_blocks": blocks}
    tenant.save()
    assert tenant.is_module_active("orders") is orders
    for slug in slugs:
        ContentPage.objects.create(slug=slug, title=slug, body="<p>x</p>", is_published=True)
    return tenant


def _q(url: str) -> dict:
    return parse_qs(urlsplit(url).query)


# --- S15-versand -----------------------------------------------------------------------


def test_versand_route_block_host():
    """Хост блоков `/versand/` — тот, что рисует витрина (`versand`), не общий `info`."""
    assert studio_pages.resolve_page("/versand/").block_host == "versand"


def test_versand_gear_opens_versand_schema():
    """№6: ⚙ на `/versand/` — схема `text@versand`, его свой блок — окно этой строки."""
    tenant = _shop({"versand": [OWN_BLOCK]})
    assert site_schema.code_for_path(tenant, "/versand/") == "text@versand"
    page = window_links.studio_settings_url(_req(tenant), "/versand/")
    assert _q(page)["seite"] == ["text@versand"]
    url = window_links.studio_settings_url(_req(tenant), "/versand/", OWN_BLOCK["id"])
    assert _q(url)["seite"] == ["text@versand"] and _q(url)["block"] == [OWN_BLOCK["id"]]


def test_about_and_info_hosts_unchanged():
    """Негативный контроль: «Über uns» — общий `text` (хост `info`), главная и листинг —
    как прежде."""
    tenant = _shop({"info": [OWN_BLOCK]})
    assert studio_pages.resolve_page("/ueber-uns/").block_host == "info"
    assert site_schema.code_for_path(tenant, "/ueber-uns/") == site_schema.TEXT
    assert site_schema.code_for_path(tenant, "/") == "home"
    assert site_schema.code_for_path(tenant, "/sortiment/") == "catalog"
    url = window_links.studio_settings_url(_req(tenant), "/ueber-uns/", OWN_BLOCK["id"])
    assert _q(url)["seite"] == [site_schema.TEXT] and _q(url)["block"] == [OWN_BLOCK["id"]]


# --- S15-versand-gear ------------------------------------------------------------------


def test_versand_slug_page_gear_when_orders_off():
    """№6: без заказов своя страница `versand` живёт на `/seite/versand/` с блоками
    `seite:versand` — ⚙ её строки, не «Diesen Block finden Sie … nicht»."""
    tenant = _shop({"seite:versand": [OWN_BLOCK]}, "versand", orders=False)
    assert not site_schema.versand_shown(tenant)
    assert site_schema.code_for_path(tenant, "/seite/versand/") == "text@seite:versand"
    req = _req(tenant)
    url = window_links.studio_settings_url(req, "/seite/versand/", OWN_BLOCK["id"])
    assert _q(url)["seite"] == ["text@seite:versand"]
    assert _q(url)["block"] == [OWN_BLOCK["id"]]
    assert not list(req._messages)


def test_versand_slug_page_with_orders_is_versand():
    """Охранный: с заказами `/seite/versand/` уходит 301 на `/versand/` — там `text@versand`."""
    tenant = _shop({}, "versand")
    assert site_schema.code_for_path(tenant, "/versand/") == "text@versand"


# --- S15-upper-slug --------------------------------------------------------------------


@pytest.mark.parametrize("slug", ["Ueber_Uns", "x_2", "ABC"])
def test_upper_slug_page_gear(slug):
    """№5: слаг с заглавными и «_» (алфавит `SlugField`) — ⚙ есть и ведёт на свою строку."""
    tenant = _shop({f"seite:{slug}": [OWN_BLOCK]}, slug)
    assert site_schema.code_for_path(tenant, f"/{slug}/") == f"text@seite:{slug}"
    url = window_links.studio_settings_url(_req(tenant), f"/{slug}/", OWN_BLOCK["id"])
    assert _q(url)["seite"] == [f"text@seite:{slug}"]
    assert _q(url)["block"] == [OWN_BLOCK["id"]]


def test_upper_slug_host_kept_by_normalize():
    """№5: блоки и SEO хоста `seite:Ueber_Uns` переживают `normalize`; соседи `x`/`x_2`
    не путаются."""
    raw = {
        "page_blocks": {
            "seite:Ueber_Uns": [OWN_BLOCK],
            "seite:x": [{**OWN_BLOCK, "id": "bx"}],
            "seite:x_2": [{**OWN_BLOCK, "id": "bx2"}],
        },
        "seo": {"pages": {"seite:Ueber_Uns": {"title": "Wir"}}},
    }
    out = siteconfig.normalize(raw)
    blocks = out["page_blocks"]
    assert [b["id"] for b in blocks["seite:Ueber_Uns"]] == ["b1"]
    assert [b["id"] for b in blocks["seite:x"]] == ["bx"]
    assert [b["id"] for b in blocks["seite:x_2"]] == ["bx2"]
    assert out["seo"]["pages"]["seite:Ueber_Uns"]["title"] == "Wir"


@pytest.mark.parametrize(
    "host", ["seite:", "seite:a b", "seite:a/b", "seite:ü", "seite:a:b", "seite:a\n", "seite"]
)
def test_bad_content_page_host_still_rejected(host):
    """Негативный контроль: вне алфавита `SlugField` — не хост своей страницы."""
    assert not siteconfig.is_content_page_host(host)
    assert not siteconfig.is_page_block_host(host)
    assert not siteconfig.is_seo_page_host(host)


# --- architect №13: один регэксп хоста ------------------------------------------------

#: писатель слага — осознанно строже (нижний регистр, `make_slug`): заглавные приходят только
#: из импорта и админки; читатели хоста принимают весь алфавит `SlugField`
_WRITER_EXCEPTIONS = {"apps/core/content_pages.py": "_SLUG_RE"}


def _compiled_patterns(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "attr", "") == "compile"
            and node.value.args
            and isinstance(node.value.args[0], ast.Constant)
            and isinstance(node.value.args[0].value, str)
        ):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            yield names, node.value.args[0].value


def test_one_content_page_host_regex():
    """Хост `seite:<slug>` проверяет ОДИН регэксп (`siteconfig.is_content_page_host`);
    копий в других модулях нет. Писатель слага — исключение с причиной (выше)."""
    found = []
    for path in sorted((ROOT / "apps").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if "/tests/" in rel or "/migrations/" in rel:
            continue
        for names, pattern in _compiled_patterns(path):
            if "seite" in pattern:
                found.append((rel, tuple(names)))
            elif pattern.startswith("^[a-z0-9]+(?:-[a-z0-9]+)*"):
                assert _WRITER_EXCEPTIONS.get(rel) in names, (rel, names)
    assert found == [("apps/tenants/siteconfig.py", ("CONTENT_PAGE_HOST_RE",))]
    from apps.core import detail_parts

    assert not hasattr(detail_parts, "_PAGE_HOST_RE")
    assert not hasattr(siteconfig, "_CONTENT_PAGE_HOST_RE")
    assert detail_parts.module_of("seite:Ueber_Uns") == "page"
