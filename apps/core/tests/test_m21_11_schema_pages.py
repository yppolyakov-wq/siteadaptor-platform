"""M21.11: «Seitenaufbau» — у каждой текстовой страницы свой набор блоков, карточка
контактов «Über uns» выключается."""

import pytest

from apps.core import site_schema
from apps.core.models import ContentPage
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant():
    return TenantFactory(slug="sp-t", name="T")


def test_each_text_page_has_its_own_host():
    ContentPage.objects.create(slug="zahlung", title="Zahlung", is_published=True)
    codes = {p.code: p.host for p in site_schema.text_pages()}
    assert codes["text"] == "info"
    assert codes["text@versand"] == "versand"
    assert codes["text@seite:zahlung"] == "seite:zahlung"


def test_block_added_on_one_page_does_not_appear_on_another():
    ContentPage.objects.create(slug="zahlung", title="Zahlung", is_published=True)
    t = _tenant()
    site_schema.apply(t, "text@seite:zahlung", "add", block_type="text")
    cfg = siteconfig.normalize(t.site_config)
    pb = cfg.get("page_blocks") or {}
    assert len(pb.get("seite:zahlung", [])) == 1
    assert not pb.get("info") and not pb.get("versand")


def test_unknown_host_is_rejected():
    t = _tenant()
    for code in ("text@catalog", "text@seite:BAD", "text@legal", "home@info"):
        with pytest.raises(site_schema.SchemaError):
            site_schema.apply(t, code, "add", block_type="text")


def test_contact_card_toggles_and_is_not_deletable():
    t = _tenant()
    rows = site_schema.blocks_for(siteconfig.normalize(t.site_config), "text")
    assert rows[0]["ref"] == site_schema.CONTACT_REF and rows[0]["enabled"]
    site_schema.apply(t, "text", "toggle", ref=site_schema.CONTACT_REF)
    assert siteconfig.normalize(t.site_config).get("about_contact") is False
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(t, "text", "delete", ref=site_schema.CONTACT_REF)
    site_schema.apply(t, "text", "toggle", ref=site_schema.CONTACT_REF)
    assert "about_contact" not in siteconfig.normalize(t.site_config)


def test_about_page_hides_contact_card_when_switched_off():
    from pathlib import Path

    from django.conf import settings

    tpl = (Path(settings.BASE_DIR) / "templates/storefront/about.html").read_text()
    assert "site.about_contact is not False" in tpl


def test_host_of_missing_page_is_rejected():
    """Ревью безопасности: хосты-призраки не создаются (общий потолок хостов)."""
    t = _tenant()
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(t, "text@seite:gibt-es-nicht", "add", block_type="text")


def test_blocks_follow_slug_change_and_vanish_with_page():
    from django.db import connection

    from apps.core import content_pages

    t = _tenant()
    page = ContentPage.objects.create(slug="alt", title="Alt", is_published=True)
    site_schema.apply(t, "text@seite:alt", "add", block_type="text")
    connection.tenant = t
    content_pages.save_page(page, title="Neu", slug="neu", body="", is_published=True)
    t.refresh_from_db()
    pb = t.site_config.get("page_blocks") or {}
    assert "seite:alt" not in pb and len(pb.get("seite:neu", [])) == 1
    connection.tenant = t  # тест: фабрика тенанта сбрасывает подключение (в запросе оно стабильно)
    assert content_pages.move_page_blocks("neu", None)
    t.refresh_from_db()
    assert "seite:neu" not in (t.site_config.get("page_blocks") or {})
