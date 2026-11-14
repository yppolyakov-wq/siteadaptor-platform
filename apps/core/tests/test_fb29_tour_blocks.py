"""FB-29 T1: своя структура страницы и свои блоки — у тура (тем же модулем
`object_structure`, что у товара, услуги, номера, события и акции)."""

import pathlib
import uuid

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import banners, site_schema
from apps.core import object_structure as ost
from apps.events import public_views
from apps.events.models import Event, Tour
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tour(title="Rheinsteig", **kwargs):
    kwargs.setdefault("slug", f"tour-{uuid.uuid4().hex[:8]}")
    kwargs.setdefault("is_published", True)
    return Tour.objects.create(title=title, **kwargs)


def _text(ref, title):
    return {"key": "text", "id": ref, "enabled": True, "data": {"title": title}}


def _page(tour, page_blocks=None, site=None):
    request = RequestFactory().get(f"/tour/{tour.slug}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    config = {**(site or {}), "page_blocks": page_blocks or {}}
    request.tenant = TenantFactory.build(enabled_modules=["events"], site_config=config)
    return public_views.tour_detail(request, slug=tour.slug).content.decode()


def test_kind_registries_stay_in_sync():
    kinds = set(ost.MODULES)
    assert "tour" in kinds
    assert kinds == set(site_schema.OBJECT_KINDS) == set(site_schema._OBJECT_MODELS)
    assert kinds == set(site_schema._OBJECT_EDIT_URLS) == set(siteconfig.OBJECT_HOST_KINDS)
    for kind in kinds:
        assert siteconfig.is_object_host(f"{kind}:{'a' * 32}"), kind


def test_tour_carries_the_override_field():
    assert Tour._meta.get_field("page_override").default is dict


def test_only_an_existing_tour_gets_a_row():
    tour = _tour()
    code = ost.schema_code("tour", tour)
    assert code == f"tour@tour:{tour.pk.hex}"
    assert site_schema.host_for(code) == f"tour:{tour.pk.hex}"
    assert site_schema.host_for(f"tour@tour:{uuid.uuid4().hex}") == ""
    assert site_schema.host_for(f"event@tour:{tour.pk.hex}") == ""
    assert site_schema.host_for(f"tour@event:{tour.pk.hex}") == ""


def test_tour_row_previews_the_tour_address_not_the_event_one():
    tour = _tour(slug="rheinsteig-t1")
    row = site_schema.object_row(siteconfig.normalize({}), ost.schema_code("tour", tour))
    assert row is not None and row.label == "Rheinsteig"
    assert row.preview_url.startswith("/tour/rheinsteig-t1/")


def test_tour_screen_links_back_to_the_tour_form():
    tour = _tour()
    back = site_schema.object_back(ost.schema_code("tour", tour))
    assert back and str(tour.pk) in back["url"] and "tour" in back["url"]


def test_tour_has_sections_but_no_page_layout():
    tour = _tour()
    panel = ost.panel({}, "tour", tour)
    assert panel["rows"] and panel["layouts"] == []
    post = {"page_override_present": "1", "ps_layout": "tabs", "ps_faq": "hide"}
    assert ost.apply_post(tour, "tour", post) == ["page_override"]
    assert tour.page_override == {"hidden": ["faq"]}


def test_form_without_the_sentinel_leaves_the_field_alone():
    tour = _tour(page_override={"hidden": ["faq"]})
    assert ost.apply_post(tour, "tour", {"ps_faq": "show"}) == []
    assert ost.apply_post(tour, "tour", {"page_override_present": "1", "ps_reset": "1"}) == [
        "page_override"
    ]
    assert tour.page_override == {}


def test_untouched_tour_keeps_the_shared_order():
    cfg = {"event_detail": {"order": ["faq", "program"], "hidden": ["venue"]}}
    tour = _tour()
    assert ost.effective_order(cfg, "events", tour) == siteconfig.event_detail_order(cfg)


def test_tour_page_follows_the_tours_own_sections():
    faq = [{"q": "Brauche ich Erfahrung?", "a": "Nein."}]
    tour = _tour(details={"faq": faq})
    assert "Brauche ich Erfahrung?" in _page(tour)
    tour.page_override = {"hidden": ["faq"]}
    tour.save(update_fields=["page_override"])
    assert "Brauche ich Erfahrung?" not in _page(tour)
    other = _tour(title="Moselsteig", details={"faq": faq})
    assert "Brauche ich Erfahrung?" in _page(other), "отличие — только у своего тура"


def test_own_block_shows_only_on_its_tour():
    tour, other = _tour(), _tour(title="Moselsteig")
    blocks = {f"tour:{tour.pk.hex}": [_text("b1", "Nur Rheinsteig T1")]}
    assert _page(tour, blocks).count("Nur Rheinsteig T1") == 1
    assert "Nur Rheinsteig T1" not in _page(other, blocks)


def test_tour_block_never_shows_on_an_event_with_the_same_key():
    """Хост — по виду: блок тура не всплывает у события (и наоборот)."""
    from django.utils import timezone

    tour = _tour()
    event = Event.objects.create(title="Abend", starts_at=timezone.now())
    assert ost.object_host("tour", tour) != ost.object_host("event", tour)
    assert ost.object_host("event", event).startswith("event:")


def test_own_blocks_can_stand_above_the_shared_ones():
    tour = _tour()
    blocks = {
        "event_detail": [_text("s1", "Gemeinsam T1")],
        f"tour:{tour.pk.hex}": [_text("b1", "Eigen T1")],
    }
    body = _page(tour, blocks)
    assert body.index("Gemeinsam T1") < body.index("Eigen T1")
    tour.page_override = {"blocks_first": True}
    tour.save(update_fields=["page_override"])
    body = _page(tour, blocks)
    assert body.index("Eigen T1") < body.index("Gemeinsam T1")


def test_place_block_in_the_tours_own_blocks_silences_the_default_place():
    from django.template import Context, Template

    tour = _tour()
    b = banners.create({"title": "Tourbanner T1", "image": {"url": "/media/hero/a.jpg"}})
    banners.set_show_on(b, keep=[], add=[f"tour:{tour.pk}"])
    place = {"key": "banner", "id": "b1", "enabled": True, "data": {"from_page": True}}
    tpl = Template('{% load siteui %}{% place_banners "tour" tour %}')

    def render(page_blocks):
        request = RequestFactory().get("/")
        request.tenant = TenantFactory.build(site_config={"page_blocks": page_blocks})
        return tpl.render(Context({"request": request, "tour": tour}))

    assert "Tourbanner T1" in render({})
    assert render({f"tour:{tour.pk.hex}": [place]}).strip() == ""
    assert "Tourbanner T1" in render({f"event:{tour.pk.hex}": [place]}), "чужой вид не глушит"


def test_ghost_host_of_a_deleted_tour_is_purged():
    from apps.tenants.models import Tenant

    tour = _tour()
    host = f"tour:{tour.pk.hex}"
    tenant = TenantFactory(
        auto_create_schema=False,
        site_config={
            "page_blocks": {host: [_text("b1", "Weg")]},
            "i18n": {"en": {"page_blocks": {host: {"b1": {"title": "Gone"}}}}},
        },
    )
    assert ost.purge_ghost_hosts(tenant) == 0, "тур жив — блоки целы"
    tour.delete()
    assert ost.purge_ghost_hosts(tenant) == 1
    saved = Tenant.objects.get(pk=tenant.pk).site_config
    assert host not in saved["page_blocks"] and host not in saved["i18n"]["en"]["page_blocks"]


def test_templates_and_views_are_wired():
    src = pathlib.Path("templates/storefront/tour_detail.html").read_text()
    before = src.index('{% object_blocks "tour" tour "before" %}')
    shared = src.index('{% page_blocks "event_detail" %}')
    after = src.index('{% object_blocks "tour" tour %}')
    assert before < shared < after
    form = pathlib.Path("templates/events/tour_form.html").read_text()
    assert "tenant/_object_structure.html" in form
    assert form.index("_object_structure.html") < form.index('value="delete"')
    views = pathlib.Path("apps/events/views.py").read_text()
    assert 'object_structure.apply_post(tour, "tour"' in views


def _cabinet_post(tour, data):
    from types import SimpleNamespace

    from django.contrib.messages.storage.fallback import FallbackStorage

    from apps.events import views

    request = RequestFactory().post("/", data)
    request.tenant = TenantFactory.build(enabled_modules=["events"])
    request.user = SimpleNamespace(is_authenticated=True)
    request.session = {}
    request._messages = FallbackStorage(request)
    return views.tour_edit.__wrapped__(request, pk=tour.pk)


def test_tour_form_saves_the_structure_with_the_other_fields():
    tour = _tour(page_override={"hidden": ["venue"]})
    base = {"title": "Rheinsteig neu", "slug": tour.slug}
    assert _cabinet_post(tour, base).status_code == 302
    tour.refresh_from_db()
    assert tour.title == "Rheinsteig neu" and tour.page_override == {"hidden": ["venue"]}, "W0"
    post = {**base, "page_override_present": "1", "ps_faq": "hide", "ps_blocks_first": "1"}
    assert _cabinet_post(tour, post).status_code == 302
    tour.refresh_from_db()
    assert tour.page_override == {"hidden": ["faq"], "blocks_first": True}
    assert tour.title == "Rheinsteig neu"


def test_crafted_codes_reach_no_host():
    from django.utils import timezone

    event = Event.objects.create(title="Abend", starts_at=timezone.now())
    assert site_schema.host_for(f"tour@tour:{event.pk.hex}") == "", "pk события — не тур"
    assert not siteconfig.is_object_host("tour:" + "a" * 32 + "\n")
    assert site_schema._page_type("tour") is None, "без объекта строки «tour» нет"


def test_tour_row_needs_the_events_module():
    tour = _tour()
    code = ost.schema_code("tour", tour)
    off = TenantFactory.build(disabled_modules=["events"])
    with pytest.raises(site_schema.SchemaError):
        site_schema.resolve(off, code)


# ───────── T2: Студия «Aufbau ändern» ведёт на строку объекта ─────────


def test_studio_link_opens_the_objects_own_row_when_it_has_blocks():
    tour = _tour(slug="rheinsteig-t2")
    host = f"tour:{tour.pk.hex}"
    plain = TenantFactory.build(enabled_modules=["events"], site_config={})
    assert site_schema.url_for_path(plain, "/tour/rheinsteig-t2/").endswith("?seite=event")
    own = TenantFactory.build(
        enabled_modules=["events"], site_config={"page_blocks": {host: [_text("b1", "Eigen")]}}
    )
    url = site_schema.url_for_path(own, "/tour/rheinsteig-t2/")
    assert url.endswith(f"seite=tour%40tour%3A{tour.pk.hex}")
    assert site_schema.url_for_path(own, "/tour/gibt-es-nicht/").endswith("?seite=event")


def test_studio_link_for_an_event_with_own_blocks():
    from django.utils import timezone

    event = Event.objects.create(title="Abend", starts_at=timezone.now())
    host = f"event:{event.pk.hex}"
    own = TenantFactory.build(
        enabled_modules=["events"], site_config={"page_blocks": {host: [_text("b1", "Eigen")]}}
    )
    assert site_schema.url_for_path(own, f"/veranstaltung/{event.pk}/").endswith(
        f"seite=event%40event%3A{event.pk.hex}"
    )
    ghost = uuid.uuid4()
    stale = TenantFactory.build(
        enabled_modules=["events"],
        site_config={"page_blocks": {f"event:{ghost.hex}": [_text("b1", "Alt")]}},
    )
    assert site_schema.url_for_path(stale, f"/veranstaltung/{ghost}/").endswith("?seite=event"), (
        "объекта нет — общая строка"
    )
