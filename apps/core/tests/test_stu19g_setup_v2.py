"""STU-19g: the setup helper creates services, rooms, events and offers too.

Locks:
* the rule planner recognises the four new entities in the cabinet languages;
* short stems match only at a word start ("Soda" is not a room);
* every field a step names exists on the real form (Django form or inline POST form);
* the link really prefills the create form (GET only; an event date is never prefilled);
* the AI may only pick a duration the owner literally wrote;
* Ctrl+K offers "Anlegen" only for a phrase naming something the user may create.
"""

import re
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.conf import settings as dj_settings
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import setup_assistant as sa
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

NEW = [sa.ENTITY_SERVICE, sa.ENTITY_ROOM, sa.ENTITY_EVENT, sa.ENTITY_PROMO]
ALL = [sa.ENTITY_CATEGORY, sa.ENTITY_PRODUCT, *NEW]


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def tenant():
    return TenantFactory(business_type="friseur")


def _req(tenant, path, data=None):
    request = RequestFactory().get(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"g-{o}", email=f"g-{o}@t.de", password="pw12345678"
    )
    request.tenant = tenant
    return request


def _field(step, name):
    return next(f for f in step.fields if f.name == name)


@pytest.mark.parametrize(
    "text,entity",
    [
        ("neue Leistung Haarschnitt 25 € 45 min", sa.ENTITY_SERVICE),
        ("новая услуга Стрижка 25 €", sa.ENTITY_SERVICE),
        ("Zimmer Doppelzimmer Seeblick 95 €", sa.ENTITY_ROOM),
        ("yeni oda Deniz 80 €", sa.ENTITY_ROOM),
        ("Workshop Brotbacken 39 €", sa.ENTITY_EVENT),
        ("мероприятие Йога на крыше", sa.ENTITY_EVENT),
        ("Aktion Herbst-Rabatt 9,90 €", sa.ENTITY_PROMO),
    ],
)
def test_new_entities_are_recognised(tenant, text, entity):
    plan = sa.plan_from_rules(text, tenant, ALL)
    assert plan.steps and plan.steps[0].entity == entity


def test_service_step_carries_name_price_duration(tenant):
    (step,) = sa.plan_from_rules("neue Leistung Haarschnitt 25 € 45 min", tenant, ALL).steps
    assert _field(step, "name").value == "Haarschnitt"
    assert _field(step, "price_eur").value == "25,00"
    assert _field(step, "duration").value == "45"
    # UX-D D2.2: своя страница создания услуги (без ?neu=1#neu)
    assert step.form_url.startswith("/dashboard/booking/leistungen/neu/?")
    assert "duration=45" in step.form_url


@pytest.mark.parametrize(
    "text",
    [
        "Soda 2 €",
        "Zimmerpflanze 12 €",
        "Eventuell Brot 2 €",
        "Transaktion Gebühr 2 €",
        "Kundenservice Paket 5 €",
    ],
)
def test_stem_inside_another_word_is_not_an_entity(tenant, text):
    plan = sa.plan_from_rules(text, tenant, ALL)
    assert [s.entity for s in plan.steps] == [sa.ENTITY_PRODUCT]


def test_palette_ignores_names_that_merely_contain_a_stem(tenant, monkeypatch):
    from apps.core import permissions

    monkeypatch.setattr(permissions, "has_perm", lambda user, key: True)
    monkeypatch.setattr(sa, "allowed_entities", lambda t, u: ALL)
    assert sa.palette_section(tenant, SimpleNamespace(pk=1), "Zimmermann") is None


def test_minutes_unit_does_not_eat_words(tenant):
    (step,) = sa.plan_from_rules("Produkt 3 минеральные воды 2 €", tenant, ALL).steps
    assert "минеральные" in _field(step, "name_de").value
    assert sa._duration_in("Стрижка 40 мин") == "40"
    assert sa._duration_in("Стрижка 40 минут") == "40"


def test_disallowed_new_entity_is_skipped(tenant):
    plan = sa.plan_from_rules("Zimmer Seeblick 95 €", tenant, [sa.ENTITY_SERVICE])
    assert plan.steps == ()


def test_entity_fields_exist_on_forms(tenant):
    """Event/offer: the Django form; service/room: the inline "＋" POST form."""
    from apps.events.forms import EventForm
    from apps.promotions.forms import PromotionForm

    django_forms = {
        sa.ENTITY_EVENT: set(EventForm().fields),
        sa.ENTITY_PROMO: set(PromotionForm(tenant=tenant).fields),
    }
    inline = {
        sa.ENTITY_SERVICE: ("booking/_service_new_form.html", "<form"),
        sa.ENTITY_ROOM: ("stays/units.html", 'value="unit"'),
    }
    for entity in NEW:
        names = [f for f, _l, _r in sa.ENTITIES[entity]["fields"]]
        if entity in django_forms:
            assert set(names) <= django_forms[entity], entity
            continue
        path, marker = inline[entity]
        src = (Path(dj_settings.BASE_DIR) / "templates" / path).read_text()
        form = src[src.index(marker) :]
        form = form[: form.index("</form>")]
        for name in names:
            assert re.search(rf'name="{name}"', form), (entity, name)


def test_service_and_room_forms_are_prefilled(tenant):
    from apps.booking import views as booking_views
    from apps.stays import views as stays_views

    body = booking_views.service_new(
        _req(
            tenant,
            "/dashboard/booking/leistungen/neu/",
            {"name": "Haarschnitt", "price_eur": "25,00", "duration": "45"},
        )
    ).content.decode()
    assert 'value="Haarschnitt"' in body and 'value="25,00"' in body and 'value="45"' in body

    body = stays_views.units(
        _req(tenant, "/dashboard/stays/units/", {"neu": "1", "name": "Seeblick", "price_eur": "95"})
    ).content.decode()
    assert 'value="Seeblick"' in body and 'value="95"' in body


def test_event_and_offer_forms_are_prefilled(tenant):
    from apps.events import views as event_views
    from apps.promotions import views as promo_views

    body = event_views.event_create(
        _req(
            tenant,
            "/dashboard/events/new/",
            {"title": "Brotbacken", "price_eur": "39,00", "starts_at": "2030-01-01T10:00"},
        )
    ).content.decode()
    assert 'value="Brotbacken"' in body and "39" in body
    assert "2030-01-01" not in body  # the date is typed by the owner

    body = promo_views.promotion_create(
        _req(tenant, "/promotions/new/", {"title_de": "Herbst-Rabatt"})
    ).content.decode()
    assert 'value="Herbst-Rabatt"' in body


def test_prefill_ignores_post_and_unknown_fields(tenant):
    request = _req(tenant, "/x/", {"name": "A", "evil": "x"})
    assert sa.prefill(request, sa.ENTITY_SERVICE) == {"name": "A"}
    post = RequestFactory().post("/x/?name=A", {"name": "B"})
    assert sa.prefill(post, sa.ENTITY_SERVICE) == {}


def test_ai_duration_must_be_written_by_owner(tenant):
    text = "Leistung Haarschnitt 25 € 45 min"
    data = {
        "steps": [
            {"entity": "service", "name": "Haarschnitt", "duration_text": "60 min"},
            {"entity": "service", "name": "Haarschnitt", "duration_text": "45 min"},
        ]
    }
    plan = sa._from_ai(data, text, tenant, ALL)
    assert [_field(s, "duration").value for s in plan.steps] == ["", "45"]


def test_ai_schema_lists_every_entity():
    enum = sa.SCHEMA["properties"]["steps"]["items"]["properties"]["entity"]["enum"]
    assert set(enum) == set(sa.ENTITIES)


def test_palette_offers_create_only_for_creatable_phrase(tenant, monkeypatch):
    from apps.core import permissions

    monkeypatch.setattr(permissions, "has_perm", lambda user, key: True)
    monkeypatch.setattr(sa, "allowed_entities", lambda t, u: [sa.ENTITY_SERVICE])
    user = SimpleNamespace(pk=1)
    sec = sa.palette_section(tenant, user, "neue Leistung Haarschnitt")
    assert sec and sec["key"] == "create"
    assert "frage=neue+Leistung+Haarschnitt" in sec["items"][0]["url"]
    assert sa.palette_section(tenant, user, "Zimmer Seeblick") is None  # not allowed
    assert sa.palette_section(tenant, user, "Müller") is None  # not a create phrase
    assert sa.palette_section(tenant, user, "ab") is None  # too short


def test_palette_link_goes_to_the_open_helper_screen(tenant, monkeypatch):
    """STU-19i: the palette opens the helper's own screen (open to the whole team) —
    no website.view gate any more."""
    monkeypatch.setattr(sa, "allowed_entities", lambda t, u: [sa.ENTITY_SERVICE])
    sec = sa.palette_section(tenant, SimpleNamespace(pk=1), "neue Leistung Haarschnitt")
    assert sec["items"][0]["url"].startswith("/dashboard/anlegen/?frage=")


def test_palette_js_does_not_double_encode_urls():
    """The server sends encoded local paths — encodeURI() on top turned "€" in a helper
    link into the literal text "%E2%82%AC" (found on the Playwright stand)."""
    js = (Path(dj_settings.BASE_DIR) / "static/js/cabinet.js").read_text(encoding="utf-8")
    assert "encodeURI(it.url)" not in js
    assert 'palEsc(u).replace(/"/g, "&quot;")' in js
