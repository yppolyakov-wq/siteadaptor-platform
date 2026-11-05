"""AIS-M M-1c: экран «Richtungen & Funktionen» — блоки, точечные POST, права, гейты."""

import re
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import diagnoses, directions_screen, modules, packages
from apps.core.views import modules_view
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(tenant, method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/modules/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(username=f"m-{o}", password="pw12345678")
    request.tenant = tenant
    return request


def _html(tenant):
    return modules_view(_req(tenant)).content.decode()


def test_core_and_base_on_are_not_toggles():
    html = _html(TenantFactory(business_type="bakery", disabled_modules=[]))
    for key in ("catalog", "dashboard", "settings", "crm", "reviews", "inbox", "promotions"):
        assert f'data-module="{key}"' not in html, key


def test_base_disabled_shows_switch_back():
    html = _html(TenantFactory(business_type="bakery", disabled_modules=["crm"]))
    assert "data-directions-base-off" in html and 'data-module="crm"' in html


def test_addon_without_direction_hidden_when_off():
    preset = [m for m in modules.default_disabled_for("hotel") if m != "loyalty"]
    t = TenantFactory(business_type="hotel", disabled_modules=[*preset, "loyalty"])
    ctx = directions_screen.context(t)
    assert "loyalty" not in {r["key"] for r in ctx["addons"]}
    t2 = TenantFactory(business_type="hotel", disabled_modules=preset)  # включён — виден
    assert "loyalty" in {r["key"] for r in directions_screen.context(t2)["addons"]}


def test_every_module_a_diagnosis_can_name_has_a_control():
    """Диагноз «X ist ausgeschaltet» ведёт сюда — у выключенного модуля обязан быть контрол."""
    for spec in modules.REGISTRY:
        if spec.core:
            continue
        t = TenantFactory(business_type="bakery", disabled_modules=[spec.key])
        html = _html(t)
        has = f'data-module="{spec.key}"' in html or any(
            f'data-direction="{d}"' in html
            for d in ("termine", "tisch", "zimmer", "tickets", "anfragen", "waren")
        )
        assert has, spec.key
    assert diagnoses  # реестр диагнозов ссылается на экран «modules»


def test_post_module_changes_only_that_key():
    t = TenantFactory(business_type="bakery", disabled_modules=["finance"])
    resp = modules_view(_req(t, "post", {"action": "module", "key": "loyalty", "on": "0"}))
    assert resp.status_code == 302
    assert sorted(Tenant.objects.get(pk=t.pk).disabled_modules) == ["finance", "loyalty"]


def test_post_direction_on():
    t = TenantFactory(business_type="bakery", disabled_modules=["events"])
    modules_view(_req(t, "post", {"action": "direction", "key": "tickets", "on": "1"}))
    assert "events" not in Tenant.objects.get(pk=t.pk).disabled_modules


@pytest.mark.parametrize(
    "data",
    [
        {"action": "module", "key": "nope", "on": "1"},
        {"action": "module", "key": "catalog", "on": "0"},
        {"action": "direction", "key": "nope", "on": "1"},
        {"action": "x", "key": "loyalty", "on": "1"},
        {"action": "module", "key": "loyalty", "on": "yes"},
    ],
)
def test_garbage_post_is_400_without_write(data):
    t = TenantFactory(business_type="bakery", disabled_modules=["finance"])
    assert modules_view(_req(t, "post", data)).status_code == 400
    assert Tenant.objects.get(pk=t.pk).disabled_modules == ["finance"]


def test_forged_post_outside_package_keeps_db(monkeypatch):
    t = TenantFactory(business_type="bakery", disabled_modules=["gift"])
    monkeypatch.setattr(packages, "module_allowed", lambda tenant, key: key != "gift")
    modules_view(_req(t, "post", {"action": "module", "key": "gift", "on": "1"}))
    assert Tenant.objects.get(pk=t.pk).disabled_modules == ["gift"]
    assert "Nicht im Paket" in _html(Tenant.objects.get(pk=t.pk))


def test_every_form_sends_one_key():
    html = _html(TenantFactory(business_type="werkstatt", disabled_modules=["crm"]))
    forms = [
        f
        for f in re.findall(
            r"<form method=\"post\">.*?</form>|<form method=\"post\" class=\"mt-[a-z0-9]+\">.*?</form>",
            html,
            re.S,
        )
    ]
    assert forms
    for form in forms:
        assert form.count('name="key"') == 1
        assert "csrfmiddlewaretoken" in form


def test_orders_reachable_without_waren():
    """Ревью M-1c HIGH: салон без товаров с выключенным orders — контрол есть."""
    preset = list(modules.default_disabled_for("friseur"))
    t = TenantFactory(business_type="friseur", disabled_modules=sorted({*preset, "orders"}))
    assert 'data-direction="waren"' in _html(t)


def test_disabled_addon_without_direction_still_has_control():
    preset = list(modules.default_disabled_for("hotel"))
    t = TenantFactory(business_type="hotel", disabled_modules=sorted({*preset, "loyalty"}))
    assert 'data-module="loyalty"' in _html(t)


def test_module_action_cannot_switch_direction_modules():
    t = TenantFactory(business_type="friseur", disabled_modules=[])
    resp = modules_view(_req(t, "post", {"action": "module", "key": "booking", "on": "0"}))
    assert resp.status_code == 400
    assert "booking" not in Tenant.objects.get(pk=t.pk).disabled_modules


def test_noop_direction_is_not_reported_as_saved():
    t = TenantFactory(business_type="cafe", disabled_modules=[])
    problems = directions_screen.apply(t, "direction", "speisekarte", True)
    assert problems == {}  # уже активна — ок
    problems = directions_screen.apply(t, "direction", "speisekarte", False)
    assert problems  # не выключается — честная причина, не «Gespeichert»
