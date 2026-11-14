"""FB-29 R5: своя структура и свои блоки — у номера, события и акции (как у товара и
услуги, тем же модулем `object_structure`)."""

import pathlib
import uuid
from types import SimpleNamespace

import pytest

from apps.core import object_structure as ost
from apps.core import site_schema
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


def _obj(**override):
    return SimpleNamespace(page_override=override)


def test_models_carry_the_override_field():
    from apps.events.models import Event
    from apps.promotions.models import Promotion
    from apps.stays.models import StayUnit

    for model in (StayUnit, Event, Promotion):
        assert model._meta.get_field("page_override").default is dict, model


def test_room_and_event_sections_follow_the_object():
    cfg = {"stay_detail": {"hidden": ["similar"]}}
    assert ost.effective_hidden(cfg, "stays", _obj()) == {"similar"}
    assert ost.effective_hidden(cfg, "stays", _obj(shown=["similar"], hidden=["reviews"])) == {
        "reviews"
    }
    assert ost.clean({"hidden": ["faq", "nope"]}, "events") == {"hidden": ["faq"]}


def test_event_order_stays_shared_and_the_object_only_hides_or_shows():
    cfg = {"event_detail": {"order": ["faq", "program"], "hidden": ["venue"]}}
    shared = siteconfig.event_detail_order(cfg)
    assert ost.effective_order(cfg, "events", _obj()) == shared
    own = ost.effective_order(cfg, "events", _obj(hidden=["faq"], shown=["venue"]))
    assert "faq" not in own and "venue" in own
    assert own[0] == "program", "порядок общий"


def test_promotion_has_no_sections_only_own_blocks():
    assert ost.clean({"hidden": ["description"], "blocks_first": True}, ost.MODULES["promo"]) == {
        "blocks_first": True
    }
    panel = ost.panel({}, "promo", _obj())
    assert panel["rows"] == [] and panel["layouts"] == []


def test_hosts_for_the_new_kinds():
    for kind in ("stay", "event", "promo"):
        host = f"{kind}:{uuid.uuid4().hex}"
        assert siteconfig.is_page_block_host(host), host
        assert site_schema.place_capable(host)
    assert not siteconfig.is_page_block_host("promotion:" + "a" * 32)


def test_only_existing_objects_get_a_row():
    from apps.stays.models import StayUnit

    unit = StayUnit.objects.create(name="Doppelzimmer")
    code = ost.schema_code("stay", unit)
    assert (
        code == f"stay@stay:{unit.pk.hex}" and site_schema.host_for(code) == f"stay:{unit.pk.hex}"
    )
    assert site_schema.host_for(f"stay@stay:{uuid.uuid4().hex}") == ""
    assert site_schema.host_for(f"event@stay:{unit.pk.hex}") == ""


def test_detail_templates_render_own_blocks_on_both_sides():
    for name, kind, var, host in (
        ("stay_detail.html", "stay", "unit", "stay_detail"),
        ("event_detail.html", "event", "event", "event_detail"),
        ("promotion_detail.html", "promo", "promotion", "promo_detail"),
    ):
        src = pathlib.Path("templates/storefront", name).read_text()
        before = src.index(f'{{% object_blocks "{kind}" {var} "before" %}}')
        shared = src.index(f'{{% page_blocks "{host}" %}}')
        after = src.index(f'{{% object_blocks "{kind}" {var} %}}')
        assert before < shared < after, name


def test_cabinet_forms_carry_the_section():
    for name in (
        "templates/stays/unit_page.html",
        "templates/events/event_form.html",
        "templates/promotions/promotion_form.html",
    ):
        assert "tenant/_object_structure.html" in pathlib.Path(name).read_text(), name


def test_event_form_saves_only_with_the_sentinel(settings):
    from django.utils import timezone

    from apps.events.models import Event

    settings.ROOT_URLCONF = "config.urls_tenant"
    event = Event.objects.create(title="Yoga", starts_at=timezone.now())
    assert ost.apply_post(event, "event", {"ps_faq": "hide"}) == []
    changed = ost.apply_post(event, "event", {"page_override_present": "1", "ps_faq": "hide"})
    assert changed == ["page_override"] and event.page_override == {"hidden": ["faq"]}


def test_views_read_the_object_override():
    stays = pathlib.Path("apps/stays/public_views.py").read_text()
    events = pathlib.Path("apps/events/public_views.py").read_text()
    assert 'object_structure.effective_hidden(_raw, "stays", unit)' in stays
    assert 'object_structure.effective_order(_raw, "events", event)' in events
    for src, kind in ((pathlib.Path("apps/stays/views.py").read_text(), '"stay"'),
                      (pathlib.Path("apps/events/views.py").read_text(), '"event"'),
                      (pathlib.Path("apps/promotions/views.py").read_text(), '"promo"')):  # fmt: skip
        assert "object_structure.apply_post(" in src and kind in src
