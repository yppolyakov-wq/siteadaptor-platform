"""FB-31 P6 A0/A1/A3: Студия больше не пишет разделы деталей и шаблоны страниц — один
писатель «Seitenaufbau» (решение владельца, `docs/fb31-p6-cleanup-plan-2026-11-16.md`).
Устаревшая вкладка Студии (её форма ещё шлёт старые поля) не откатывает правку схемы."""

import pytest

from apps.core.tests.test_pages_view import _builder
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

SAVED = {
    "event_detail": {"order": ["faq", "idea"], "hidden": ["venue"], "layout": "tabs"},
    "product_detail": {"hidden": ["info"], "layout": "breit"},
    "service_detail": {"order": ["team"], "hidden": ["faq"], "layout": "tabs"},
    "stay_detail": {"hidden": ["amenities"], "layout": "breit"},
    "catalog_page_style": "regale",
    "page_styles": {"services": "tabs", "events": "kopfbild"},
}

STALE_POST = {
    # инспектор детали события
    "ed_order_idea": "0",
    "ed_order_faq": "1",
    "ed_visible_idea": "on",
    "ed_layout": "",
    # товар, услуга, номер
    "pd_present": "1",
    "pd_layout": "",
    "sd_present": "1",
    "sd_layout": "",
    "std_present": "1",
    "std_layout": "",
    # плитки «Vorlage»
    "catalog_page_style": "",
    "services_page_style": "",
    "events_page_style": "",
    # «Ähnliche» (STU-19f-2 уже не писала)
    "related_preset": "cols6",
}


def _tenant():
    return TenantFactory(
        schema_name="public", slug="p6w", name="P6W", disabled_modules=[], site_config=SAVED
    )


def test_stale_studio_form_does_not_touch_sections_or_page_templates():
    tenant = _tenant()
    before = siteconfig.normalize(tenant.site_config)
    _builder("post", STALE_POST, tenant)
    tenant.refresh_from_db()
    after = siteconfig.normalize(tenant.site_config)
    for key in (
        "event_detail",
        "product_detail",
        "service_detail",
        "stay_detail",
        "catalog_page_style",
        "page_styles",
        "detail_related_layout",
    ):
        assert after.get(key) == before.get(key), key


def test_studio_save_still_writes_its_own_content():
    tenant = _tenant()
    _builder("post", {**STALE_POST, "hero_title": "Neu"}, tenant)
    tenant.refresh_from_db()
    assert (tenant.site_config or {}).get("hero_title") == "Neu"
