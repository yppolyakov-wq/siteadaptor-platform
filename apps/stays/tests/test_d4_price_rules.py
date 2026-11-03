"""UX-D D4.2: «Preise & Regeln» — правила цены и продаж номеров в Einstellungen › Zimmer.

Раньше — четыре карточки во вкладке «Einstellungen» списка номеров. Обработчики те же
(`settings_actions`), поэтому поведение прежнее; меняется место и возврат после Save."""

import re
import uuid
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from apps.core.models import Membership
from apps.stays import price_rules_views as v
from apps.stays import settings_actions, views
from apps.stays.models import StaySettings, StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[3]
URL = "/dashboard/stays/preisregeln/"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, role=Membership.ROLE_OWNER, path=URL):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(disabled_modules=[], business_type="hotel")
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": role})
    return req


ACTION_FIELD = {
    "rabatte": ("autodiscount_add", 'name="threshold"'),
    "dynamik": ("occupancy_add", 'name="occupancy"'),
    "luecken": ("gap_deal", 'name="gap_max_nights"'),
    "regeln": ("restriction_add", 'name="max_advance_days"'),
}


@pytest.mark.parametrize("tab", list(ACTION_FIELD))
def test_each_tab_hosts_its_forms(tab):
    action, field = ACTION_FIELD[tab]
    html = v.price_rules(_req(data={"tab": tab})).content.decode()
    assert f'value="{action}"' in html and field in html
    assert f'name="tab" value="{tab}"' in html
    assert re.search(rf'href="\?tab={tab}"[^>]*aria-current="page"', html)


def test_junk_tab_falls_back_to_first():
    html = v.price_rules(_req(data={"tab": "<x>"})).content.decode()
    assert re.search(r'href="\?tab=rabatte"[^>]*aria-current="page"', html)


@pytest.mark.parametrize(
    "data, tab",
    [
        (
            {"action": "autodiscount_add", "kind": "los", "threshold": "7", "percent": "10"},
            "rabatte",
        ),
        ({"action": "occupancy_add", "occupancy": "80", "percent": "10"}, "dynamik"),
        ({"action": "gap_deal", "enabled": "1", "gap_max_nights": "3"}, "luecken"),
        ({"action": "booking_window", "max_advance_days": "200"}, "regeln"),
    ],
)
def test_post_saves_and_returns_to_its_tab(data, tab):
    resp = v.price_rules(_req("post", data))
    assert resp.status_code == 302 and resp.url == f"{URL}?tab={tab}"
    s = StaySettings.load()
    assert s.auto_discount_rules or s.occupancy_rules or s.gap_max_nights or s.max_advance_days


def test_foreign_action_is_rejected():
    assert v.price_rules(_req("post", {"action": "kurtaxe", "kurtaxe_eur": "9"})).status_code == 400
    assert StaySettings.load().kurtaxe_cents == 0


def test_staff_sees_rules_without_forms_and_cannot_write():
    s = StaySettings.load()
    s.gap_max_nights = 3
    s.save(update_fields=["gap_max_nights"])
    html = v.price_rules(_req(data={"tab": "luecken"}, role=Membership.ROLE_STAFF)).content.decode()
    assert "data-gap-state" in html and 'value="gap_deal"' not in html
    regeln = v.price_rules(_req(data={"tab": "regeln"}, role=Membership.ROLE_STAFF))
    assert "data-window-state" in regeln.content.decode()
    v.price_rules(_req("post", {"action": "gap_deal"}, role=Membership.ROLE_STAFF))
    assert StaySettings.load().gap_max_nights == 3


def test_saving_gap_form_unchanged_keeps_settings():
    """W0: форма Lücken-Deal — одно действие, пишет оба поля; отрисованная форма без
    правок не меняет настройки."""
    s = StaySettings.load()
    s.gap_max_nights, s.gap_discount_percent = 4, 30
    s.save(update_fields=["gap_max_nights", "gap_discount_percent"])
    v.price_rules(
        _req(
            "post",
            {
                "action": "gap_deal",
                "enabled": "1",
                "gap_max_nights": "4",
                "gap_discount_percent": "30",
            },
        )
    )
    s = StaySettings.load()
    assert (s.gap_max_nights, s.gap_discount_percent) == (4, 30)


def test_restriction_rule_lists_unit_name():
    unit = StayUnit.objects.create(name="Seeblick", price_cents=9000)
    s = StaySettings.load()
    s.restriction_rules = [{"unit": str(unit.pk), "min_nights": 3}]
    s.save(update_fields=["restriction_rules"])
    html = v.price_rules(_req(data={"tab": "regeln"})).content.decode()
    assert "Seeblick" in html


def test_units_list_no_longer_hosts_rule_forms():
    text = (ROOT / "templates/stays/units.html").read_text()
    for action in (
        "autodiscount_add",
        "occupancy_add",
        "gap_deal",
        "restriction_add",
        "booking_window",
    ):
        assert f'value="{action}"' not in text, action
    assert "stays:price-rules" in text


def test_legacy_post_to_units_lands_on_new_screen():
    resp = views.units(
        _req(
            "post",
            {"action": "occupancy_add", "occupancy": "80", "percent": "5"},
            path="/dashboard/stays/units/",
        )
    )
    assert resp.url == f"{URL}?tab=dynamik"


def test_old_regeln_bookmark_redirects():
    resp = views.units(
        _req(data={"tab": "einstellungen", "sec": "regeln"}, path="/dashboard/stays/units/")
    )
    assert resp.status_code == 302 and resp.url == f"{URL}?tab=regeln"


def test_home_points_every_rule_action_to_its_tab():
    for action, tab in v.ACTION_TAB.items():
        assert settings_actions.home_url(action) == f"{URL}?tab={tab}"


def test_screen_is_in_settings_zimmer_group_and_permissions():
    from apps.core import nav_registry, view_perms

    entry = next(e for e in nav_registry.ENTRIES if e.url_name == "stays:price-rules")
    assert entry.hub == "settings" and entry.group == "zimmer" and entry.module_key == "stays"
    rule = view_perms.RULES["stays:price-rules"]
    assert (rule.read, rule.write) == ("einstellungen.view", "einstellungen.edit")


def test_template_has_no_scripts():
    text = (ROOT / "templates/stays/price_rules.html").read_text()
    assert "<script" not in text and not re.search(r"\son[a-z]+=", text)
    assert reverse("stays:price-rules") == URL
