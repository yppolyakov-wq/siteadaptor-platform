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


# ── A4: ассистент и разбор полей вывода ──


def test_output_payload_refuses_junk_instead_of_silent_defaults():
    from apps.core import page_settings

    for bad in ({"out_mode": "x"}, {"out_max": "7"}, {"out_max": "abc"}):
        with pytest.raises(page_settings.PageSettingError):
            page_settings.output_payload(bad, "out")
    assert page_settings.output_payload({"out_mode": "raster", "out_max": "12"}, "out") == {
        "raster": True,
        "max": "12",
    }
    assert page_settings.output_payload({"out_mode": "grid"}, "out") == {}


def test_assistant_does_not_change_a_template_replaced_by_rows(monkeypatch):
    from apps.core import assistant_pages, site_schema
    from apps.core.tests.test_assistant_a2 import _user

    tenant = TenantFactory(business_type="bakery")
    # механизм на сетке каталога (у пустой пекарни шаблоны-композиции недоступны)
    monkeypatch.setitem(site_schema.REPLACED_BY_BLOCKS, "catalog", frozenset({"catalog_layout"}))
    items = assistant_pages.build(tenant, _user(), "Zeige die Produkte als Preisliste")
    assert items and "Seitenaufbau" in str(items[0]["blocked"])


def test_review_assistant_apply_refuses_a_replaced_setting_built_before_p6(monkeypatch):
    from apps.core import assistant_actions, assistant_pages

    monkeypatch.setattr(assistant_pages, "replaced_codes", lambda: frozenset({"catalog_layout"}))
    row = {"spec": None, "item": {"target": {"pk": "catalog_layout"}}, "index": 0}
    with pytest.raises(assistant_actions.ApplyError):
        assistant_actions._change_page(row, TenantFactory.build())


# ── A5: форма объекта и схема ──


def test_tab_save_keeps_sections_saved_by_the_schema_meanwhile():
    from apps.core import object_structure
    from apps.core.tests import test_fb31p5_object_golden as og

    ev = og._event()
    stale = type(ev).objects.get(pk=ev.pk)  # форма открыта до правки схемы
    ev.page_override = {"hidden": ["faq"], "order": ["faq", "idea"]}
    ev.save(update_fields=["page_override"])  # «Speichern» в «Seitenaufbau»
    object_structure.apply_post(stale, "event", {"page_override_present": "1", "ps_layout": "tabs"})
    assert stale.page_override == {"hidden": ["faq"], "layout": "tabs", "order": ["faq", "idea"]}


def test_leave_link_warns_about_unsaved_form_changes():
    from pathlib import Path

    src = Path("templates/tenant/_object_structure.html").read_text()
    assert "data-ps-leave=" in src and "window.confirm" in src


# ── A6: сортировка туров по названию ──


def test_tours_by_name_sort_umlauts_like_a_dictionary():
    from types import SimpleNamespace

    from apps.events.public_views import _sort_tours

    tours = [SimpleNamespace(title_text=t) for t in ("Zugspitze", "Ötztal", "Ostsee", "Äolien")]
    got = [t.title_text for t in _sort_tours(tours, "name")]
    assert got == ["Äolien", "Ostsee", "Ötztal", "Zugspitze"]
