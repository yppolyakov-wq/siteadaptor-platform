"""Реестр плиток первого экрана (`core.hero_tiles`, план hero-tiles-all-archetypes-
plan-2026-07-30): гейты модулей, «горячая» плитка акции, fail-safe на мёртвом url."""

import pytest
from django.template.loader import render_to_string

from apps.core import hero_tiles
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


class _Deal:
    title_text = "Sommer-Deal"


def _tenant(**kw):
    return TenantFactory.build(**kw)


@pytest.mark.parametrize("widget", hero_tiles.HERO_TILE_WIDGETS)
def test_every_widget_yields_tiles_when_modules_active(settings, widget):
    """Каждый архетип реестра даёт непустой набор при всех активных модулях —
    иначе первый экран у него пустой (регресс, который легко не заметить)."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _tenant(disabled_modules=[])
    tiles = hero_tiles.tiles_for(widget, tenant, deal=_Deal())
    assert tiles, f"{widget}: нет плиток"
    assert all(t["href"].startswith("/") for t in tiles)


def test_unknown_widget_is_empty(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    assert hero_tiles.tiles_for("", _tenant()) == []
    assert hero_tiles.tiles_for("bakery", _tenant()) == []  # кастомная ветка шаблона
    assert hero_tiles.tiles_for("nope", _tenant()) == []


def test_deal_gate_hides_tile_without_promotion(settings):
    """gate="deal": без живой акции плитки нет; с акцией — подпись из заголовка."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _tenant(disabled_modules=[])
    without = [t["label"] for t in hero_tiles.tiles_for("friseur", tenant, deal=None)]
    with_deal = hero_tiles.tiles_for("friseur", tenant, deal=_Deal())
    assert "Aktionen & Angebote" not in [str(x) for x in without]
    hot = [t for t in with_deal if t["highlight"]]
    assert hot and hot[0]["sub"] == "Sommer-Deal"


def test_aktionsmarkt_deal_tile_survives_without_promotion(settings):
    """A8: акции — сам архетип, поэтому плитка «Aktuelle Deals» без гейта."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    labels = [str(t["label"]) for t in hero_tiles.tiles_for("aktionsmarkt", _tenant(), deal=None)]
    assert "Aktuelle Deals" in labels


def test_module_gate_drops_tiles(settings):
    """Выключенный модуль убирает свою плитку (а не ломает набор)."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    full = hero_tiles.tiles_for("werkstatt", _tenant(disabled_modules=[]), deal=None)
    lean = hero_tiles.tiles_for("werkstatt", _tenant(disabled_modules=["jobs", "orders"]))
    assert len(lean) < len(full)
    assert "Kostenvoranschlag" not in [str(t["label"]) for t in lean]


def test_dead_url_name_drops_tile_not_page(settings, monkeypatch):
    """Fail-safe: опечатка в url_name гасит ПЛИТКУ, а не главную страницу."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    broken = [{"icon": "x", "label": "X", "url": "storefront-does-not-exist", "gate": ""}]
    monkeypatch.setitem(hero_tiles.HERO_TILE_SETS, "friseur", broken)
    assert hero_tiles.tiles_for("friseur", _tenant()) == []


def test_needs_deal_only_where_deal_tiles_exist():
    assert hero_tiles.needs_deal("friseur") is True
    assert hero_tiles.needs_deal("retreat") is False  # нет deal-плитки → нет лишнего SQL
    assert hero_tiles.needs_deal("nope") is False


def test_generic_branch_renders_via_hero_widget_partial(settings):
    """Генерик подключён {% else %}-веткой _hero_widget.html и не мешает
    кастомным (stays/services/gastro/bakery/butcher/mode)."""
    settings.ROOT_URLCONF = "config.urls_tenant"

    class _Req:
        tenant = None

    req = _Req()
    req.tenant = _tenant(disabled_modules=[])
    body = render_to_string(
        "storefront/sections/_hero_widget.html", {"hero_widget": "handwerker", "request": req}
    )
    assert "Angebot anfordern" in body and "/anfrage/" in body
    assert "Rückruf anfordern" in body


def test_all_registry_widgets_survive_normalize():
    """normalize не должен выбрасывать hero_widget новых архетипов (иначе демо
    теряет первый экран при первом же сохранении билдера)."""
    from apps.tenants import siteconfig

    for widget in hero_tiles.HERO_TILE_WIDGETS:
        cfg = siteconfig.normalize({"site_defaults": {"hero_widget": widget}})
        assert cfg["site_defaults"]["hero_widget"] == widget


def test_kits_have_first_screen():
    """Фидбэк «первый экран для всех архетипов»: у каждого демо-кита есть либо
    слайдер, либо hero-виджет (иначе главная не ловит направления)."""
    from apps.tenants.demo_kits import KITS

    missing = [k for k, kit in KITS.items() if not kit.heroes and not kit.hero_widget]
    assert missing == [], f"без первого экрана: {missing}"
