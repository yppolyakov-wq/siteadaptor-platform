"""UX-D D4.1: «Tarife» — свой экран: список строками, «＋ Tarif» шторкой, правка тарифа.

Раньше тариф можно было только создать, вкл/выкл и удалить (карточка во вкладке
«Einstellungen» списка номеров)."""

import json
import re
import uuid
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory
from django.urls import reverse

from apps.core.models import Membership
from apps.stays import rate_plan_views as v
from apps.stays import services
from apps.stays.models import RatePlan, StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, role=Membership.ROLE_OWNER, drawer=False, path="/x/"):
    extra = {"HTTP_X_SF_DRAWER": "1"} if drawer else {}
    req = getattr(RequestFactory(), method)(path, data or {}, **extra)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(disabled_modules=[], business_type="hotel")
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": role})
    return req


def _unit(name=None):
    return StayUnit.objects.create(name=name or f"DZ {uuid.uuid4().hex[:4]}", price_cents=10000)


def _plan(**kw):
    defaults = {"name": "Mit Frühstück", "percent_adjust": -10, "surcharge_cents": 1500}
    defaults.update(kw)
    return RatePlan.objects.create(**defaults)


class _Fields(HTMLParser):
    """Поля формы #rp-form так, как их отправит браузер."""

    def __init__(self):
        super().__init__()
        self.on, self.data, self._ta, self._sel = False, {}, None, None

    def _add(self, k, val):
        self.data.setdefault(k, []).append(val)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.on = a.get("id") == "rp-form"
            return
        if not self.on or not a.get("name") and tag != "option":
            return
        if tag == "input":
            if a.get("type") in ("checkbox", "radio") and "checked" not in a:
                return
            self._add(a["name"], a.get("value", ""))
        elif tag == "textarea":
            self._ta = [a["name"], ""]
        elif tag == "select":
            self._sel = [a["name"], None]
        elif tag == "option" and self._sel and "selected" in a:
            self._sel[1] = a.get("value", "")

    def handle_data(self, d):
        if self._ta:
            self._ta[1] += d

    def handle_endtag(self, tag):
        if tag == "form":
            self.on = False
        elif tag == "textarea" and self._ta:
            self._add(*self._ta)
            self._ta = None
        elif tag == "select" and self._sel:
            self._add(self._sel[0], self._sel[1] or "")
            self._sel = None


def _edit(rp, method="get", data=None, role=Membership.ROLE_OWNER):
    return v.rate_plan_edit(_req(method, data, role), pk=rp.pk)


def test_list_rows_have_no_editable_fields_and_link_to_the_plan():
    rp = _plan()
    html = v.rate_plans(_req()).content.decode()
    row = html[html.index("data-rate-plan-row") :]
    row = row[: row.index("</li>")]
    assert reverse("stays:rate-plan-edit", args=[rp.pk]) in row
    assert not re.search(r"<(input|select|textarea)(?![^>]*type=\"hidden\")", row)
    assert "−10" in html or "-10" in html


def test_list_toggle_stays_on_list():
    rp = _plan()
    resp = v.rate_plans(_req("post", {"action": "rateplan_toggle", "rateplan": str(rp.pk)}))
    rp.refresh_from_db()
    assert resp.url == reverse("stays:rate-plans") and not rp.is_active


def test_list_rejects_foreign_actions():
    resp = v.rate_plans(_req("post", {"action": "kurtaxe", "kurtaxe_eur": "9"}))
    assert resp.status_code == 400


def test_edit_changes_every_field():
    a, b = _unit("A"), _unit("B")
    rp = _plan()
    _edit(
        rp,
        "post",
        {
            "action": "update",
            "name": "Halbpension",
            "description": "Abendessen inklusive",
            "percent_adjust": "5",
            "surcharge_eur": "32,50",
            "meal_plan": RatePlan.MEAL_HALF if hasattr(RatePlan, "MEAL_HALF") else "half_board",
            "cancellation": RatePlan.CANCEL_NONREF,
            "free_cancel_days": "0",
            "prepayment_percent": "100",
            "sort_order": "3",
            "rate_scope": "some",
            "units": [str(b.pk)],
        },
    )
    rp.refresh_from_db()
    assert (rp.name, rp.percent_adjust, rp.surcharge_cents) == ("Halbpension", 5, 3250)
    assert rp.cancellation == RatePlan.CANCEL_NONREF and rp.prepayment_percent == 100
    assert not rp.applies_to_all and set(rp.units.all()) == {b}
    assert a not in rp.units.all()


def test_saving_the_rendered_form_unchanged_keeps_the_plan():
    unit = _unit()
    rp = _plan(applies_to_all=False, prepayment_percent=30, free_cancel_days=7, sort_order=2)
    rp.units.set([unit])
    data = _Fields()
    data.feed(_edit(rp).content.decode())
    before = RatePlan.objects.values().get(pk=rp.pk)
    resp = _edit(rp, "post", data.data)
    assert resp.status_code == 302
    after = RatePlan.objects.values().get(pk=rp.pk)
    before.pop("updated_at"), after.pop("updated_at")
    assert after == before and set(rp.units.all()) == {unit}


@pytest.mark.parametrize(
    "field, value",
    [
        ("percent_adjust", "abc"),
        ("percent_adjust", "999"),
        ("surcharge_eur", "zwölf"),
        ("surcharge_eur", "1e999"),
        ("meal_plan", "caviar"),
        ("cancellation", "maybe"),
        ("prepayment_percent", "150"),
        ("name", "  "),
    ],
)
def test_bad_input_is_rejected_at_the_field_and_plan_untouched(field, value):
    rp = _plan()
    data = {
        "action": "update",
        "name": "Neu",
        "percent_adjust": "0",
        "surcharge_eur": "0",
        field: value,
    }
    resp = _edit(rp, "post", data)
    html = resp.content.decode()
    rp.refresh_from_db()
    assert resp.status_code == 200 and rp.name == "Mit Frühstück"
    assert 'aria-invalid="true"' in html


def test_some_scope_without_categories_is_an_error():
    rp = _plan()
    resp = _edit(rp, "post", {"action": "update", "name": "X", "rate_scope": "some"})
    rp.refresh_from_db()
    assert resp.status_code == 200 and rp.name == "Mit Frühstück" and rp.applies_to_all


def test_garbage_pk_is_404():
    with pytest.raises(Http404):
        v.rate_plan_edit(_req(), pk=uuid.uuid4())


def test_editing_the_plan_does_not_change_existing_booking():
    unit = _unit()
    rp = _plan()
    start = date.today() + timedelta(days=10)
    booking = services.book_stay(
        unit, arrival=start, departure=start + timedelta(days=2), name="Gast", rate_plan=rp
    )
    snap = (booking.total_cents, booking.rate_snapshot, booking.deposit_cents)
    _edit(rp, "post", {"action": "update", "name": "Teuer", "percent_adjust": "50"})
    booking.refresh_from_db()
    assert (booking.total_cents, booking.rate_snapshot, booking.deposit_cents) == snap


def test_staff_sees_plan_read_only():
    rp = _plan()
    html = _edit(rp, role=Membership.ROLE_STAFF).content.decode()
    assert "<fieldset" in html and " disabled" in html
    assert 'form="rp-delete"' not in html
    listing = v.rate_plans(_req(role=Membership.ROLE_STAFF)).content.decode()
    assert reverse("stays:rate-plan-new") not in listing


def test_permissions_are_price_permissions():
    from apps.core import view_perms

    for name in ("stays:rate-plans", "stays:rate-plan-new", "stays:rate-plan-edit"):
        rule = view_perms.RULES[name]
        assert (rule.read, rule.write) == ("preise.view", "preise.edit")


def test_new_plan_drawer_fragment_and_create_navigates():
    resp = v.rate_plan_new(_req(drawer=True))
    html = resp.content.decode()
    assert resp["X-Sf-Fragment"] == "1" and "<script" not in html
    assert not re.search(r"\son[a-z]+=", html)
    resp = v.rate_plan_new(
        _req(
            "post",
            {
                "name": "Frühbucher",
                "percent_adjust": "-15",
                "rate_scope": "all",
                "next": "/dashboard/stays/tarife/",
            },
            drawer=True,
        )
    )
    rp = RatePlan.objects.get(name="Frühbucher")
    data = json.loads(resp.content)
    assert data["navigate"] and data["location"].startswith(
        reverse("stays:rate-plan-edit", args=[rp.pk])
    )
    assert rp.percent_adjust == -15 and rp.applies_to_all


def test_new_plan_error_keeps_input():
    resp = v.rate_plan_new(_req("post", {"name": "", "surcharge_eur": "12,50"}, drawer=True))
    html = resp.content.decode()
    assert resp["X-Sf-Fragment"] == "1" and 'value="12,50"' in html
    assert not RatePlan.objects.exists()


def test_new_plan_without_js_redirects_to_plan_page():
    resp = v.rate_plan_new(_req("post", {"name": "Basis"}))
    rp = RatePlan.objects.get(name="Basis")
    assert resp.status_code == 302 and resp.url == reverse("stays:rate-plan-edit", args=[rp.pk])


def test_drawer_aware_is_innermost():
    from apps.core import drawer

    code = drawer.drawer_aware(lambda r: r).__code__
    chain = [v.rate_plan_new]
    while hasattr(chain[-1], "__wrapped__"):
        chain.append(chain[-1].__wrapped__)
    assert chain[-2].__code__ is code


def test_units_settings_tab_no_longer_hosts_rate_plan_forms():
    text = (ROOT / "templates/stays/units.html").read_text()
    assert 'value="rateplan"' not in text and 'value="rateplan_units"' not in text
    assert "stays:rate-plans" in text


def test_legacy_rateplan_post_to_units_returns_to_new_screen():
    from apps.stays import views

    req = _req("post", {"action": "rateplan_toggle", "rateplan": str(_plan().pk)})
    resp = views.units(req)
    assert resp.url == reverse("stays:rate-plans")


def test_tarife_is_a_sortiment_subitem_for_hotels():
    from apps.core import nav_registry

    entry = next(e for e in nav_registry.ENTRIES if e.url_name == "stays:rate-plans")
    assert entry.hub == "sellables" and entry.module_key == "stays"


def test_templates_have_no_inline_scripts():
    for name in ("rate_plans.html", "rate_plan_edit.html", "_rate_plan_fields.html"):
        text = (ROOT / "templates/stays" / name).read_text()
        assert "<script" not in text and not re.search(r"\son[a-z]+=", text)
