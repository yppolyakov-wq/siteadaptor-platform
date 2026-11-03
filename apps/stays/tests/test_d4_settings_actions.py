"""UX-D D4.0: настроечные действия кабинета номеров — один модуль (`settings_actions`).

Рефактор без изменения поведения: обработчики перенесены из `views.units()` 1:1,
`units()` принимает их по-прежнему (старые формы и открытые вкладки браузера)."""

import inspect
import pathlib
import re
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core.models import Membership
from apps.stays import settings_actions, views
from apps.stays.models import RatePlan, StaySettings
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _post(data, role=Membership.ROLE_OWNER):
    req = RequestFactory().post("/dashboard/stays/units/", data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(disabled_modules=[])
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": role})
    resp = views.units(req)
    return resp, [str(m) for m in get_messages(req)]


def test_every_action_has_handler_and_home():
    assert set(settings_actions.HANDLERS) == set(settings_actions.HOME)
    assert settings_actions.ACTIONS == frozenset(settings_actions.HANDLERS)
    assert len(settings_actions.ACTIONS) == 15


def test_settings_actions_live_in_one_place():
    """units() больше не держит своих веток этих действий — один источник поведения."""
    src = pathlib.Path(views.__file__).read_text()
    body = src[src.index("def units(") :]
    body = body[: body.index("        if pk:\n")]
    own = set(re.findall(r'(?:el)?if action == "([a-z_]+)"', body))
    assert not own & settings_actions.ACTIONS


def test_price_writing_settings_actions_require_price_permission():
    pattern = r"RatePlan|StaySettings"
    writers = {
        a for a, h in settings_actions.HANDLERS.items() if re.search(pattern, inspect.getsource(h))
    }
    assert writers == settings_actions.ACTIONS - {"card_amenities"}
    assert writers <= views.RATE_EDIT_ACTIONS


def test_legacy_post_to_units_still_saves_and_returns_to_its_section():
    resp, msgs = _post(
        {"action": "kurtaxe", "kurtaxe_eur": "2,50", "kurtaxe_label": "Kurtaxe", "house_rules": "x"}
    )
    s = StaySettings.load()
    assert s.kurtaxe_cents == 250 and s.house_rules == "x"
    assert resp.status_code == 302
    assert resp.url == "/dashboard/stays/units/?tab=einstellungen&sec=kurtaxe"
    assert msgs == ["Einstellungen gespeichert."]


@pytest.mark.parametrize(
    "action, sec",
    [("gap_deal", "preise"), ("booking_window", "regeln"), ("kurtaxe", "kurtaxe")],
)
def test_home_urls_keep_previous_sections(action, sec):
    """Пока экран не переехал (D4.2/D4.3) — прежняя под-вкладка; тарифы — D4.1."""
    assert settings_actions.home_url(action).endswith(f"?tab=einstellungen&sec={sec}")
    assert settings_actions.home_url("rateplan") == "/dashboard/stays/tarife/"


def test_staff_cannot_create_rate_plan_through_units():
    resp, msgs = _post({"action": "rateplan", "name": "Frühstück"}, role=Membership.ROLE_STAFF)
    assert not RatePlan.objects.exists()
    assert any("Inhaber" in m for m in msgs)


def test_next_still_wins_over_home():
    resp, _ = _post({"action": "gap_deal", "enabled": "1", "next": "/dashboard/stays/"})
    assert resp.url == "/dashboard/stays/"
    resp, _ = _post({"action": "gap_deal", "next": "//evil.example/x"})
    assert "evil" not in resp.url


def test_overflowing_amount_is_zero_not_500():
    """«1e999» в поле суммы раньше ронял страницу OverflowError."""
    resp, _ = _post({"action": "kurtaxe", "kurtaxe_eur": "1e999"})
    assert resp.status_code == 302 and StaySettings.load().kurtaxe_cents == 0
