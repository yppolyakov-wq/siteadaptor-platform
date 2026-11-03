"""UX-D D4.5: список номеров — строки без форм; «＋ Neues Zimmer» шторкой; старые адреса.

Раньше над списком стояла раскрытая форма нового номера со всеми полями, а рядом —
вкладка «Einstellungen» (настройки переехали в D4.1–D4.4)."""

import json
import re
import uuid
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core.models import Membership
from apps.stays import unit_new_views as v
from apps.stays import views
from apps.stays.models import StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[3]
NEW = "/dashboard/stays/units/neu/"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, role=Membership.ROLE_OWNER, drawer=False, path=NEW):
    extra = {"HTTP_X_SF_DRAWER": "1"} if drawer else {}
    req = getattr(RequestFactory(), method)(path, data or {}, **extra)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(disabled_modules=[], business_type="hotel")
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": role})
    return req


def test_list_rows_have_no_form_fields_and_no_open_create_form():
    StayUnit.objects.create(name="Doppelzimmer", price_cents=9000)
    html = views.units(_req(path="/dashboard/stays/units/")).content.decode()
    lst = html[html.index("data-units-list") :]
    lst = lst[: lst.index("data-units-settings-links")]
    assert not re.search(r'<(input|select|textarea)(?![^>]*type="hidden")', lst)
    assert 'value="unit"' not in html and 'id="neu"' not in html
    assert 'href="/dashboard/stays/units/neu/" data-drawer' in html
    for link in (
        "data-rate-plans-link",
        "data-price-rules-link",
        "data-stay-settings-link",
        "data-channels-link",
    ):
        assert link in html, link


def test_staff_without_price_rights_sees_no_create_button():
    html = views.units(
        _req(path="/dashboard/stays/units/", role=Membership.ROLE_STAFF)
    ).content.decode()
    assert "/dashboard/stays/units/neu/" not in html


def test_drawer_fragment_and_create_navigates_to_room_page():
    resp = v.unit_new(_req(drawer=True))
    html = resp.content.decode()
    assert resp["X-Sf-Fragment"] == "1" and "<script" not in html
    assert not re.search(r"\son[a-z]+=", html)
    resp = v.unit_new(
        _req(
            "post",
            {
                "name": "Suite Alpenblick",
                "price_eur": "129,50",
                "quantity": "2",
                "max_guests": "3",
                "next": "/dashboard/stays/units/",
            },
            drawer=True,
        )
    )
    unit = StayUnit.objects.get(name="Suite Alpenblick")
    assert (unit.price_cents, unit.quantity, unit.max_guests) == (12950, 2, 3)
    data = json.loads(resp.content)
    assert data["navigate"] and data["location"].startswith(f"/dashboard/stays/units/{unit.pk}/")


@pytest.mark.parametrize(
    "field, value",
    [
        ("name", "  "),
        ("price_eur", "abc"),
        ("price_eur", "1e999"),
        ("quantity", "0"),
        ("max_guests", "x"),
        ("deposit_eur", "-5"),
    ],
)
def test_bad_input_keeps_values_and_marks_field(field, value):
    data = {"name": "Zimmer A", "price_eur": "80", field: value}
    resp = v.unit_new(_req("post", data, drawer=True))
    html = resp.content.decode()
    assert resp["X-Sf-Fragment"] == "1" and 'aria-invalid="true"' in html
    assert not StayUnit.objects.exists()


def test_without_js_redirects_to_room_page():
    resp = v.unit_new(_req("post", {"name": "Einzel", "price_eur": "60"}))
    unit = StayUnit.objects.get(name="Einzel")
    assert resp.status_code == 302 and resp.url == f"/dashboard/stays/units/{unit.pk}/"


def test_long_name_clamped_and_bad_type_defaults():
    v.unit_new(_req("post", {"name": "x" * 200, "price_eur": "60", "type": "palace"}))
    unit = StayUnit.objects.get()
    assert len(unit.name) == 120 and unit.type == StayUnit.TYPE_ROOM


def test_old_neu_link_redirects_with_prefill():
    resp = views.units(_req(data={"neu": "1", "name": "Suite"}, path="/dashboard/stays/units/"))
    assert resp.status_code == 302 and resp.url.startswith(NEW) and "name=Suite" in resp.url


def test_old_settings_tab_redirects():
    resp = views.units(_req(data={"tab": "einstellungen"}, path="/dashboard/stays/units/"))
    assert resp.status_code == 302 and resp.url == "/dashboard/stays/preisregeln/"


def test_prefill_from_setup_helper():
    html = v.unit_new(_req(data={"name": "Suite", "price_eur": "99"}, drawer=True)).content.decode()
    assert 'value="Suite"' in html and 'value="99"' in html


def test_entry_points_open_the_new_form():
    from apps.core import sellable_manage
    from apps.core import setup_assistant as sa

    assert sa.ENTITIES[sa.ENTITY_ROOM]["url_name"] == "stays:unit-new"
    assert sa.ENTITIES[sa.ENTITY_ROOM]["perm"] == "preise.edit"
    assert sellable_manage._MANAGE["stay"]["add"][0] == "stays:unit-new"


def test_permissions_write_needs_price_rights():
    from apps.core import view_perms

    rule = view_perms.RULES["stays:unit-new"]
    assert (rule.read, rule.write) == ("sortiment.view", "preise.edit")


def test_drawer_aware_is_innermost():
    from apps.core import drawer

    code = drawer.drawer_aware(lambda r: r).__code__
    chain = [v.unit_new]
    while hasattr(chain[-1], "__wrapped__"):
        chain.append(chain[-1].__wrapped__)
    assert chain[-2].__code__ is code


def test_no_template_points_to_the_old_settings_tab():
    for path in (ROOT / "templates").rglob("*.html"):
        text = path.read_text()
        assert "tab=einstellungen" not in text and "?neu=1" not in text, path
