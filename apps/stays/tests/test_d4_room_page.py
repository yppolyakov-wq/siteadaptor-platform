"""UX-D D4.6: страница номера — вкладки рисует сервер, мини-формы возвращают на свою.

Раньше вкладки переключал инлайн-скрипт, активной всегда была первая, а после любой
мини-формы (сезон, блокировка, комната, iCal) владелец оказывался на «Grunddaten» и
искал своё место заново. Главная форма ``unit_settings`` остаётся ОДНОЙ на трёх
вкладках (инвариант W0: она пишет все поля разом)."""

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
from apps.stays import views
from apps.stays.models import Room, StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "templates/stays/unit_page.html"

# Поля, которые пишет unit_settings (W0: все — внутри #unit-form).
SETTINGS_FIELDS = (
    "description",
    "bed_type",
    "area_sqm",
    "amenities",
    "photos",
    "price_eur",
    "weekend_price_eur",
    "deposit_eur",
    "vat_rate",
    "gap_present",
    "gap_max_nights",
    "gap_discount_percent",
    "quantity",
    "min_nights",
    "max_guests",
    "require_manual_confirm",
)
SAVED = (
    "name",
    "description",
    "price_cents",
    "weekend_price_cents",
    "deposit_cents",
    "vat_rate",
    "gap_max_nights",
    "gap_discount_percent",
    "quantity",
    "min_nights",
    "max_guests",
    "require_manual_confirm",
    "area_sqm",
    "bed_type",
    "amenities",
    "is_active",
)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, role=Membership.ROLE_OWNER):
    req = getattr(RequestFactory(), method)("/dashboard/stays/units/x/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(disabled_modules=[], business_type="hotel")
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": role})
    return req


def _unit(**kw):
    defaults = {
        "name": "Doppelzimmer Seeblick",
        "description": "Balkon zum See",
        "price_cents": 12900,
        "weekend_price_cents": 14900,
        "deposit_cents": 3000,
        "quantity": 2,
        "min_nights": 2,
        "max_guests": 3,
        "require_manual_confirm": True,
        "area_sqm": 24,
        "bed_type": "Doppelbett",
        "amenities": ["wifi", "balcony"],
        "gap_max_nights": 2,
        "gap_discount_percent": 15,
    }
    defaults.update(kw)
    return StayUnit.objects.create(**defaults)


def _page(unit, role=Membership.ROLE_OWNER, **get):
    return views.units(_req(data=get, role=role), pk=unit.pk).content.decode()


class _Forms(HTMLParser):
    """Поля #unit-form так, как их отправит браузер (выключенный fieldset — не шлётся)."""

    def __init__(self):
        super().__init__()
        self.in_main = False
        self.disabled = 0
        self.fields: list[tuple[str, str]] = []
        self.main_names: set[str] = set()
        self.nested_forms = 0
        self.mini_forms: list[dict] = []
        self._mini = None
        self._textarea = None
        self._select = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            if self.in_main:
                self.nested_forms += 1
            elif a.get("id") == "unit-form":
                self.in_main = True
            else:
                self._mini = {}
            return
        if tag == "fieldset" and self.in_main:
            self.disabled += 1 if "disabled" in a else 0
            self._fs = getattr(self, "_fs", []) + ["disabled" in a]
            return
        name = a.get("name")
        if self._mini is not None and tag == "input" and name:
            self._mini[name] = a.get("value", "")
        if not self.in_main or not name:
            if self.in_main and tag == "option" and self._select is not None:
                self._option(a)
            return
        self.main_names.add(name)
        if self.disabled:
            return
        if tag == "input":
            kind = a.get("type", "text")
            if kind in ("checkbox", "radio") and "checked" not in a:
                return
            if kind == "file":
                return
            default = "on" if kind in ("checkbox", "radio") else ""  # как браузер
            self.fields.append((name, a.get("value", default)))
        elif tag == "textarea":
            self._textarea = [name, ""]
        elif tag == "select":
            self._select = [name, None, None]

    def _option(self, a):
        if self._select[2] is None:
            self._select[2] = a.get("value", "")
        if "selected" in a:
            self._select[1] = a.get("value", "")

    def handle_data(self, data):
        if self._textarea is not None:
            self._textarea[1] += data

    def handle_endtag(self, tag):
        if tag == "form":
            if self.in_main:
                self.in_main = False
            elif self._mini is not None:
                self.mini_forms.append(self._mini)
                self._mini = None
        elif tag == "fieldset" and self.in_main and getattr(self, "_fs", None):
            if self._fs.pop():
                self.disabled -= 1
        elif tag == "textarea" and self._textarea is not None:
            self.fields.append(tuple(self._textarea))
            self._textarea = None
        elif tag == "select" and self._select is not None:
            name, sel, first = self._select
            self.fields.append((name, sel if sel is not None else first))
            self._select = None


def _parse(html):
    p = _Forms()
    p.feed(html)
    data = {}
    for name, value in p.fields:
        data.setdefault(name, []).append(value)
    return data, p


def _snapshot(unit):
    unit.refresh_from_db()
    return {f: getattr(unit, f) for f in SAVED}


# --- вкладки ------------------------------------------------------------------


def test_page_has_five_server_tabs_first_active_by_default():
    html = _page(_unit())
    tabs = re.findall(r"<button[^>]*data-pf-tab=\"([a-z]+)\"[^>]*>", html)
    assert tabs == list(views.ROOM_TABS)
    assert html.count('role="tab" aria-selected="true"') == 1
    assert re.search(r'data-pf-tab="basis"[^>]*aria-selected="true"', html)
    assert 'id="unit-form"' in html and "data-room-page" in html


@pytest.mark.parametrize("tab", ["preise", "regeln", "zimmer", "ical"])
def test_tab_param_selects_the_tab(tab):
    html = _page(_unit(), tab=tab)
    assert re.search(rf'data-pf-tab="{tab}"[^>]*aria-selected="true"', html)
    assert re.search(r'data-pf-tab="basis"[^>]*aria-selected="false"', html)
    form = re.search(r'<form id="unit-form"[^>]*>', html).group(0)
    assert (" hidden" in form) == (tab in ("zimmer", "ical"))


def test_junk_tab_falls_back_to_basic_data():
    html = _page(_unit(), tab="<script>")
    assert re.search(r'data-pf-tab="basis"[^>]*aria-selected="true"', html)
    assert "&lt;script&gt;" not in html  # мусор не попадает в скрытое поле `tab`


# --- одна форма, всё внутри (W0) ----------------------------------------------


def test_all_settings_fields_are_inside_the_one_form_without_nested_forms():
    html = _page(_unit())
    _data, p = _parse(html)
    assert p.nested_forms == 0
    for name in SETTINGS_FIELDS:
        assert name in p.main_names, name
    # мини-формы — отдельные и не несут полей unit_settings
    assert p.mini_forms
    for mini in p.mini_forms:
        assert mini.get("action") != "unit_settings"


def test_saving_the_rendered_form_unchanged_keeps_every_value():
    unit = _unit()
    Room.objects.create(unit=unit, number="101")
    Room.objects.create(unit=unit, number="102")
    before = _snapshot(unit)
    data, _p = _parse(_page(unit, tab="preise"))
    resp = views.units(_req("post", data), pk=unit.pk)
    assert resp.status_code == 302 and resp.url.endswith(f"/units/{unit.pk}/?tab=preise")
    assert _snapshot(unit) == before


def test_staff_sees_prices_disabled_and_saving_keeps_them():
    unit = _unit()
    html = _page(unit, role=Membership.ROLE_STAFF)
    assert "data-prices-readonly" in html
    assert re.search(r"<fieldset[^>]*disabled", html)
    before = _snapshot(unit)
    data, _p = _parse(html)
    assert "price_eur" not in data and "gap_present" not in data
    views.units(_req("post", data, role=Membership.ROLE_STAFF), pk=unit.pk)
    assert _snapshot(unit) == before


# --- возврат на вкладку --------------------------------------------------------


@pytest.mark.parametrize("tab, suffix", [("basis", "/"), ("preise", "/?tab=preise")])
def test_main_save_returns_to_the_tab_it_was_sent_from(tab, suffix):
    unit = _unit()
    data, _p = _parse(_page(unit))
    data["tab"] = [tab]
    resp = views.units(_req("post", data), pk=unit.pk)
    assert resp.url.endswith(f"/units/{unit.pk}{suffix}")


def test_every_mini_form_carries_the_tab_it_lives_on():
    unit = _unit()
    Room.objects.create(unit=unit, number="101")
    unit.images = [{"id": "a1", "url": "/media/x.jpg", "is_primary": True}]
    unit.save(update_fields=["images"])
    from apps.stays.models import ICalSource, SeasonRate, UnitBlock

    SeasonRate.objects.create(
        unit=unit, start_date="2026-12-01", end_date="2026-12-10", price_cents=1000
    )
    UnitBlock.objects.create(unit=unit, start_date="2026-12-11", end_date="2026-12-12")
    ICalSource.objects.create(unit=unit, url="https://example.com/a.ics")
    _data, p = _parse(_page(unit))
    seen = set()
    for mini in p.mini_forms:
        action = mini.get("action")
        if action is None:
            continue  # формы хрома кабинета (язык, выход)
        seen.add(action)
        if action == "toggle":
            continue  # шапка: текущая вкладка страницы
        assert mini.get("tab") == views.ROOM_ACTION_TAB[action], action
    assert seen >= {
        "toggle",
        "photo_delete",
        "rate",
        "rate_delete",
        "block",
        "block_delete",
        "room_add",
        "room_delete",
        "ical_add",
        "ical_sync",
        "ical_delete",
    }


@pytest.mark.parametrize(
    "data, tab",
    [
        ({"action": "room_add", "number": "103", "tab": "zimmer"}, "zimmer"),
        ({"action": "block", "start_date": "2027-01-02", "end_date": "2027-01-03"}, "regeln"),
        ({"action": "rate", "start_date": "x", "tab": "garbage"}, "preise"),
        ({"action": "ical_add", "url": "https://example.com/b.ics"}, "ical"),
        ({"action": "toggle", "tab": "ical"}, "ical"),
    ],
)
def test_mini_forms_return_to_their_tab(data, tab):
    unit = _unit()
    resp = views.units(_req("post", {**data, "unit": str(unit.pk)}), pk=unit.pk)
    assert resp.status_code == 302 and resp.url.endswith(f"/units/{unit.pk}/?tab={tab}")


def test_photo_delete_returns_to_basic_data_without_query():
    unit = _unit(images=[{"id": "a1", "url": "/media/x.jpg", "is_primary": True}])
    resp = views.units(
        _req("post", {"action": "photo_delete", "unit": str(unit.pk), "image": "zz"}), pk=unit.pk
    )
    assert resp.url.endswith(f"/units/{unit.pk}/")


# --- шаблон: без инлайн-скриптов, копирование кнопкой, ссылки на новые экраны -----


def test_template_has_no_inline_script_or_handlers():
    src = TEMPLATE.read_text()
    assert "<script" not in src
    assert not re.search(r"\son[a-z]+=", src)
    list_src = (ROOT / "templates/stays/units.html").read_text()
    assert "<script" not in list_src and "unit_page" not in list_src


def test_ical_link_is_copied_with_a_button():
    html = _page(_unit(), tab="ical")
    assert 'id="room-ical-export"' in html
    assert 'data-copy-target="room-ical-export"' in html
    assert "this.select()" not in html


def test_zero_means_general_setting_links_to_the_new_screens():
    html = _page(_unit(), tab="preise")
    assert "/dashboard/stays/preisregeln/?tab=luecken" in html
    assert "/dashboard/stays/preisregeln/?tab=regeln" in html
    assert "data-rate-plans-link" in html and "data-price-calendar-link" in html


def test_header_summary_shows_price_capacity_and_rooms():
    unit = _unit()
    Room.objects.create(unit=unit, number="101")
    html = _page(unit)
    summary = re.search(r"data-room-summary>(.*?)</p>", html, re.S).group(1)
    assert "129" in summary and "1" in summary
    assert "/unterkunft/" in html  # «Auf der Website ansehen»


def test_quantity_is_readonly_when_rooms_define_capacity():
    unit = _unit()
    Room.objects.create(unit=unit, number="101")
    html = _page(unit, tab="regeln")
    assert re.search(r'name="quantity"[^>]*readonly', html)
    assert not re.search(r'name="quantity"[^>]*readonly', _page(_unit(name="Ohne Zimmer")))


def test_list_renders_rows_only():
    _unit()
    html = views.units(_req()).content.decode()
    assert 'id="unit-form"' not in html and "data-pf-tab" not in html
    assert "data-units-list" in html
