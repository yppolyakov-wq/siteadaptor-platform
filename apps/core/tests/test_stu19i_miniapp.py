"""STU-19i: the setup helper in the lite cabinet and the Telegram Mini App.

Locks:
* the helper has its own screen, open in the Mini App whitelist and the lite package;
* a step whose form does not open here (Mini App whitelist / package / rights) has no
  link — an honest note instead of a dead end;
* the lite home links the helper.
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import lite_cabinet, packages, tg_login
from apps.core import setup_assistant as sa
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ALL = [sa.ENTITY_CATEGORY, sa.ENTITY_PRODUCT, sa.ENTITY_SERVICE, sa.ENTITY_PROMO]


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def tenant():
    return TenantFactory(business_type="friseur")


def _req(tenant, data=None):
    request = RequestFactory().get("/dashboard/anlegen/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"i-{o}", email=f"i-{o}@t.de", password="pw12345678"
    )
    request.tenant = tenant
    return request


def test_screen_is_open_in_mini_app_and_lite_package():
    assert "setup-ask" in tg_login.TG_LITE_VIEWS
    assert "setup-ask" in packages._AKTIONEN_VIEWS


def test_screen_renders_plan(tenant, monkeypatch):
    monkeypatch.setattr(sa, "allowed_entities", lambda t, u: ALL)
    body = lite_cabinet.setup_ask(
        _req(tenant, {"frage": "neue Leistung Haarschnitt 25 €"})
    ).content.decode()
    assert "data-setup-ask-page" in body
    assert 'action="/dashboard/anlegen/"' in body
    assert "Haarschnitt" in body


def test_mini_app_hides_links_to_closed_forms(tenant, monkeypatch):
    """In Telegram the services list is closed, a product form is open."""
    monkeypatch.setattr(sa, "allowed_entities", lambda t, u: ALL)
    monkeypatch.setattr(tg_login, "is_tg_session", lambda request: True)
    request = _req(tenant, {"frage": "Leistung Haarschnitt 25 €, Produkt Shampoo 9 €"})
    plan = sa.for_request(sa.plan_from_rules(request.GET["frage"], tenant, ALL), request)
    by = {s.entity: s.reachable for s in plan.steps}
    assert by == {sa.ENTITY_SERVICE: False, sa.ENTITY_PRODUCT: True}
    body = lite_cabinet.setup_ask(request).content.decode()
    assert "data-setup-unreachable" in body
    assert "leistungen/?" not in body  # no dead link
    assert "catalog/products/new/" in body


def test_package_gate_hides_link(tenant, monkeypatch):
    monkeypatch.setattr(packages, "view_allowed", lambda t, name: name != "booking:services")
    request = _req(tenant)
    plan = sa.for_request(sa.plan_from_rules("Leistung Haarschnitt 25 €", tenant, ALL), request)
    assert [s.reachable for s in plan.steps] == [False]


def test_unknown_error_fails_closed(tenant, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(packages, "view_allowed", boom)
    assert sa.reachable(_req(tenant), "catalog:product-create") is False


def test_lite_home_links_helper():
    from pathlib import Path

    from django.conf import settings

    src = (Path(settings.BASE_DIR) / "templates/tenant/lite_home.html").read_text()
    assert "{% url 'setup-ask' %}" in src


def test_reachable_is_true_for_a_plain_owner(tenant):
    assert sa.reachable(_req(tenant), "catalog:product-create") is True
