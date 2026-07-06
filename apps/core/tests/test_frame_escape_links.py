"""T-6: ссылки витрины в DENY-зону кабинета обязаны выпрыгивать из iframe.

Инцидент 2026-07-06 (прод, restaurant-demo): владелец кликнул «✏️ Edit design»
ВНУТРИ канвы превью редактора (внутренние переходы канвы идут без ?preview=1,
поэтому FAB там виден) → кадр загрузил /dashboard/site/home/ → X-Frame-Options:
DENY → chrome-error «refused to connect»; после F5 Chrome восстанавливает
историю сабфрейма → канва остаётся мёртвой. Витрина рендерится и в iframe
редактора (H1.1 — SAMEORIGIN), значит каждая её ссылка на пути из
StorefrontFrameOptionsMiddleware._BLOCK_PREFIXES должна нести target="_top"
(или "_blank"), иначе она убивает канву.
"""

import re
from pathlib import Path

from django.conf import settings

STOREFRONT_TEMPLATES = Path(settings.BASE_DIR) / "templates" / "storefront"

# Признаки ссылки в DENY-зону: реверс кабинетных url-имён или литеральный href.
_BLOCKED_URL_RE = re.compile(
    r"""\{%\s*url\s+['"](site-home|catalog:)"""  # site-home + весь CRUD /catalog/
    r"""|href="/(dashboard|catalog|imports|promotions|crm|willkommen|accounts)/"""
)
_ESCAPES_FRAME_RE = re.compile(r'target="(_top|_blank)"')
_A_TAG_RE = re.compile(r"<a\s[^>]*>", re.DOTALL)


def test_storefront_links_to_deny_zone_escape_the_frame():
    offenders = []
    for tpl in sorted(STOREFRONT_TEMPLATES.rglob("*.html")):
        source = tpl.read_text(encoding="utf-8")
        for tag in _A_TAG_RE.findall(source):
            if _BLOCKED_URL_RE.search(tag) and not _ESCAPES_FRAME_RE.search(tag):
                offenders.append(f"{tpl.relative_to(STOREFRONT_TEMPLATES)}: {tag[:120]}")
    assert not offenders, (
        "Ссылка витрины в DENY-зону без target=_top/_blank убивает канву редактора "
        "(X-Frame-Options: DENY в iframe):\n" + "\n".join(offenders)
    )


def test_known_traps_carry_escape_targets():
    """Точечные замки инцидента: FAB «Edit design» и ✎ категории."""
    base = (STOREFRONT_TEMPLATES / "_base.html").read_text(encoding="utf-8")
    fab = next(t for t in _A_TAG_RE.findall(base) if "data-owner-edit" in t)
    assert 'target="_top"' in fab
    assert "?page=" in fab  # T-6.1: deep-link — редактор открывается на текущей странице
    # T-6.1: внутри канвы (iframe) FAB прячем — дубль редактора путал владельца.
    assert "window.top !== window.self" in base

    products = (STOREFRONT_TEMPLATES / "products.html").read_text(encoding="utf-8")
    cat_edit = next(t for t in _A_TAG_RE.findall(products) if "catalog:category-edit" in t)
    assert 'target="_blank"' in cat_edit
