"""FB-33 M2c-0: «Быстрые ссылки» до выноса в блок — помощники рендера и список мест.

Слепок «где плитки баннера видны и где заменяли кнопку» (M2c-0) снят в M2c-4: баннер ключ
`site_defaults.hero_widget` больше не читает ни в одном виде — замок L2 в
`test_fb33_m2c4_no_hero_widget.py`. Здесь — помощники рендера (их берёт тест блока) и
перечень мест кода, где ещё встречается слово `hero_widget`.
"""

import re

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory

from apps.core import hero_tiles
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

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


@pytest.mark.parametrize("style", ("accent", "split"))
def test_without_tiles_the_button_is_there(style):
    html, _ctx = _render(style, "")
    assert "data-hero-cta" in html


def test_registry_of_link_sets_is_what_the_migration_must_cover():
    """Перенос (M2c-2) переводит в блок наборы-ссылки; `stays`/`services` — не ссылки."""
    from apps.core import quick_links_migration as qlm

    link_sets = set(qlm.LEGACY_WIDGETS) - {"stays", "services"}
    assert set(hero_tiles.HERO_TILE_WIDGETS) <= link_sets
    assert link_sets - set(hero_tiles.HERO_TILE_WIDGETS) == {"gastro", "bakery", "butcher", "mode"}


def test_known_places_that_touch_hero_widget():
    """Замок M2c: перенос (M2c-2) и писатели (M2c-3) должны учесть КАЖДОЕ место, где код
    читает или пишет `hero_widget`. M2c-4: витрина и нормализатор ключ не читают — остались
    перенос, его команда, поля китов/ось сборок и имя партиала `_hero_widget.html` в
    реестре плиток. Новое место — сначала в план, потом сюда."""
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
        "apps/core/hero_tiles.py",  # имя партиала `_hero_widget.html` в комментариях
        "apps/core/management/commands/detach_quick_links.py",  # M2c-2: команда переноса
        "apps/core/quick_links_migration.py",  # M2c-2: перенос (снимает ключ)
        "apps/tenants/demo_kits.py",  # поле кита `hero_widget` (набор), не ключ конфига
        "apps/tenants/sitetemplates.py",  # ось сборки `hero_widget` → `_bundle_tiles`
        "apps/tenants/templatetags/siteui.py",  # `quick_links_html` рисует партиал
    ]
