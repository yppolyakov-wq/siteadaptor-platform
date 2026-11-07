"""FB-22b: C-блок «Banner» — баннер на любой странице (поля слайда главной)."""

import datetime

import pytest
from django.template import Context
from django.test import RequestFactory
from django.utils import timezone

from apps.tenants import siteconfig
from apps.tenants.templatetags import siteui


def _clean(data):
    return siteconfig._clean_cblock_data("banner", data)


def _render(data, preview=False):
    ctx = Context({"request": RequestFactory().get("/"), "is_preview": preview})
    return siteui.render_block(ctx, {"key": "banner", "id": "bn1", "data": data})


def test_banner_is_repeatable_on_pages_and_home():
    assert "banner" in siteconfig.REPEATABLE_BLOCKS
    cfg = siteconfig.normalize(
        {"page_blocks": {"info": [{"key": "banner", "id": "b1", "data": {"title": "Hi"}}]}}
    )
    host = next(iter(cfg["page_blocks"].values()))
    assert any(b["key"] == "banner" and b["data"]["title"] == "Hi" for b in host)


def test_clean_keeps_safe_fields_and_drops_junk():
    out = _clean(
        {
            "url": "/media/x.jpg",
            "title": "Sommer",
            "text": "Jetzt",
            "button_label": "Los",
            "button_url": "javascript:alert(1)",
            "link": "page:contact",
            "align": "left",
            "overlay": "evil",
            "tone": "dark",
            "starts": "2026-01-01",
            "ends": "nope",
            "click_all": "1",
            "height": "huge",
            "foo": "bar",
        }
    )
    assert out["url"] == "/media/x.jpg" and out["title"] == "Sommer"
    assert out["button_url"] == ""  # javascript: не проходит
    assert out["link"] == "page:contact" and out["align"] == "left" and out["tone"] == "dark"
    assert "overlay" not in out and "ends" not in out and "height" not in out and "foo" not in out
    assert out["starts"] == "2026-01-01" and out["click_all"] is True


def test_demo_data_round_trips():
    demo = siteconfig.CBLOCK_DEMO_DATA["banner"]
    assert _clean(demo) == demo


@pytest.mark.django_db
def test_render_h2_link_and_dates():
    html = _render({"title": "Sommer", "button_label": "Los", "button_url": "/aktionen/"})
    assert "<h2" in html and "<h1" not in html and 'href="/aktionen/"' in html
    future = (timezone.localdate() + datetime.timedelta(days=3)).isoformat()
    assert _render({"title": "Bald", "starts": future}).strip() == ""
    # в превью Студии блок вне дат не пропадает молча
    assert "Banner" in _render({"title": "Bald", "starts": future}, preview=True)


def test_empty_banner_is_invisible_but_marked_in_preview():
    assert _render({}).strip() == ""
    assert _render({}, preview=True).strip() != ""
