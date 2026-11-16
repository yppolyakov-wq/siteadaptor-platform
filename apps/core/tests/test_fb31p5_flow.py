"""FB-31 P5 R1–R3: свои блоки между разделами детали события/тура (якоря разделов)."""

import pytest

from apps.core import detail_parts
from apps.core.tests import test_fb31p5_detail_golden as g
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db
B1 = {"key": "text", "id": "b1", "data": {"title": "Zwischen-Hinweis", "body": "x"}}
B2 = {"key": "text", "id": "b2", "data": {"title": "Am Ende", "body": "y"}}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_anchors_place_blocks_after_sections_and_keep_the_tail():
    rows = [{"key": "idea"}, B1, {"key": "bring"}, B2]
    a = detail_parts.anchors(rows, "event_detail")
    assert a["after"] == {"idea": ["b1"]} and a["tail"] == ["b2"] and a["placed"]
    assert detail_parts.anchors([B1, B2], "event_detail") == {
        "placed": False,
        "lead": [],
        "after": {},
        "tail": ["b1", "b2"],
    }


def test_hidden_section_keeps_its_blocks_in_place():
    rows = [{"key": "idea"}, B1, {"key": "bring"}]
    items = detail_parts.flow(rows, "event_detail", ["bring"], ["idea", "bring"])
    assert items == [{"part": "ids:b1"}, {"section": "bring"}]


def test_canonical_form_is_not_stored():
    """Все блоки после последнего раздела = прежний хвост: якоря не хранятся."""
    rows = [{"key": "idea"}, {"key": "bring"}, B1]
    plain = siteconfig.normalize_page_blocks({"event_detail": [B1]})
    assert siteconfig.normalize_page_blocks({"event_detail": rows}) == plain
    kept = siteconfig.normalize_page_blocks(
        {"event_detail": [{"key": "idea"}, B1, {"key": "bring"}]}
    )
    assert [r.get("id") or r["key"] for r in kept["event_detail"]] == ["idea", "b1", "bring"]


def _html(kind, rows):
    render = g.RENDER[kind][0]
    return render({"page_blocks": {"event_detail": rows}}).content.decode()


@pytest.mark.parametrize("kind", ["event", "tour"])
def test_block_between_sections_renders_between_them(kind):
    html = _html(kind, [{"key": "idea"}, B1, {"key": "bring"}, B2])
    idea = html.index('data-ed-section="idea"')
    mid = html.index("Zwischen-Hinweis")
    bring = html.index('data-ed-section="bring"')
    assert idea < mid < bring, "блок — между разделами"
    assert html.index("Am Ende") > bring, "после последнего раздела — хвост"
    assert html.count("Zwischen-Hinweis") == 1, "блок не дублируется в хвосте"


def test_tabs_layout_draws_between_blocks_under_the_tabs():
    cfg = {
        "event_detail": {"layout": "tabs"},
        "page_blocks": {"event_detail": [{"key": "idea"}, B1, {"key": "bring"}]},
    }
    html = g.RENDER["event"][0](cfg).content.decode()
    assert html.count("Zwischen-Hinweis") == 1
    assert html.index("Zwischen-Hinweis") > html.index("data-pd-tabs")
