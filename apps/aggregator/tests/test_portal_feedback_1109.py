"""Фидбэк владельца 2026-11-09: метки поверх фото в quad-карточках, значки в шапке,
нижнее меню на всю ширину."""

from __future__ import annotations

import re
from pathlib import Path

TPL = Path(__file__).resolve().parents[3] / "templates" / "aggregator"


def test_quad_badge_and_price_sit_on_the_photo_and_title_is_truncated():
    src = (TPL / "_portal_quad.html").read_text()
    photo = src[src.index('<span class="relative block aspect-square') :]
    photo = photo[: photo.index('</span>\n          <span class="mt-1.5')]
    assert "data-quad-badge" in photo and "absolute top-2 left-2" in photo
    assert "data-quad-price" in photo and "absolute bottom-2 left-2" in photo
    title = src[src.index('<span class="mt-1.5') :].split(">", 1)[0]
    assert " truncate" in title and "line-clamp" not in title
    assert 'title="{{ l.title_text }}"' in title  # полное имя доступно наведением


def test_header_account_links_are_icons_with_accessible_names():
    src = (TPL / "portal_base.html").read_text()
    for key, label in (
        ("business", "Für Unternehmen"),
        ("merkzettel", "Merkzettel"),
        ("login", "Sign in"),
        ("account", "My account"),
    ):
        a = re.search(rf'<a [^>]*data-head-icon="{key}"[^>]*>.*?</a>', src, re.S).group(0)
        assert "<svg" in a and 'aria-hidden="true"' in a, key
        assert f'<span class="sr-only">{{% trans "{label}" %}}</span>' in a, key
        assert "h-11 w-11" in a, key  # цель ≥ 44 px


def test_bottom_nav_spans_full_width_and_sticks_to_bottom():
    src = (TPL / "portal_base.html").read_text()
    nav = re.search(r"<nav [^>]*data-portal-bottom-nav[^>]*>", src).group(0)
    assert "fixed inset-x-0 bottom-0" in nav
    assert "left-3" not in nav and "rounded-3xl" not in nav
    assert "safe-area-inset-bottom" in nav
