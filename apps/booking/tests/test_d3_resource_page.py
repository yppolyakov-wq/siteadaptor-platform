"""UX-D D3.1: страница ресурса — вкладки рисует сервер, всё о ресурсе — одна форма.

Раньше ресурс правился в свёрнутой карточке списка семью формами; «Plätze» и «Anzahlung»
сохранялись одной, профиль мастера — другой, имя после создания не менялось вовсе."""

import re
import uuid
from datetime import time
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.booking import views_resources as vr
from apps.booking.models import AvailabilityRule, Resource, Service
from apps.core.models import Membership
from apps.core.tests.form_post import form_post
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[3]

SAVED = (
    "name",
    "sort_order",
    "capacity",
    "counts_party_size",
    "bookable_online",
    "deposit_cents",
    "require_manual_confirm",
    "seats",
    "zone",
    "min_seats",
    "title",
    "bio",
    "is_active",
)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, role=Membership.ROLE_OWNER):
    req = getattr(RequestFactory(), method)("/dashboard/booking/ressourcen/x/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(business_type="restaurant", disabled_modules=[])
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": role})
    return req


def _table(**kw):
    defaults = {
        "name": "Tisch 1",
        "type": Resource.TYPE_TABLE,
        "capacity": 1,
        "seats": 4,
        "zone": "Terrasse",
        "deposit_cents": 550,
        "require_manual_confirm": True,
        "min_seats": 2,
        "sort_order": 3,
    }
    defaults.update(kw)
    return Resource.objects.create(**defaults)


def _staff(**kw):
    defaults = {
        "name": "Anna",
        "type": Resource.TYPE_STAFF,
        "title": "Stylistin",
        "bio": "Seit 2010",
        "deposit_cents": 1000,
    }
    defaults.update(kw)
    return Resource.objects.create(**defaults)


def _page(r, role=Membership.ROLE_OWNER, **get):
    return vr.resource_edit(_req(data=get, role=role), pk=r.pk).content.decode()


def _post(r, data, role=Membership.ROLE_OWNER):
    req = _req("post", data, role=role)
    resp = vr.resource_edit(req, pk=r.pk)
    return resp, [(m.level_tag, str(m)) for m in get_messages(req)]


def _snap(r):
    r.refresh_from_db()
    return {f: getattr(r, f) for f in SAVED}


def _tabs(html):
    return re.findall(r'<button[^>]*data-pf-tab="([a-z]+)"', html)


def test_tabs_depend_on_type():
    assert _tabs(_page(_table())) == ["basis", "zeiten", "buchung", "tisch"]
    assert _tabs(_page(_staff())) == ["basis", "zeiten", "buchung", "profil"]
    room = Resource.objects.create(name="Saal", type=Resource.TYPE_ROOM)
    assert _tabs(_page(room)) == ["basis", "zeiten", "buchung"]


@pytest.mark.parametrize("tab", ["zeiten", "buchung", "tisch"])
def test_tab_param_selects_the_tab(tab):
    html = _page(_table(), tab=tab)
    assert re.search(rf'data-pf-tab="{tab}"[^>]*aria-selected="true"', html)
    form = re.search(r'<form id="resource-form"[^>]*>', html).group(0)
    assert (" hidden" in form) == (tab == "zeiten")


def test_foreign_or_junk_tab_falls_back_to_basic_data():
    html = _page(_staff(), tab="tisch")  # у мастера нет вкладки «Tisch»
    assert re.search(r'data-pf-tab="basis"[^>]*aria-selected="true"', html)
    assert 'name="seats"' not in html


def test_one_form_without_nested_forms():
    _data, p = form_post(_page(_table()), "resource-form")
    assert p.nested_forms == 0
    for name in ("name", "sort_order", "capacity", "deposit_eur", "seats", "zone", "min_seats"):
        assert name in p.names, name
    assert all(m.get("action") != "resource_update" for m in p.mini_forms)


@pytest.mark.parametrize("make", [_table, _staff])
def test_saving_the_rendered_form_unchanged_keeps_every_value(make):
    r = make()
    before = _snap(r)
    data, _p = form_post(_page(r, tab="buchung"), "resource-form")
    resp, msgs = _post(r, data)
    assert resp.status_code == 302 and resp.url.endswith(f"/ressourcen/{r.pk}/?tab=buchung")
    assert _snap(r) == before
    assert msgs == [("success", msgs[0][1])]


def test_rename_and_change_everything_in_one_save():
    r = _table()
    data, _p = form_post(_page(r), "resource-form")
    data.update({"name": ["Tisch 7"], "zone": ["Garten"], "seats": ["6"], "deposit_eur": ["12,50"]})
    _post(r, data)
    r.refresh_from_db()
    assert (r.name, r.zone, r.seats, r.deposit_cents) == ("Tisch 7", "Garten", 6, 1250)


def test_bad_deposit_saves_nothing_and_returns_to_its_tab():
    r = _table()
    before = _snap(r)
    data, _p = form_post(_page(r), "resource-form")
    data.update({"name": ["Neu"], "deposit_eur": ["abc"], "tab": ["basis"]})
    resp, msgs = _post(r, data)
    assert resp.url.endswith("?tab=buchung") and msgs[0][0] == "error"
    assert _snap(r) == before


def test_empty_name_is_refused():
    r = _table()
    data, _p = form_post(_page(r), "resource-form")
    data["name"] = ["   "]
    _resp, msgs = _post(r, data)
    r.refresh_from_db()
    assert r.name == "Tisch 1" and msgs[0][0] == "error"


def test_combination_conflict_saves_nothing():
    a, b = _table(name="T3"), _table(name="T4")
    combo = _table(name="T3+4")
    combo.parts.set([a, b])
    before = _snap(a)
    data, _p = form_post(_page(a), "resource-form")
    data.update({"capacity": ["3"], "zone": ["Neu"]})
    resp, msgs = _post(a, data)
    assert msgs[0][0] == "error" and resp.url.endswith("?tab=buchung")
    assert _snap(a) == before


def test_staff_without_price_right_sees_deposit_disabled_and_keeps_it():
    r = _staff()
    html = _page(r, role=Membership.ROLE_STAFF)
    assert "data-prices-readonly" in html
    data, _p = form_post(html, "resource-form")
    assert "deposit_eur" not in data
    data["title"] = ["Meisterin"]
    _post(r, data, role=Membership.ROLE_STAFF)
    r.refresh_from_db()
    assert r.deposit_cents == 1000 and r.title == "Meisterin"


def test_mini_forms_carry_their_tab_and_return_there():
    r = _table()
    other = _table(name="T9")
    AvailabilityRule.objects.create(resource=r, weekday=0, start_time=time(9), end_time=time(17))
    _table(name="T2")
    _data, p = form_post(_page(r), "resource-form")
    for mini in p.mini_forms:
        action = mini.get("action")
        if action is None or action == "toggle":
            continue
        assert mini.get("tab") == vr.ACTION_TAB[action], action
    resp, _m = _post(
        r,
        {"action": "rule", "resource": str(r.pk), "weekday": "1", "tab": "zeiten"},
    )
    assert resp.url.endswith(f"/ressourcen/{r.pk}/?tab=zeiten")
    assert other.rules.count() == 0


def test_page_only_edits_its_own_resource():
    r, other = _table(), _table(name="Fremd")
    with pytest.raises(Http404):
        _post(r, {"action": "toggle", "resource": str(other.pk)})
    with pytest.raises(Http404):
        _post(r, {"action": "closed", "resource": str(r.pk)})  # не действие страницы
    other.refresh_from_db()
    assert other.is_active


def test_unknown_resource_is_404():
    with pytest.raises(Http404):
        vr.resource_edit(_req(), pk=uuid.uuid4())


def test_staff_profile_lists_offered_services_read_only():
    r = _staff()
    s = Service.objects.create(name="Haarschnitt", duration_minutes=30)
    s.resources.add(r)
    html = _page(r, tab="profil")
    assert "data-resource-offers" in html and "Haarschnitt" in html
    assert 'name="services"' not in html


def test_template_has_no_inline_script():
    src = (ROOT / "templates/booking/resource_page.html").read_text()
    assert "<script" not in src and not re.search(r"\son[a-z]+=", src)


def test_permissions_match_the_resources_screen():
    from apps.core import view_perms

    assert view_perms.RULES["booking:resource-edit"] == view_perms.RULES["booking:resources"]


# --- ревью D3.1 ---------------------------------------------------------------


@pytest.mark.parametrize(
    "extra", [{"start_time": "abc"}, {"weekday": "9"}, {"weekday": "-1"}, {"end_time": "25:99"}]
)
def test_garbage_hours_rule_is_an_error_not_500(extra):
    r = _table()
    data = {"action": "rule", "resource": str(r.pk), "tab": "zeiten", **extra}
    resp, msgs = _post(r, data)
    assert resp.status_code == 302 and msgs[0][0] == "error"
    assert not r.rules.exists()


def test_invalid_photo_is_an_error_and_saves_nothing():
    from django.core.files.uploadedfile import SimpleUploadedFile

    r = _staff()
    data, _p = form_post(_page(r), "resource-form")
    data["title"] = ["Neu"]
    data["photo"] = SimpleUploadedFile("x.jpg", b"not an image", content_type="image/jpeg")
    resp, msgs = _post(r, data)
    r.refresh_from_db()
    assert r.title == "Stylistin" and msgs[0][0] == "error"
    assert resp.url.endswith("?tab=profil")


def test_legacy_list_form_does_not_let_staff_change_deposit():
    from apps.booking import views

    r = _table(deposit_cents=1500, require_manual_confirm=True)
    req = _req(
        "post",
        {
            "action": "resource_settings",
            "resource": str(r.pk),
            "deposit_eur": "0",
            "counts_party_size": "on",
        },
        role=Membership.ROLE_STAFF,
    )
    views.resources(req)
    r.refresh_from_db()
    assert (r.deposit_cents, r.require_manual_confirm, r.counts_party_size) == (1500, True, True)


def test_page_has_section_headings_and_combo_group_name():
    a, b = _table(name="T3"), _table(name="T4")
    _table(name="T5")
    html = _page(a, tab="tisch")
    assert 'id="res-combo-h"' in html and 'aria-labelledby="res-combo-h"' in html
    assert html.count("<h2") >= 2  # «Öffnungszeiten» и «Kombination aus Tischen»
    assert b.name in html
