"""UX-D D3.0: действия экрана ресурсов — отдельный модуль 1:1 + хотфикс предоплаты.

Предоплата ресурса рисовалась `{% widthratio %}` — округлением до евро: 5,50 € в поле
показывались «6», и любое сохранение мест/зоны записывало 6,00 €. Мусор в поле молча
обнулял предоплату."""

import re
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


def _settings_form(html, pk):
    """Поля формы resource_settings ресурса pk — как их отправит браузер."""
    m = re.search(
        r'<form[^>]*>(?:(?!</form>).)*?value="resource_settings">'
        r'<input type="hidden" name="resource" value="' + str(pk) + r'">(.*?)</form>',
        html,
        re.S,
    )
    assert m, "форма resource_settings не найдена"
    body = m.group(1)
    data = {"action": "resource_settings", "resource": str(pk)}
    for tag in re.findall(r"<input[^>]*>", body):
        name = re.search(r'name="([^"]+)"', tag)
        if not name:
            continue
        kind = re.search(r'type="([^"]+)"', tag)
        kind = kind.group(1) if kind else "text"
        if kind == "checkbox" and "checked" not in tag:
            continue
        value = re.search(r'value="([^"]*)"', tag)
        data[name.group(1)] = value.group(1) if value else "on"
    return data


def test_every_action_has_exactly_one_tab():
    assert set(views_resources.ACTION_TAB) == set(views_resources.HANDLERS)
    assert set(views_resources.ACTION_TAB.values()) <= set(views_resources.RESOURCE_TABS) | {None}


def test_deposit_with_cents_survives_saving_seats_unchanged():
    r = _table(deposit_cents=550)
    html = views.resources(_req(data={"open": str(r.pk)})).content.decode()
    data = _settings_form(html, r.pk)
    assert data.get("deposit_eur") not in ("6", "5")  # не округлено до евро
    _post(data)
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


def test_legacy_actions_still_redirect_to_the_open_card():
    r = _table()
    resp, _m = _post({"action": "toggle", "resource": str(r.pk)})
    assert resp.status_code == 302 and resp.url.endswith(f"?open={r.pk}#res-{r.pk}")


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
