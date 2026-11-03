"""UX-D D2.2: «＋ Leistung» — шторкой (фрагмент существующей страницы создания)."""

import json
import re
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.booking import views
from apps.booking.models import Service
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, drawer=True, path="/dashboard/booking/leistungen/neu/"):
    extra = {"HTTP_X_SF_DRAWER": "1"} if drawer else {}
    req = getattr(RequestFactory(), method)(path, data or {}, **extra)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(disabled_modules=[])
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": Membership.ROLE_OWNER})
    return req


def test_fragment_is_marked_and_has_no_scripts():
    resp = views.service_new(_req())
    html = resp.content.decode()
    assert resp["X-Sf-Fragment"] == "1" and "no-store" in resp["Cache-Control"]
    assert "<html" not in html and "<script" not in html
    assert not re.search(r"\son[a-z]+=", html)
    assert "data-drawer-title=" in html and "data-drawer-form" in html


def test_prefill_from_setup_helper_link():
    html = views.service_new(
        _req(data={"name": "Haarschnitt", "price_eur": "25,00", "duration": "45"})
    ).content.decode()
    assert 'value="Haarschnitt"' in html and 'value="25,00"' in html and 'value="45"' in html


def test_foreign_next_is_ignored():
    html = views.service_new(_req(data={"next": "//evil.example/x"})).content.decode()
    assert "evil.example" not in html


def test_create_in_drawer_navigates_to_the_new_service_page():
    resp = views.service_new(
        _req(
            "post",
            {
                "name": "Bartpflege",
                "duration": "20",
                "price_eur": "18,00",
                "next": "/dashboard/booking/leistungen/",
            },
        )
    )
    data = json.loads(resp.content)
    svc = Service.objects.get(name="Bartpflege")
    assert svc.duration_minutes == 20 and svc.price_cents == 1800
    assert data["ok"] is True and data["navigate"] is True
    assert data["location"].startswith(f"/dashboard/booking/leistungen/{svc.pk}/")


def test_create_without_js_redirects_to_the_service_page():
    resp = views.service_new(_req("post", {"name": "Bartpflege"}, drawer=False))
    svc = Service.objects.get(name="Bartpflege")
    assert resp.status_code == 302 and resp.url.startswith(
        f"/dashboard/booking/leistungen/{svc.pk}/"
    )


def test_empty_name_keeps_input_and_marks_the_field():
    resp = views.service_new(
        _req("post", {"name": "  ", "price_eur": "33,00", "duration": "50", "next": "/x/"})
    )
    html = resp.content.decode()
    assert resp.status_code == 200 and resp["X-Sf-Fragment"] == "1"
    assert json.loads(resp["X-Sf-Messages"])[0]["level"] == "error"
    assert 'aria-invalid="true"' in html
    assert 'value="33,00"' in html and 'value="50"' in html
    assert not Service.objects.exists()


def test_old_neu_link_redirects_to_the_new_form():
    resp = views.services_view(
        _req(
            data={"neu": "1", "name": "Haarschnitt"},
            drawer=False,
            path="/dashboard/booking/leistungen/",
        )
    )
    assert resp.status_code == 302
    assert (
        resp.url.startswith("/dashboard/booking/leistungen/neu/") and "name=Haarschnitt" in resp.url
    )


def test_entry_points_open_the_new_form():
    from apps.core import sellable_manage
    from apps.core import setup_assistant as sa

    assert sa.ENTITIES[sa.ENTITY_SERVICE]["url_name"] == "booking:service-new"
    spec = sellable_manage._MANAGE["service"]
    assert spec["add"][0] == "booking:service-new"


def test_service_new_drawer_aware_is_innermost():
    from apps.core import drawer

    code = drawer.drawer_aware(lambda r: r).__code__
    chain = [views.service_new]
    while hasattr(chain[-1], "__wrapped__"):
        chain.append(chain[-1].__wrapped__)
    assert chain[-2].__code__ is code


def test_permissions_match_the_services_list():
    from apps.core import view_perms

    assert view_perms.RULES["booking:service-new"] == view_perms.RULES["booking:services"]
