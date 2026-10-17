"""В3 (план docs/v3-map-tiles-plan-2026-10-17.md): подложка карт — бесплатные векторные
тайлы OpenFreeMap через MapLibre GL поверх Leaflet. Тайлы OSM (tile.openstreetmap.org,
export/embed) политикой OSM для нагрузки запрещены — в коде их быть не должно."""

import re
from pathlib import Path

import pytest
from django.template import Context, Template
from django.test import override_settings

ROOT = Path(__file__).resolve().parents[3]
SCAN = [ROOT / "templates", ROOT / "apps"]


def _sources():
    for base in SCAN:
        for path in base.rglob("*"):
            if path.suffix not in {".html", ".py", ".js"} or "tests" in path.parts:
                continue
            yield path, path.read_text(encoding="utf-8", errors="ignore")


def test_no_osm_tiles_or_embed_anywhere():
    bad = [
        str(p)
        for p, text in _sources()
        if "tile.openstreetmap.org" in text or "openstreetmap.org/export/embed" in text
    ]
    assert bad == []


def test_basemap_only_through_shared_loader():
    """Подложку ставит только общий загрузчик: нет второго места, где провайдер
    зашит литералом и разойдётся при смене (одна env-переменная — одно место)."""
    raw = [str(p) for p, text in _sources() if "L.tileLayer(" in text]
    assert raw == []
    literal = [
        str(p)
        for p, text in _sources()
        if "tiles.openfreemap.org" in text and not str(p).endswith("settings")
    ]
    assert literal == []


def _render():
    return Template("{% load sf_map %}{% sf_map_loader %}").render(Context({}))


@override_settings(MAP_STYLE_URL="https://example.test/style.json")
def test_style_url_comes_from_settings():
    assert "https://example.test/style.json" in _render()


def test_default_attribution_names_all_three_parties():
    from django.conf import settings

    text = settings.MAP_ATTRIBUTION
    assert "OpenFreeMap" in text and "OpenMapTiles" in text
    assert "openstreetmap.org/copyright" in text
    assert "attribution" in _render()


def test_cdn_assets_pinned_with_sri():
    from apps.core.templatetags.sf_map import MAP_ASSETS

    assert MAP_ASSETS
    for asset in MAP_ASSETS:
        assert re.search(r"@\d+\.\d+\.\d+/", asset["url"]), asset
        assert asset["integrity"].startswith(("sha384-", "sha256-")), asset
    html = _render()
    for asset in MAP_ASSETS:
        assert asset["integrity"] in html


def test_loader_has_honest_fallbacks():
    """Нет WebGL, не загрузился скрипт, провайдер не ответил — честная надпись
    вместо пустого серого прямоугольника."""
    html = _render()
    assert "webgl" in html.lower()
    assert "setTimeout" in html  # страховка, если стиль так и не загрузился
    assert '.on("error"' in html or ".on('error'" in html
    assert "data-map-down" in html


def test_loader_is_idempotent_and_lazy():
    html = _render()
    assert "window.sfMap" in html
    assert "IntersectionObserver" in html
    # загрузчик не тянет скрипты сам при рендере — только по вызову
    assert '<script src="https://unpkg.com/maplibre' not in html


@pytest.mark.parametrize(
    "tpl",
    [
        "templates/aggregator/_map.html",
        "templates/storefront/_point_map.html",
        "templates/storefront/_route.html",
    ],
)
def test_every_map_has_fallback_text_and_no_eager_cdn(tpl):
    text = (ROOT / tpl).read_text()
    assert "data-down-text" in text
    assert '<script src="https://unpkg.com/leaflet' not in text
    assert '<link rel="stylesheet" href="https://unpkg.com/leaflet' not in text
    assert "sfMap" in text


@override_settings(
    MAP_ATTRIBUTION='<a href="https://ok.test">OK</a><img src=x onerror=alert(1)>'
    '<a href="javascript:alert(2)">bad</a>'
)
def test_attribution_from_env_is_sanitized():
    """Ревью В3: атрибуция рисуется innerHTML — из env проходят только https-ссылки."""
    from apps.core.templatetags.sf_map import sf_map_loader

    attr = sf_map_loader()["sf_map_config"]["attribution"]
    assert "onerror" not in attr and "<img" not in attr and "javascript:" not in attr
    assert 'href="https://ok.test"' in attr
