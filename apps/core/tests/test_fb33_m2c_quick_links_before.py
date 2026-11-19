"""FB-33 M2c-0: как «Быстрые ссылки» (`site_defaults.hero_widget`) рисуются ДО выноса в блок.

Характеризация для переноса: в каких видах баннера плитки видны, где они ЗАМЕНЯЮТ кнопку
баннера, а где их нет вовсе (bento). После M2c плитки уходят в отдельный блок, а кнопка
возвращается — этот слепок говорит, что именно должно поменяться и где.
"""

import re

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory

from apps.core import hero_tiles
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

STYLES = ("plain", "accent", "split", "fullscreen", "bento")
#: вид баннера → (плитки видны, кнопка баннера видна) при заданном наборе плиток
EXPECTED = {
    "plain": (True, False),  # у plain кнопки нет вовсе
    "accent": (True, False),  # плитки ЗАМЕНЯЮТ кнопку
    "split": (True, True),
    "fullscreen": (True, False),  # без фото fullscreen рисуется как accent
    "bento": (False, True),  # bento плитки не читает — у него своя кнопка
}
LINK_SETS = ("aktionsmarkt", "friseur", "handwerker", "shop", "gastro", "mode")


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _render(style, widget):
    tenant = TenantFactory(business_type="online_shop", disabled_modules=[])
    raw = {"site_defaults": {"hero_widget": widget} if widget else {}}
    if style != "plain":
        raw["hero_style"] = style
    cfg = siteconfig.normalize(raw)
    request = RequestFactory().get("/")
    request.tenant = tenant
    primary = {"landing": "storefront-products", "label": "Sortiment", "module": "catalog"}
    ctx = {"site": cfg, "request": request, "primary_item": primary, "modules": {}}
    return render_to_string("storefront/sections/_hero.html", ctx), ctx


def _squash(html):
    return re.sub(r"\s+", " ", html).strip()


def _tiles_html(widget, ctx):
    tpl = "storefront/sections/_hero_widget.html"
    return _squash(render_to_string(tpl, {**ctx, "hero_widget": widget}))


@pytest.mark.parametrize("widget", LINK_SETS)
@pytest.mark.parametrize("style", STYLES)
def test_where_tiles_show_and_where_they_replace_the_button(style, widget):
    html, ctx = _render(style, widget)
    tiles = _tiles_html(widget, ctx)
    assert re.search(r'href="/', tiles), f"{widget}: набор без ссылок"
    tiles_shown, cta_shown = EXPECTED[style]
    assert (tiles in _squash(html)) is tiles_shown
    assert ("data-hero-cta" in html) is cta_shown


@pytest.mark.parametrize("style", ("accent", "split"))
def test_without_tiles_the_button_is_there(style):
    html, _ctx = _render(style, "")
    assert "data-hero-cta" in html


def test_registry_of_link_sets_is_what_the_migration_must_cover():
    """Перенос (M2c-2) переводит в блок наборы-ссылки; `stays`/`services` — не ссылки."""
    link_sets = set(siteconfig.HERO_WIDGETS) - {"stays", "services"}
    assert set(hero_tiles.HERO_TILE_WIDGETS) <= link_sets
    assert link_sets - set(hero_tiles.HERO_TILE_WIDGETS) == {"gastro", "bakery", "butcher", "mode"}


def test_known_places_that_touch_hero_widget():
    """Замок M2c: перенос (M2c-2) и писатели (M2c-3) должны учесть КАЖДОЕ место, где код
    читает или пишет `hero_widget`. Новое место — сначала в план M2c, потом сюда."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    found = sorted(
        str(p.relative_to(root))
        for p in (root / "apps").rglob("*.py")
        if "/tests/" not in str(p)
        and "/migrations/" not in str(p)
        and "hero_widget" in p.read_text(encoding="utf-8")
    )
    assert found == [
        "apps/core/hero_tiles.py",
        "apps/core/quick_links_migration.py",  # M2c-2: перенос (снимает ключ)
        "apps/core/setup_steps.py",
        "apps/core/views.py",
        "apps/tenants/demo_kits.py",
        "apps/tenants/siteconfig.py",
        "apps/tenants/sitetemplates.py",
        "apps/tenants/templatetags/siteui.py",
    ]
