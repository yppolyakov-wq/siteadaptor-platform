"""PH-12b: читаемые чернила на цвете портала (WCAG 1.4.3, ≥ 4,5:1 при любом primary_color)."""

import re

import pytest
from django.core.cache import cache

from apps.aggregator.tests.test_portal_discover import _html, _listing, _portal
from apps.core import colors

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]

SAMPLES = ("#C2410C", "#111827", "#FDE047", "#22C55E", "#0EA5E9")


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_ink_on_picks_the_more_contrasting_text_colour():
    assert colors.ink_on("#C2410C") == "#ffffff"
    assert colors.ink_on("#111827") == "#ffffff"
    assert colors.ink_on("#FDE047") == "#111827"
    assert colors.ink_on("#22C55E") == "#111827"
    assert colors.ink_on("junk") == "#ffffff"  # fail-safe


@pytest.mark.parametrize("hex_color", SAMPLES)
def test_ink_and_link_reach_aa_contrast(hex_color):
    assert colors.contrast(colors.ink_on(hex_color), hex_color) >= 4.5
    assert colors.contrast(colors.readable_on_white(hex_color), "#ffffff") >= 4.5


def test_normalize_hex_rejects_anything_but_rrggbb():
    assert colors.normalize_hex("#C2410C") == "#c2410c"
    for bad in ("red", "#fff", "#12345g", "#123456;}body{display:none", "", None):
        assert colors.normalize_hex(bad) == "#111827"


def test_storefront_helpers_are_unchanged():
    from apps.core import context

    assert context._accent_ink("#FDE047") == "#111827"
    assert context._accent_ink("#4f46e5") == "#ffffff"


def test_portal_sets_ink_and_link_variables():
    _listing("promotion", "Pizza")
    html = _html(_portal(primary_color="#FDE047"))
    style = re.search(r"<style>:root \{[^<]*</style>", html).group(0)
    assert "--portal-color: #fde047" in style and "--portal-ink: #111827" in style
    assert "--portal-link:" in style
    assert '[style*="background: var(--portal-color"]' in style


def test_broken_primary_colour_cannot_inject_css():
    _listing("promotion", "Pizza")
    html = _html(_portal(primary_color="#1;}a{x"))  # поле — 7 символов, но и в них есть выход
    style = html.split("<style>:root", 1)[1].split("</style>", 1)[0]
    assert "a{x" not in style and "--portal-color: #111827" in style


def test_brand_coloured_text_links_use_the_readable_link_colour():
    """Замок класса: в шаблонах портала нет текста цветом портала (он мог быть 2:1 на белом)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "templates" / "aggregator"
    offenders = [
        p.name
        for p in root.glob("*.html")
        if re.search(r"(?<![-\w])color: var\(--portal-color\)", p.read_text())
    ]
    assert offenders == []


def test_every_brand_background_is_caught_by_the_ink_rule():
    """Замок класса (ревью a11y): любой фон цветом портала в шаблонах — в одной из форм,
    которые ловит правило чернил (иначе белый текст на светлом бренде — 1,x:1)."""
    from pathlib import Path

    caught = (
        "background: var(--portal-color",
        "background:var(--portal-color",
        "background-color: var(--portal-color",
        "background-color:var(--portal-color",
    )
    root = Path(__file__).resolve().parents[3] / "templates" / "aggregator"
    misses = []
    for path in root.glob("*.html"):
        for m in re.finditer(r'style="([^"]*var\(--portal-color[^"]*)"', path.read_text()):
            decl = m.group(1)
            # светлая подложка color-mix(… white) — текст на ней цветом ссылки, правило не нужно
            if "color-mix(" in decl:
                continue
            if re.search(r"background[\w-]*\s*:[^;]*var\(--portal-color", decl) and not any(
                c in decl for c in caught
            ):
                misses.append(f"{path.name}: {decl}")
    assert misses == []


def test_storefront_accent_cannot_inject_css():
    """Ревью PH-12b: тот же класс на витрине — tenant.primary_color шёл в <style> как есть."""
    from django.contrib.sessions.backends.cache import SessionStore
    from django.test import RequestFactory

    from apps.core.context import modules_nav
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="inj", slug="inj", name="Inj", primary_color="#1;}a{x")
    req = RequestFactory().get("/")
    req.session = SessionStore()
    req.tenant = tenant
    assert modules_nav(req)["storefront_accent"] == ""
    tenant.primary_color = "#4F46E5"
    assert modules_nav(req)["storefront_accent"] == "#4f46e5"
