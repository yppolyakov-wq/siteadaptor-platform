"""DL-15: неполный ряд «по центру + широкая одиночная карточка» (решение владельца B+D),
полоса «Endet bald» в 2 колонки широкими карточками, бейдж карточки крупнее, демо
aktionsmarkt «по ширине». Плитка-подсказка (E) остаётся режимом tail="fill" (DL-11)."""

from __future__ import annotations

import importlib.util
import re
from datetime import timedelta
from importlib import import_module
from pathlib import Path

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory
from django.utils import timezone

from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]


def _gen():
    spec = importlib.util.spec_from_file_location(
        "gen_fill_rows_css", ROOT / "scripts" / "gen_fill_rows_css.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _get(view, path, tenant):
    request = RequestFactory().get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return view(request).content.decode()


# ── CSS: B (по центру) + D (широкая одиночная) ──────────────────────────────


def test_css_spread_centers_and_has_no_space_evenly():
    css = _gen().generate()
    assert (
        '[data-sf-tail="spread"]:not(.is-list):not([data-density]) { display: flex; flex-wrap: wrap; justify-content: center; }'
        in css
    )
    assert "space-evenly" not in css


def test_css_solo_card_rules_only_for_tablet_and_desktop():
    css = _gen().generate()
    assert "@supports selector(a:has(> b)) {" in css
    # десктоп и планшет: одна карточка в последнем ряду → width 100 % + горизонтальная форма
    for n in range(2, 7):
        assert (
            f'[data-sf-cols$="/{n}"]:not([data-density])[data-sf-tail="spread"]:not(.is-list):not([data-sf-more]) > :nth-child({n}n+1):last-child'
            in css
        )
        assert (
            f'[data-sf-cols*="/{n}/"][data-sf-tail="spread"]:not(.is-list)[data-sf-more] > :nth-child({n}n+1):nth-last-child(2)'
            in css
        )
        # телефон — только B (узко для горизонтальной карточки)
        assert (
            f'[data-sf-cols^="{n}/"][data-sf-tail="spread"]:not(.is-list):not([data-sf-more]) > :nth-child({n}n+1):last-child'
            not in css
        )
    assert "{ width: 100%; }" in css
    assert "{ width: 38%; flex: none; aspect-ratio: 3 / 2; }" in css


def test_css_wide_form_targets_only_media_link_and_sf_wide():
    """Форма меняется у ссылки с медиа-боксом и текстовым телом; голая `> a {` (оживила
    бы скрытую ✎-ссылку редактора) не эмиттится; .sf-wide получает те же правила."""
    css = _gen().generate()
    block = css[css.index("@supports selector") :]
    assert "> a {" not in block
    assert (
        ".sf-wide > a:has(> [data-sf-media-box] + div), a.sf-wide:has(> [data-sf-media-box] + div) { display: flex; align-items: center; }"
        in block
    )
    # карточка товара (ряд цены вне ссылки): корень — grid, ссылка — display:contents
    assert (
        ".sf-wide:has(> a > [data-sf-media-box] + div):has(> a ~ div) > a:has(> [data-sf-media-box] + div) { display: contents; }"
        in block
    )
    # ширину получают только карточки, способные стать горизонтальными (overlay/плитки — нет)
    assert "), a.sf-wide:has(> [data-sf-media-box] + div) { width: 100%; }" not in block
    assert ":has(> a > [data-sf-media-box] + div), a:is(" in block

    # .sf-wide — ребёнок обычной сетки: ширину не трогаем
    assert ".sf-wide { width: 100%; }" not in block


def test_css_has_is_never_nested():
    """`:has()` внутри `:has()` невалиден — браузер молча выбрасывает всё правило
    (поймано стендом DL-15: широкая карточка осталась узкой)."""
    css = _gen().generate()
    depth = 0
    i = 0
    while i < len(css):
        if css.startswith(":has(", i):
            assert depth == 0, css[max(0, i - 80) : i + 40]
            depth = 1
            i += 5
            level = 1
            while level:
                ch = css[i]
                level += ch == "("
                level -= ch == ")"
                assert not css.startswith(":has(", i), css[max(0, i - 80) : i + 40]
                i += 1
            depth = 0
        else:
            i += 1


def test_app_css_block_is_fresh():
    gen = _gen()
    src = (ROOT / "static" / "src" / "app.css").read_text(encoding="utf-8")
    block = src[src.index(gen.START) : src.index(gen.END) + len(gen.END)] + "\n"
    assert block == gen.generate()


# ── /aktionen/: «Endet bald» в 2 колонки широкими карточками, бейдж крупнее ──


def test_ending_soon_is_two_column_grid_of_wide_cards():
    tenant = TenantFactory(schema_name="public", slug="dl15a", name="A", disabled_modules=[])
    soon = timezone.now() + timedelta(days=1)
    for i in range(2):
        Promotion.objects.create(
            title={"de": f"Bald {i}"}, status="active", ends_at=soon, discount_percent=30
        )
    html = _get(public_views.promotion_list, "/aktionen/", tenant)
    m = re.search(
        r'<div class="grid grid-cols-1 sm:grid-cols-2 gap-4" data-ending-grid>(.*?)\n      </div>',
        html,
        re.S,
    )
    assert m, html[:600]
    assert m.group(1).count("sf-wide") == 2
    assert "w-56 shrink-0" not in html and "lg:justify-evenly" not in html
    # бейдж карточки крупнее (text-sm px-3); детальная (size=lg) не тронута
    assert 'bg-red-600 text-white text-sm font-bold px-3 py-1 rounded-full shadow"' in html
    assert "text-xs font-bold px-2.5 py-1 rounded-full shadow" not in html


def test_no_ending_soon_no_grid():
    tenant = TenantFactory(schema_name="public", slug="dl15b", name="B", disabled_modules=[])
    Promotion.objects.create(title={"de": "Lang"}, status="active")
    html = _get(public_views.promotion_list, "/aktionen/", tenant)
    assert "data-ending-grid" not in html


# ── демо aktionsmarkt «по ширине» ────────────────────────────────────────────


def test_aktionsmarkt_promo_groups_fill_rows():
    """Владелец: «пересей демо, чтоб всё было по ширине» — группы /aktionen/ кратны 3
    (колонки десктопа), «Endet bald» (≤3 дней, до 4 карточек) — чётное число (2 колонки)."""
    from collections import Counter

    from apps.tenants import demo_kits

    kit = demo_kits.AKTIONSMARKT
    # DL-17.4: запланированные акции (`starts_in_days`) в секции групп не выводятся —
    # у них своя лента «Vorschau», поэтому кратность рядов считают только действующие.
    live = [p for p in kit.promotions_spec if not p.get("starts_in_days")]
    groups = Counter(p.get("group", "") for p in live)
    bad = {g: n for g, n in groups.items() if g and n % 3}
    assert not bad, bad
    assert any(p.get("starts_in_days") for p in kit.promotions_spec)  # демо A1 «Vorschau»
    soon = sum(1 for p in kit.promotions_spec if 0 < p.get("ends_in_days", 99) <= 3)
    assert min(soon, 4) % 2 == 0, soon
