"""UX-D D3.0: действия экрана ресурсов — отдельный модуль 1:1 + хотфикс предоплаты.

Предоплата ресурса рисовалась `{% widthratio %}` — округлением до евро: 5,50 € в поле
показывались «6», и любое сохранение мест/зоны записывало 6,00 €. Мусор в поле молча
обнулял предоплату."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.booking import views, views_resources
from apps.booking.models import AvailabilityRule, Resource
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None):
    req = getattr(RequestFactory(), method)("/dashboard/booking/ressourcen/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(business_type="restaurant", disabled_modules=[])
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": Membership.ROLE_OWNER})
    return req


def _table(**kw):
    defaults = {"name": "Tisch 1", "type": Resource.TYPE_TABLE, "capacity": 1, "seats": 4}
    defaults.update(kw)
    return Resource.objects.create(**defaults)


def _post(data):
    req = _req("post", data)
    resp = views.resources(req)
    return resp, [(m.level_tag, str(m)) for m in get_messages(req)]


def test_every_action_has_exactly_one_tab():
    assert set(views_resources.ACTION_TAB) == set(views_resources.HANDLERS)
    assert set(views_resources.ACTION_TAB.values()) <= set(views_resources.RESOURCE_TABS) | {None}


def test_deposit_with_cents_survives_saving_seats_unchanged():
    """D3.0: поле предоплаты — в формате денег (было «6» вместо 5,50 €). Форма — со
    страницы ресурса (D3.1/D3.2: список стал строками)."""
    from apps.booking import views_resources as vr
    from apps.core.tests.form_post import form_post

    r = _table(deposit_cents=550)
    html = vr.resource_edit(_req(), pk=r.pk).content.decode()
    data, _p = form_post(html, "resource-form")
    assert data["deposit_eur"][0] not in ("6", "5")  # не округлено до евро
    req = _req("post", data)
    vr.resource_edit(req, pk=r.pk)
    r.refresh_from_db()
    assert r.deposit_cents == 550


@pytest.mark.parametrize("raw", ["abc", "5,5,5", "-3", "999999999"])
def test_garbage_deposit_keeps_old_value_and_says_so(raw):
    r = _table(deposit_cents=1200)
    _resp, msgs = _post({"action": "resource_settings", "resource": str(r.pk), "deposit_eur": raw})
    r.refresh_from_db()
    assert r.deposit_cents == 1200
    assert any(level == "error" for level, _t in msgs)


def test_german_deposit_is_parsed():
    r = _table()
    _post({"action": "resource_settings", "resource": str(r.pk), "deposit_eur": "12,50"})
    r.refresh_from_db()
    assert r.deposit_cents == 1250


def test_create_with_garbage_deposit_is_refused():
    _resp, msgs = _post({"action": "resource", "name": "Tisch 9", "deposit_eur": "x"})
    assert not Resource.objects.filter(name="Tisch 9").exists()
    assert any(level == "error" for level, _t in msgs)


def test_rule_delete_cannot_remove_a_rule_by_bare_pk_of_another_resource():
    """Удаление правила требует ресурс правила (раньше — любой pk)."""
    from datetime import time

    a, b = _table(name="A"), _table(name="B")
    rule = AvailabilityRule.objects.create(
        resource=b, weekday=0, start_time=time(9), end_time=time(17)
    )
    _post({"action": "rule_delete", "rule": str(rule.pk), "resource": str(a.pk)})
    assert AvailabilityRule.objects.filter(pk=rule.pk).exists()
    _post({"action": "rule_delete", "rule": str(rule.pk), "resource": str(b.pk)})
    assert not AvailabilityRule.objects.filter(pk=rule.pk).exists()


def test_legacy_actions_redirect_to_the_resource_page():
    """UX-D D3.2: старые формы (вкладки браузера) ведут на страницу ресурса."""
    r = _table()
    resp, _m = _post({"action": "toggle", "resource": str(r.pk)})
    assert resp.status_code == 302 and resp.url.endswith(f"/ressourcen/{r.pk}/")


def test_garbage_deposit_does_not_discard_other_changes():
    r = _table(deposit_cents=1200, zone="Innen")
    _resp, msgs = _post(
        {
            "action": "resource_settings",
            "resource": str(r.pk),
            "deposit_eur": "abc",
            "seats_present": "1",
            "capacity": "1",
            "seats": "6",
            "zone": "Terrasse",
        }
    )
    r.refresh_from_db()
    assert (r.deposit_cents, r.seats, r.zone) == (1200, 6, "Terrasse")
    assert [lvl for lvl, _t in msgs] == ["error", "info"]
