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
    for path in ("/ueber-uns/", "/meine-seite/", "/seite/meine-seite/", "/versand/"):
        assert sp.resolve_page(path).code == "text", path
    assert sp.page_type("text").block_host == "info"


def test_no_separate_content_page_type():
    assert "content_page" not in {pt.code for pt in sp.PAGE_TYPES}


def test_legal_pages_have_no_blocks():
    assert sp.resolve_page("/impressum/").code == "legal"
    assert not sp.page_type("legal").block_host
    assert not siteconfig.is_page_block_host("legal")
    assert "page_blocks" not in (TEMPLATES / "legal.html").read_text()


def test_every_text_page_renders_its_own_blocks():
    """M21.11 (решение владельца): у каждой страницы типа «Seite» свой набор блоков."""
    assert '{% page_blocks "info" %}' in (TEMPLATES / "about.html").read_text()
    assert '{% page_blocks "versand" %}' in (TEMPLATES / "shipping_info.html").read_text()
    assert "{% page_blocks pb_host %}" in (TEMPLATES / "content_page.html").read_text()
    assert siteconfig.is_page_block_host("versand")
    assert siteconfig.is_page_block_host("seite:zahlung-und-versand")
    for bad in ("seite:", "seite:Bad", "seite:a/b", "seite:" + "x" * 120):
        assert not siteconfig.is_page_block_host(bad), bad


def test_normalize_drops_legacy_legal_blocks():
    cfg = siteconfig.normalize(
        {"page_blocks": {"legal": [{"key": "text", "id": "x1", "data": {"title": "T"}}]}}
    )
    assert "legal" not in (cfg.get("page_blocks") or {})


def test_schema_preview_shows_saved_state_not_studio_draft():
    """Фидбэк владельца: блок выключен в «Seitenaufbau», а превью его показывает —
    iframe читал черновик Студии из сессии. `stand=saved` = сохранённое."""
    from types import SimpleNamespace

    from django.test import RequestFactory

    from apps.core import page_settings

    saved = {"page_blocks": {"info": [{"key": "text", "id": "a1", "enabled": False}]}}
    draft = {"page_blocks": {"info": [{"key": "text", "id": "a1", "enabled": True}]}}
    req = RequestFactory().get("/ueber-uns/", {"preview": "1", "stand": "saved"})
    req.tenant = SimpleNamespace(site_config=saved)
    req.session = {"site_preview_draft": draft}
    assert page_settings.raw_config(req) is saved
    req2 = RequestFactory().get("/ueber-uns/", {"preview": "1"})
    req2.tenant, req2.session = req.tenant, req.session
    assert page_settings.raw_config(req2) is draft  # Студия по-прежнему видит черновик
    # FB-27 R2: ссылку превью собирает вьюха — сохранённое, а при черновике схемы
    # `aufbau=<code>`; черновик Студии не попадает туда ни в одном случае.
    view = (TEMPLATES.parent.parent / "apps" / "core" / "site_schema_views.py").read_text()
    assert '"stand": "saved"' in view and '"aufbau": code' in view
