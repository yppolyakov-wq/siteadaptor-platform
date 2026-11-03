"""UX-D D3.2: «＋ Neue Ressource» шторкой и список ресурсов строками.

Раньше справа от списка постоянно висела форма нового ресурса (с предоплатой, ручной
проверкой и переводами), а каждый ресурс был свёрнутой карточкой с семью формами."""

import json
import re
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

from apps.booking import views
from apps.booking import views_resources as vr
from apps.booking.models import Resource
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
NEW = "/dashboard/booking/ressourcen/neu/"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, drawer=True, path=NEW):
    extra = {"HTTP_X_SF_DRAWER": "1"} if drawer else {}
    req = getattr(RequestFactory(), method)(path, data or {}, **extra)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(business_type="restaurant", disabled_modules=[])
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": Membership.ROLE_OWNER})
    return req


def test_fragment_is_marked_and_has_no_scripts():
    resp = vr.resource_new(_req())
    html = resp.content.decode()
    assert resp["X-Sf-Fragment"] == "1" and "no-store" in resp["Cache-Control"]
    assert "<html" not in html and "<script" not in html
    assert not re.search(r"\son[a-z]+=", html)
    assert "data-drawer-title=" in html and "data-drawer-form" in html


def test_type_prefill_from_tischplan():
    html = vr.resource_new(_req(data={"type": "table"})).content.decode()
    assert re.search(r'<option value="table" selected', html)
    html = vr.resource_new(_req(data={"type": "<x>"})).content.decode()
    assert "&lt;x&gt;" not in html


@pytest.mark.parametrize("business, default", [("restaurant", "table"), ("friseur", "staff")])
def test_default_type_follows_the_business(business, default):
    req = _req()
    req.tenant = TenantFactory.build(business_type=business, disabled_modules=[])
    html = vr.resource_new(req).content.decode()
    assert re.search(rf'<option value="{default}" selected', html)


def test_create_in_drawer_navigates_to_the_resource_page():
    resp = vr.resource_new(
        _req(
            "post",
            {"name": "Tisch 12", "type": "table", "seats": "6", "zone": "Garten", "next": "/x/"},
        )
    )
    data = json.loads(resp.content)
    r = Resource.objects.get(name="Tisch 12")
    assert (r.seats, r.zone, r.capacity) == (6, "Garten", 1)
    assert data["ok"] is True and data["navigate"] is True
    assert data["location"].startswith(f"/dashboard/booking/ressourcen/{r.pk}/")


def test_staff_opens_on_profile_tab_and_ignores_table_fields():
    resp = vr.resource_new(
        _req("post", {"name": "Anna", "type": "staff", "seats": "6"}, drawer=False)
    )
    r = Resource.objects.get(name="Anna")
    assert r.seats is None and resp.url.endswith("?tab=profil")


@pytest.mark.parametrize(
    "data, field",
    [
        ({"name": "  "}, "name"),
        ({"name": "A", "capacity": "abc"}, "capacity"),
        ({"name": "A", "capacity": "0"}, "capacity"),
        ({"name": "A", "type": "table", "seats": "200"}, "seats"),
    ],
)
def test_errors_are_shown_at_the_field_and_input_kept(data, field):
    resp = vr.resource_new(_req("post", {**data, "zone": "Terrasse"}))
    html = resp.content.decode()
    assert resp.status_code == 200 and resp["X-Sf-Fragment"] == "1"
    assert json.loads(resp["X-Sf-Messages"])[0]["level"] == "error"
    assert 'aria-invalid="true"' in html and 'value="Terrasse"' in html
    assert not Resource.objects.exists()
    marker = {"name": "name", "capacity": "cap", "seats": "seats"}[field]
    assert f'id="res-new-{marker}-err"' in html


def test_foreign_next_is_ignored():
    html = vr.resource_new(_req(data={"next": "//evil.example/x"})).content.decode()
    assert "evil.example" not in html


def test_drawer_aware_is_innermost():
    from apps.core import drawer

    code = drawer.drawer_aware(lambda r: r).__code__
    chain = [vr.resource_new]
    while hasattr(chain[-1], "__wrapped__"):
        chain.append(chain[-1].__wrapped__)
    assert chain[-2].__code__ is code


def test_permissions_match_the_resources_screen():
    from apps.core import view_perms

    assert view_perms.RULES["booking:resource-new"] == view_perms.RULES["booking:resources"]


# --- список -------------------------------------------------------------------


def test_list_rows_have_no_inputs_and_one_link_each():
    a = Resource.objects.create(name="Tisch 1", type=Resource.TYPE_TABLE, seats=4)
    Resource.objects.create(name="Anna", type=Resource.TYPE_STAFF, title="Stylistin")
    html = views.resources(_req(drawer=False, path="/dashboard/booking/ressourcen/")).content
    html = html.decode()
    rows = re.findall(r"<a [^>]*data-resource-row>.*?</a>", html, re.S)
    assert len(rows) == 2
    for row in rows:
        assert "<input" not in row and "<form" not in row and "<select" not in row
    assert f"/dashboard/booking/ressourcen/{a.pk}/" in html
    assert html.count("data-resource-group") == 2  # два типа — две группы
    assert 'href="/dashboard/booking/ressourcen/neu/"' in html and "data-drawer" in html


def test_list_query_budget_does_not_grow_with_resources():
    def run():
        req = _req(drawer=False, path="/dashboard/booking/ressourcen/")
        with CaptureQueriesContext(connection) as ctx:
            views.resources(req)
        return len(ctx.captured_queries)

    for i in range(2):
        Resource.objects.create(name=f"T{i}", type=Resource.TYPE_TABLE)
    few = run()
    for i in range(8):
        Resource.objects.create(name=f"U{i}", type=Resource.TYPE_TABLE)
    assert run() <= few


def test_garbage_open_param_shows_the_list():
    resp = views.resources(
        _req(data={"open": "nope"}, drawer=False, path="/dashboard/booking/ressourcen/")
    )
    assert resp.status_code == 200
