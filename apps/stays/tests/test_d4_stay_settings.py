"""UX-D D4.3: «Unterkunft» — Kurtaxe, Hausordnung, часы заезда/выезда и удобства на
карточке номера в Einstellungen › Zimmer (раньше — под-вкладка списка номеров)."""

import re
import uuid
from html.parser import HTMLParser
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core.models import Membership
from apps.stays import settings_actions, views
from apps.stays import stay_settings_views as v
from apps.stays.models import StaySettings
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[3]
URL = "/dashboard/stays/unterkunft/"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, role=Membership.ROLE_OWNER, path=URL, tenant=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant or TenantFactory.build(disabled_modules=[], business_type="hotel")
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": role})
    return req


class _Form(HTMLParser):
    """Поля формы с hidden action=<action>, как их отправит браузер."""

    def __init__(self, action):
        super().__init__()
        self.action, self.forms, self.cur, self._ta, self._sel = action, [], None, None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.cur = {}
            return
        if self.cur is None:
            return
        name = a.get("name")
        if tag == "input" and name:
            if a.get("type") in ("checkbox", "radio") and "checked" not in a:
                return
            self.cur.setdefault(name, []).append(a.get("value", ""))
        elif tag == "textarea" and name:
            self._ta = [name, ""]
        elif tag == "select" and name:
            self._sel = [name, None]
        elif tag == "option" and self._sel is not None and "selected" in a:
            self._sel[1] = a.get("value", "")

    def handle_data(self, d):
        if self._ta:
            self._ta[1] += d

    def handle_endtag(self, tag):
        if tag == "form" and self.cur is not None:
            self.forms.append(self.cur)
            self.cur = None
        elif tag == "textarea" and self._ta and self.cur is not None:
            self.cur.setdefault(self._ta[0], []).append(self._ta[1])
            self._ta = None
        elif tag == "select" and self._sel and self.cur is not None:
            self.cur.setdefault(self._sel[0], []).append(self._sel[1] or "")
            self._sel = None

    def data(self):
        return next(f for f in self.forms if f.get("action") == [self.action])


def _form(html, action):
    p = _Form(action)
    p.feed(html)
    return p.data()


def test_screen_hosts_all_three_forms_for_owner():
    html = v.stay_settings(_req()).content.decode()
    for action in ("kurtaxe", "house_rules", "stay_hours", "card_amenities"):
        assert f'value="{action}"' in html, action


@pytest.mark.parametrize("action", ["kurtaxe", "house_rules"])
def test_kurtaxe_and_house_rules_forms_unchanged_round_trip_keeps_settings(action):
    """W0: форма, отправленная без правок, ничего не меняет."""
    s = StaySettings.load()
    s.kurtaxe_cents, s.kurtaxe_label, s.house_rules = 250, "Kurbeitrag", "Ruhe ab 22 Uhr"
    s.kurtaxe_children_free, s.kurtaxe_child_cents = False, 120
    s.save()
    before = StaySettings.objects.values().get(pk=s.pk)
    data = _form(v.stay_settings(_req()).content.decode(), action)
    v.stay_settings(_req("post", data))
    after = StaySettings.objects.values().get(pk=s.pk)
    before.pop("updated_at"), after.pop("updated_at")
    assert after == before


def test_kurtaxe_and_house_rules_are_separate_forms():
    """UX-D D6.8: формы разные — сохранение одной не трогает поля другой."""
    s = StaySettings.load()
    s.kurtaxe_cents, s.house_rules = 250, "Ruhe ab 22 Uhr"
    s.save()
    data = _form(v.stay_settings(_req()).content.decode(), "kurtaxe")
    assert "house_rules" not in data
    v.stay_settings(_req("post", {**data, "kurtaxe_eur": ["3,00"]}))
    assert (StaySettings.load().kurtaxe_cents, StaySettings.load().house_rules) == (
        300,
        "Ruhe ab 22 Uhr",
    )
    data = _form(v.stay_settings(_req()).content.decode(), "house_rules")
    assert "kurtaxe_eur" not in data
    v.stay_settings(_req("post", {**data, "house_rules": ["Keine Haustiere"]}))
    s = StaySettings.load()
    assert (s.kurtaxe_cents, s.house_rules) == (300, "Keine Haustiere")


def _grant(req, *keys):
    Membership.objects.filter(user=req.user).update(
        permissions={"add": list(keys), "remove": [], "template": ""}
    )
    return req


def test_staff_house_rules_off_by_default_owner_grants():
    """UX-D D6.8 (решение владельца): право «Hausordnung bearbeiten» — отдельное,
    у сотрудника по умолчанию нет; выданное — правит Hausordnung, но не Kurtaxe."""
    s = StaySettings.load()
    s.kurtaxe_cents, s.house_rules = 250, "alt"
    s.save()
    html = v.stay_settings(_req(role=Membership.ROLE_STAFF)).content.decode()
    assert 'value="house_rules"' not in html and "data-house-rules-locked" in html
    v.stay_settings(
        _req("post", {"action": "house_rules", "house_rules": "neu"}, role=Membership.ROLE_STAFF)
    )
    assert StaySettings.load().house_rules == "alt"

    req = _grant(_req(role=Membership.ROLE_STAFF), "hausordnung.edit")
    html = v.stay_settings(req).content.decode()
    assert 'value="house_rules"' in html and 'value="kurtaxe"' not in html
    req = _grant(
        _req(
            "post",
            {"action": "house_rules", "house_rules": "neu"},
            role=Membership.ROLE_STAFF,
        ),
        "hausordnung.edit",
    )
    v.stay_settings(req)
    req = _grant(
        _req("post", {"action": "kurtaxe", "kurtaxe_eur": "9"}, role=Membership.ROLE_STAFF),
        "hausordnung.edit",
    )
    v.stay_settings(req)
    s = StaySettings.load()
    assert (s.house_rules, s.kurtaxe_cents) == ("neu", 250)


def test_admin_edits_house_rules_by_default():
    html = v.stay_settings(_req(role=Membership.ROLE_ADMIN)).content.decode()
    assert 'value="house_rules"' in html


def test_old_units_url_cannot_bypass_house_rules_permission():
    from django.core.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        views.units(
            _req(
                "post",
                {"action": "house_rules", "house_rules": "x"},
                role=Membership.ROLE_STAFF,
                path="/dashboard/stays/units/",
            )
        )
    assert StaySettings.load().house_rules == ""


def test_hours_round_trip_keeps_settings():
    s = StaySettings.load()
    s.checkin_hour, s.checkout_hour = 16, 10
    s.save(update_fields=["checkin_hour", "checkout_hour"])
    data = _form(v.stay_settings(_req()).content.decode(), "stay_hours")
    v.stay_settings(_req("post", data))
    s = StaySettings.load()
    assert (s.checkin_hour, s.checkout_hour) == (16, 10)


def test_post_returns_to_screen():
    resp = v.stay_settings(
        _req("post", {"action": "stay_hours", "checkin_hour": "15", "checkout_hour": "11"})
    )
    assert resp.status_code == 302 and resp.url == URL


def test_foreign_action_rejected():
    assert v.stay_settings(_req("post", {"action": "gap_deal", "enabled": "1"})).status_code == 400
    assert StaySettings.load().gap_max_nights == 0


def test_staff_sees_read_only_kurtaxe_and_hours_but_edits_card_amenities():
    s = StaySettings.load()
    s.kurtaxe_cents = 300
    s.save(update_fields=["kurtaxe_cents"])
    html = v.stay_settings(_req(role=Membership.ROLE_STAFF)).content.decode()
    assert "data-kurtaxe-state" in html and "data-hours-state" in html
    assert 'value="kurtaxe"' not in html and 'value="stay_hours"' not in html
    assert 'value="card_amenities"' in html
    v.stay_settings(
        _req("post", {"action": "kurtaxe", "kurtaxe_eur": "9"}, role=Membership.ROLE_STAFF)
    )
    assert StaySettings.load().kurtaxe_cents == 300


def test_card_amenities_saved_by_staff_targeted_write():
    tenant = TenantFactory(
        schema_name=f"t_{uuid.uuid4().hex[:8]}",
        slug=f"t{uuid.uuid4().hex[:6]}",
        auto_create_schema=False,
    )
    tenant.site_config = {"theme": "keep"}
    tenant.save(update_fields=["site_config"])
    req = _req(
        "post",
        {"action": "card_amenities", "card_amenity": ["wifi"]},
        role=Membership.ROLE_STAFF,
        tenant=tenant,
    )
    v.stay_settings(req)
    tenant.refresh_from_db()
    assert tenant.site_config["theme"] == "keep"
    assert tenant.site_config.get("stay_card_amenities") == ["wifi"]


def test_units_list_no_longer_hosts_these_forms():
    text = (ROOT / "templates/stays/units.html").read_text()
    for action in ("kurtaxe", "house_rules", "stay_hours", "card_amenities"):
        assert f'value="{action}"' not in text, action
    assert "stays:stay-settings" in text


def test_legacy_post_and_bookmark_land_on_new_screen():
    resp = views.units(
        _req(
            "post",
            {"action": "stay_hours", "checkin_hour": "14", "checkout_hour": "11"},
            path="/dashboard/stays/units/",
        )
    )
    assert resp.url == URL
    resp = views.units(
        _req(data={"tab": "einstellungen", "sec": "kurtaxe"}, path="/dashboard/stays/units/")
    )
    assert resp.status_code == 302 and resp.url == URL


def test_home_urls_point_here():
    for action in ("kurtaxe", "house_rules", "stay_hours", "card_amenities"):
        assert settings_actions.home_url(action) == URL


def test_nav_and_permissions():
    from apps.core import nav_registry, view_perms

    entry = next(e for e in nav_registry.ENTRIES if e.url_name == "stays:stay-settings")
    assert entry.hub == "settings" and entry.group == "zimmer" and entry.module_key == "stays"
    rule = view_perms.RULES["stays:stay-settings"]
    assert (rule.read, rule.write) == ("einstellungen.view", "einstellungen.edit")


def test_template_has_no_scripts():
    text = (ROOT / "templates/stays/stay_settings.html").read_text()
    assert "<script" not in text and not re.search(r"\son[a-z]+=", text)


def test_old_units_url_cannot_bypass_card_amenities_permission(monkeypatch):
    """Ревью D4.3: удобства на карточке — einstellungen.edit; POST на старый адрес
    списка номеров (правило sortiment.edit) их не обходит."""
    from django.core.exceptions import PermissionDenied

    from apps.core import permissions

    real = permissions.has_perm
    monkeypatch.setattr(
        views, "has_perm", lambda u, k: False if k == "einstellungen.edit" else real(u, k)
    )
    with pytest.raises(PermissionDenied):
        views.units(
            _req(
                "post",
                {"action": "card_amenities", "card_amenity": ["wifi"]},
                path="/dashboard/stays/units/",
            )
        )


def test_read_only_notice_names_house_rules_right():
    html = v.stay_settings(_req(role=Membership.ROLE_STAFF)).content.decode()
    assert "nur Inhaber und Admins" in html and "Hausordnung bearbeiten" in html


def test_house_rules_post_without_field_does_not_wipe_text():
    s = StaySettings.load()
    s.house_rules = "Ruhe ab 22 Uhr"
    s.save(update_fields=["house_rules"])
    v.stay_settings(_req("post", {"action": "house_rules"}))
    assert StaySettings.load().house_rules == "Ruhe ab 22 Uhr"
