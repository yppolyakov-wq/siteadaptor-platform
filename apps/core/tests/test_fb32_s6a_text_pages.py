"""FB-32 S6a: «Über uns» и своя страница «Seite» — текст и карточка контактов строками схемы
«Seitenaufbau» (как разделы детали и корзины): свои блоки встают над текстом и между ним и
контактами. Порядок разделов постоянный, текст не скрывается, видимость контактов — прежний
`about_contact`. Без якорей страница рисуется прежней разметкой (снимки
`test_fb32_s6_pages_golden.py`)."""

import pytest

from apps.core import detail_parts, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _cfg, _tenant
from apps.core.tests.test_fb32_s6_pages_golden import TEXT, _about, _page

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_info_and_own_pages_have_section_rows_without_purchase():
    assert detail_parts.section_keys("info") == ("pagetext", "contact")
    assert detail_parts.section_keys("seite:anfahrt") == ("pagetext",)
    assert detail_parts.section_keys("seite:") == ()
    assert not detail_parts.has_kauf("info") and not detail_parts.has_kauf("seite:x")
    assert detail_parts.has_kauf("event_detail")
    rows = site_schema.blocks_for({}, "text")
    by = {r["ref"]: r for r in rows}
    assert by["pagetext"]["pinned"] and by["pagetext"]["fixed"]
    assert by["contact"]["fixed"] and not by["contact"]["pinned"]
    assert detail_parts.KAUF_REF not in by


def test_text_cannot_be_hidden_or_moved_and_contact_cannot_be_moved():
    t = _tenant()
    for ref, op in (("pagetext", "toggle"), ("pagetext", "down"), ("contact", "up")):
        with pytest.raises(site_schema.SchemaError):
            site_schema.apply(t, "text", op, ref=ref)


def test_hiding_contact_in_the_draft_writes_the_old_switch():
    b = Browser(_tenant())
    b.post(seite="text", op="toggle", ref="contact")
    b.post(seite="text", op="save")
    cfg = _cfg(b.tenant)
    assert cfg["about_contact"] is False
    assert not (cfg.get("page_blocks") or {}).get("info"), "без своих блоков якоря не хранятся"


def test_own_block_above_the_text_is_drawn_above_it():
    cfg = {"page_blocks": {"info": [TEXT, {"key": "pagetext"}, {"key": "contact"}]}}
    html = _about(cfg)
    assert html.index("Bus 5") < html.index('data-edit="about_title"') < html.index("Hauptstr")


def test_own_block_between_text_and_contact():
    cfg = {"page_blocks": {"info": [{"key": "pagetext"}, TEXT, {"key": "contact"}]}}
    html = _about(cfg)
    assert html.index('data-edit="about_title"') < html.index("Bus 5") < html.index("Hauptstr")
    hidden = _about({**cfg, "about_contact": False})
    assert "Hauptstr" not in hidden and "Bus 5" in hidden, "блок скрытого раздела остаётся"


def test_own_page_block_above_the_article():
    html = _page({"page_blocks": {"info": [TEXT, {"key": "pagetext"}]}})
    assert html.index("Bus 5") < html.index("data-content-page")


def test_lift_keeps_anchors_only_with_a_block_above_the_last_section():
    cfg: dict = {}
    rows = [{"key": "pagetext"}, {"key": "contact", "enabled": True}, TEXT]
    assert detail_parts.lift(cfg, "info", rows) == [TEXT]
    rows = [{"key": "pagetext"}, TEXT, {"key": "contact", "enabled": False}]
    out = detail_parts.lift(cfg, "info", rows)
    assert out == [{"key": "pagetext"}, TEXT, {"key": "contact"}] and cfg["about_contact"] is False
    # текст своей страницы не скрывается даже присланным `enabled: False`
    assert detail_parts.lift({}, "seite:x", [{"key": "pagetext", "enabled": False}, TEXT]) == [TEXT]
