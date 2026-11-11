"""M21.11 P3: один тип «Seite» для всех текстовых страниц, правовые — без блоков.

Решение владельца: «Не нужно специального «Структура страницы» для каждого типа…
только для общего типа — страницы». Под Impressum/Datenschutz/Widerruf/AGB блоков нет.
"""

from pathlib import Path

from django.conf import settings

from apps.core import studio_pages as sp
from apps.tenants import siteconfig

TEMPLATES = Path(settings.BASE_DIR) / "templates" / "storefront"


def test_all_text_pages_share_one_type():
    for path in ("/ueber-uns/", "/seite/meine-seite/", "/versand/"):
        assert sp.resolve_page(path).code == "text", path
    assert sp.page_type("text").block_host == "info"


def test_no_separate_content_page_type():
    assert "content_page" not in {pt.code for pt in sp.PAGE_TYPES}


def test_legal_pages_have_no_blocks():
    assert sp.resolve_page("/impressum/").code == "legal"
    assert not sp.page_type("legal").block_host
    assert not siteconfig.is_page_block_host("legal")
    assert "page_blocks" not in (TEMPLATES / "legal.html").read_text()


def test_every_page_of_the_type_renders_the_shared_blocks():
    for name in ("about.html", "content_page.html", "shipping_info.html"):
        assert '{% page_blocks "info" %}' in (TEMPLATES / name).read_text(), name


def test_normalize_drops_legacy_legal_blocks():
    cfg = siteconfig.normalize(
        {"page_blocks": {"legal": [{"key": "text", "id": "x1", "data": {"title": "T"}}]}}
    )
    assert "legal" not in (cfg.get("page_blocks") or {})
