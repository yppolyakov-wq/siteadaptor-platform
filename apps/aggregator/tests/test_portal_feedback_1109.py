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


def test_merkzettel_links_go_to_the_saved_list_and_pills_are_outlined():
    """a11y-ревью: «Merkzettel»/«Gemerkt» ведут к списку сохранённого, а не просто в кабинет;
    плашки на фото обведены (1.4.11), у цены есть подпись для читалок."""
    base = (TPL / "portal_base.html").read_text()
    head = re.search(r'<a [^>]*data-head-icon="merkzettel"[^>]*>', base).group(0)
    assert "#merkzettel" in head
    bottom = base[base.index("data-portal-bottom-nav") :]
    assert bottom.count("#merkzettel") >= 1
    acc = (TPL / "portal_account.html").read_text()
    assert 'id="merkzettel"' in acc
    quad = (TPL / "_portal_quad.html").read_text()
    assert quad.count("ring-white/70") == 2 and "ring-black/10" in quad
    assert '<span class="sr-only">{% trans "Preis" %}: </span>' in quad
