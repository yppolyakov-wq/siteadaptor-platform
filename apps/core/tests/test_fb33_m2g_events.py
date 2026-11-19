"""FB-33 M2g-1: события и туры — «Groups & companies», «Weitere Termine» и приватный выезд тура
строками схемы, которые скрываются на месте (не двигаются, не якоря своих блоков)."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core import detail_parts, detail_sections, object_structure, site_schema
from apps.core.tests import test_fb33_m2g_before as before
from apps.core.tests.test_fb31p5_object_schema import _code, _tenant, can_edit  # noqa: F401
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db
frozen_now = before.frozen_now
B1 = {"key": "text", "id": "b1", "data": {"title": "Zwischen", "body": "x"}}
IN_PLACE = ("groups", "more_dates", "private_tour")


@pytest.fixture(autouse=True)
def _urlconf(settings, frozen_now):
    settings.ROOT_URLCONF = "config.urls_tenant"


# ── ядро ──


def test_in_place_sections_are_not_in_the_flow_order_or_anchors():
    assert detail_sections.in_place_keys("events") == frozenset(IN_PLACE)
    assert not set(IN_PLACE) & set(detail_parts.full_order({}, "events"))
    assert not set(IN_PLACE) & set(siteconfig.event_detail_order({}))
    assert not set(IN_PLACE) & detail_parts.anchor_keys("event_detail")
    # блок после строки «на месте» — хвост (как после последнего раздела)
    keys = list(detail_parts.full_order({}, "events"))
    rows = [{"key": k} for k in keys] + [{"key": "groups"}, B1]
    a = detail_parts.anchors(rows, "event_detail", keys)
    assert a["tail"] == ["b1"]


def test_object_hosts_see_only_their_own_in_place_sections():
    assert detail_parts.in_place_keys("event_detail") == IN_PLACE
    assert detail_parts.in_place_keys("event:" + "a" * 32) == ("groups", "more_dates")
    assert detail_parts.in_place_keys("tour:" + "a" * 32) == ("private_tour",)


def test_stored_own_order_cannot_pull_an_in_place_section_into_the_flow():
    class Obj:
        page_override = {"order": ["groups", "idea"]}

    order = object_structure.effective_full_order({}, "events", Obj())
    assert order[0] == "idea" and "groups" not in order


# ── схема ──


def test_schema_rows_follow_booking_are_fixed_and_say_whose_they_are():
    cfg = siteconfig.normalize({"page_blocks": {"event_detail": [B1]}})
    rows = site_schema.blocks_for(cfg, "event")
    keys = [r["key"] for r in rows]
    at = keys.index("kauf")
    assert keys[at + 1 : at + 4] == list(IN_PLACE) and keys[-1] == "text"
    by = {r["key"]: r for r in rows}
    for key in IN_PLACE:
        assert by[key]["fixed"] and not by[key]["can_up"] and not by[key]["can_down"]
        assert not by[key]["pinned"], "скрыть можно"
    assert by["groups"]["label"].endswith("nur Veranstaltungen")
    assert by["private_tour"]["label"].endswith("nur Touren")


def test_in_place_row_only_hides():
    items = detail_parts.edit_rows({}, "event_detail", [B1])
    for op, value in (("up", ""), ("down", ""), ("move", "before:idea"), ("width", "w12")):
        with pytest.raises(site_schema.SchemaError):
            site_schema.mutate(items, "event", op, "groups", value=value)
    site_schema.mutate(items, "event", "toggle", "groups")
    assert next(i for i in items if i.get("key") == "groups")["enabled"] is False


def test_owner_hides_groups_and_dates_and_the_page_drops_them():
    from apps.core.tests.test_fb27_r2_draft import Browser

    tenant = _tenant("events")
    b = Browser(tenant)
    b.post(seite="event", op="toggle", ref="groups")
    b.post(seite="event", op="toggle", ref="more_dates")
    b.post(seite="event", op="save")
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["event_detail"]["hidden"] == ["groups", "more_dates"]
    assert "order" not in cfg["event_detail"] or not set(IN_PLACE) & set(
        cfg["event_detail"]["order"]
    )
    assert not (cfg.get("page_blocks") or {}).get("event_detail"), "строки «на месте» не хранятся"
    html = before.event_html(cfg)
    assert "Gruppenanfrage" not in html, "нет «Groups & companies»"
    assert "Weitere Termine" not in html
    shown = before.event_html({})
    assert "Gruppenanfrage" in shown and "Weitere Termine" in shown


def test_hidden_series_costs_no_query():
    cfg = {"event_detail": {"hidden": ["more_dates"]}}
    with CaptureQueriesContext(connection) as hidden:
        before.event_html(cfg)
    with CaptureQueriesContext(connection) as shown:
        before.event_html({})
    assert len(hidden) < len(shown)


def test_stale_draft_without_in_place_rows_keeps_their_visibility():
    cfg = {"event_detail": {"hidden": ["groups"]}}
    keys = list(detail_parts.full_order(cfg, "events"))
    rows = detail_parts.lift(cfg, "event_detail", [{"key": k} for k in keys] + [B1])
    assert cfg["event_detail"]["hidden"] == ["groups"]
    assert all(r.get("key") not in IN_PLACE for r in rows)


def test_object_schema_of_an_event_and_a_tour(can_edit):  # noqa: F811
    from apps.core.tests import test_fb31p5_object_golden as og
    from apps.core.tests.test_fb27_r2_draft import Browser
    from apps.events.models import Tour

    ev = og._event()
    tour = Tour.objects.create(title="Alpen", slug="alpen", is_published=True)
    b = Browser(_tenant("events"))
    html = b.get(f"?seite={_code('event', ev)}")
    assert 'data-schema-block="groups"' in html
    assert 'data-schema-block="private_tour"' not in html
    html = b.get(f"?seite={_code('tour', tour)}")
    assert 'data-schema-block="private_tour"' in html
    assert 'data-schema-block="groups"' not in html
    b.post(seite=_code("tour", tour), op="toggle", ref="private_tour")
    b.post(seite=_code("tour", tour), op="save")
    tour.refresh_from_db()
    assert tour.page_override == {"hidden": ["private_tour"]}


# ── тур ──


def test_hidden_private_tour_drops_the_box_and_the_head_button():
    cfg = {"event_detail": {"hidden": ["private_tour"]}}
    assert before.tour_html({}).count("/anfrage/?betreff=") == 2
    html = before.tour_html(cfg)
    assert "/anfrage/?betreff=" not in html, "ни блока, ни кнопки «Eigene Termine»"
    assert 'id="termine"' in html, "выезды — бронь, остаются"
    bare = before.tour_html(cfg, departures=False)
    assert "/anfrage/?betreff=" not in bare and "kind=tour" in bare, (
        "без выездов — «Termine anfragen»"
    )


# ── ревью M2g: перенос блока рядом со строкой «на месте» — редактор = страница ──


def _keys(items):
    return [i.get("id") or i["key"] for i in items]


def test_block_moved_up_jumps_over_in_place_rows_of_the_event():
    items = detail_parts.edit_rows({}, "event_detail", [B1])
    assert _keys(items)[-4:] == [*IN_PLACE, "b1"]
    site_schema.mutate(items, "event", "up", "b1")
    keys = _keys(items)
    assert keys.index("b1") == keys.index("certifications") - 1, "сразу над последним разделом"
    site_schema.mutate(items, "event", "down", "b1")
    assert _keys(items)[-1] == "b1", "обратно — в хвост, мимо строк «на месте»"


def test_block_dropped_on_an_in_place_row_lands_where_the_page_draws_it():
    for value in ("before:groups", "after:more_dates"):
        items = detail_parts.edit_rows({}, "event_detail", [B1])
        site_schema.mutate(items, "event", "up", "b1")
        site_schema.mutate(items, "event", "move", "b1", value=value)
        keys = _keys(items)
        assert keys.index("b1") == keys.index("private_tour") + 1, value
        cfg: dict = {}
        rows = detail_parts.lift(cfg, "event_detail", items)
        keys_all = list(detail_parts.full_order({}, "events"))
        assert detail_parts.anchors(rows, "event_detail", keys_all)["tail"] in (["b1"], [])
