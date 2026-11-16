"""FB-31 P5 R8: своя схема одного объекта — свои блоки между разделами, свой порядок
«nur hier» (событие, тур, услуга), у раздела сначала общие блоки, потом свои
(`docs/fb31-p5-detail-plan-2026-11-16.md` §11, §12)."""

import pytest

from apps.core import detail_parts, object_structure
from apps.core.tests import test_fb31p5_detail_golden as g
from apps.core.tests import test_fb31p5_object_golden as og
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

SHARED = {"key": "text", "id": "t-sh", "data": {"title": "Allgemein", "body": "Für alle"}}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _pos(html, *needles):
    return [html.index(n) for n in needles]


# ── ядро ──


def test_object_host_keeps_section_anchors_and_drops_them_when_useless():
    host = "event:" + "a" * 32
    rows = [{"key": "idea"}, og.OWN, {"key": "faq"}]

    def shape(blocks):
        return [(b["key"], b.get("id")) for b in blocks]

    assert shape(siteconfig.normalize_page_blocks({host: rows})[host]) == shape(rows)
    tail_only = [{"key": "idea"}, {"key": "faq"}, og.OWN]
    assert shape(siteconfig.normalize_page_blocks({host: tail_only})[host]) == shape([og.OWN])


def test_flow_puts_shared_blocks_first_then_own_at_the_same_section():
    rows = [{"key": "idea"}, SHARED, {"key": "faq"}]
    own = {"host": "event:x", "lead": [], "after": {"idea": ["t-own"]}, "tail": []}
    items = detail_parts.flow(rows, "event_detail", ["idea", "faq"], ["idea", "faq"], own=own)
    assert items == [
        {"section": "idea"},
        {"part": "ids:t-sh"},
        {"part": "ids:t-own", "host": "event:x"},
        {"section": "faq"},
    ]


def test_flow_without_shared_anchors_still_places_own_blocks():
    own = {"host": "event:x", "lead": ["t-own"], "after": {}, "tail": []}
    items = detail_parts.flow([SHARED], "event_detail", ["idea"], ["idea"], own=own)
    assert items == [{"part": "ids:t-own", "host": "event:x"}, {"section": "idea"}]


def test_lift_never_writes_shared_order_for_an_object_host():
    cfg: dict = {}
    host = "event:" + "b" * 32
    assert detail_parts.module_of(host) == "" and detail_parts.section_keys(host)
    items = [{"key": "faq", "enabled": False}, og.OWN]
    from apps.core import site_schema

    site_schema.store_items(cfg, False, host, items)
    assert "event_detail" not in cfg, "общий порядок/видимость не трогаются"


# ── хранение порядка объекта ──


def test_own_order_only_where_order_moves():
    assert object_structure.clean({"order": ["faq", "idea"]}, "events") == {
        "order": ["faq", "idea"]
    }
    assert object_structure.clean({"order": ["reviews"]}, "catalog") == {}, "товар — постоянный"
    ev = og._event()
    ev.page_override = {"order": ["faq", "idea"]}
    full = object_structure.effective_full_order({}, "events", ev)
    assert full[:2] == ["faq", "idea"] and set(full) == set(
        detail_parts.section_keys("event_detail")
    )
    assert object_structure.deviations(ev, "events") == 1


def test_tab_save_keeps_own_order_and_reset_clears_it():
    ev = og._event()
    ev.page_override = {"order": ["faq", "idea"]}
    object_structure.apply_post(ev, "event", {"page_override_present": "1", "ps_layout": "tabs"})
    assert ev.page_override == {"layout": "tabs", "order": ["faq", "idea"]}
    object_structure.apply_post(ev, "event", {"page_override_present": "1", "ps_reset": "1"})
    assert ev.page_override == {}


# ── витрина ──


def _render(kind, obj, cfg):
    return og._view(kind, obj, cfg).content.decode()


def test_event_own_block_stands_after_its_section_and_after_shared_blocks():
    ev = og._event()
    host = f"event:{ev.pk.hex}"
    cfg = {
        "page_blocks": {
            "event_detail": [{"key": "for_whom"}, SHARED, {"key": "idea"}],
            host: [{"key": "for_whom"}, og.OWN, {"key": "idea"}],
        }
    }
    html = _render("event", ev, cfg)
    sec, sh, own, nxt = _pos(
        html, 'data-ed-section="for_whom"', "Für alle", "Eigener Block", 'data-ed-section="idea"'
    )
    assert sec < sh < own < nxt
    assert html.count("Eigener Block") == 1, "не повторяется в хвосте"


def test_event_own_order_is_used_on_the_page():
    ev = og._event()
    ev.page_override = {"order": ["faq", "for_whom"]}
    ev.save(update_fields=["page_override"])
    html = _render("event", ev, {})
    faq, whom = _pos(html, 'data-ed-section="faq"', 'data-ed-section="for_whom"')
    assert faq < whom


def test_tour_own_block_between_sections():
    tour = og._tour()
    host = f"tour:{tour.pk.hex}"
    html = _render(
        "tour", tour, {"page_blocks": {host: [{"key": "idea"}, og.OWN, {"key": "bring"}]}}
    )
    idea, own, bring = _pos(
        html, 'data-ed-section="idea"', "Eigener Block", 'data-ed-section="bring"'
    )
    assert idea < own < bring


def test_service_own_block_between_sections():
    svc = og._service()
    host = f"service:{svc.pk.hex}"
    keys = list(detail_parts.section_keys("service_detail"))
    rows = [{"key": keys[0]}, og.OWN, *[{"key": k} for k in keys[1:]]]
    html = _render("service", svc, {"page_blocks": {host: rows}})
    assert "Eigener Block" in html and html.count("Eigener Block") == 1


@pytest.mark.parametrize("kind,first", [("product", "description"), ("stay", "description")])
def test_fixed_pages_place_own_blocks_before_reviews_and_after_shared(kind, first):
    obj = og.MAKE[kind]()
    host = f"{kind}:{obj.pk.hex}"
    shared_host = og.SHARED_HOST[kind]
    keys = list(detail_parts.section_keys(shared_host))
    cfg = {
        "page_blocks": {
            shared_host: [{"key": first}, SHARED, *[{"key": k} for k in keys if k != first]],
            host: [{"key": first}, og.OWN, *[{"key": k} for k in keys if k != first]],
        }
    }
    html = _render(kind, obj, cfg)
    sh, own = _pos(html, "Für alle", "Eigener Block")
    assert sh < own and html.count("Eigener Block") == 1


def test_promo_keeps_its_own_blocks_in_one_piece():
    assert detail_parts.own_tail({}, "promo", object()) is None


def test_without_anchors_pages_stay_as_before():
    # эталоны R8a — главный замок; здесь — что старый путь не задет
    ev = og._event()
    host = f"event:{ev.pk.hex}"
    html = _render("event", ev, {"page_blocks": {host: [og.OWN]}})
    assert html.count("Eigener Block") == 1
    assert g.TEXT["data"]["title"] not in html
