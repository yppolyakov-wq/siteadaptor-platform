"""KA-12 Zimmer Z-3: экран «Preise & Verfügbarkeit» — сетка, Vorschau, Übernehmen, день.

Смотрят все роли кабинета, правят owner/admin (О-4); Vorschau — GET без записи;
«Übernehmen» сверяет отпечаток; форма дня задаёт поля целиком (сентинел)."""

import re
import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache.backends.locmem import LocMemCache
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Membership
from apps.core.modules import default_disabled_for
from apps.stays import night_rates as nr
from apps.stays import price_calendar_views as v
from apps.stays.models import NightRate, SeasonRate, StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.core import ratelimit

    monkeypatch.setattr(ratelimit, "cache", LocMemCache(f"rl-z3-{uuid.uuid4()}", {}))


def _day(n=1):
    return timezone.localdate() + timedelta(days=n)


def _user(role=Membership.ROLE_OWNER):
    tag = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"u-{tag}", email=f"u-{tag}@test.de", password="pw12345678"
    )
    Membership.objects.get_or_create(user=user, defaults={"role": role})
    return user


def _req(method="get", path="/dashboard/stays/preise/", data=None, role=Membership.ROLE_OWNER):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = _user(role)
    request.tenant = TenantFactory.build(
        business_type="hotel", disabled_modules=list(default_disabled_for("hotel"))
    )
    return request


def _unit(name=None, **kw):
    kw.setdefault("price_cents", 10000)
    kw.setdefault("quantity", 2)
    return StayUnit.objects.create(name=name or f"DZ {uuid.uuid4().hex[:6]}", **kw)


def _html(resp):
    return resp.content.decode()


def _bulk(unit, **extra):
    data = {
        "unit": [str(unit.pk)],
        "from": _day(1).isoformat(),
        "bis": _day(3).isoformat(),
        "wd": [str(i) for i in range(7)],
        "price_mode": "set",
        "price": "123,40",
    }
    data.update(extra)
    return data


def test_grid_shows_prices_sources_and_badges():
    unit = _unit(name="Seeblick-Suite", weekend_price_cents=13000)
    SeasonRate.objects.create(
        unit=unit, label="Sommer", start_date=_day(2), end_date=_day(2), price_cents=15000
    )
    NightRate.objects.create(
        unit=unit, day=_day(1), price_cents=11111, stop_sell=True, min_nights=3
    )
    html = _html(v.price_calendar(_req(data={"tage": "14"})))
    assert "Seeblick-Suite" in html and "111,11" in html and "Sommer" in html
    assert "Stopp" in html and "min. 3" in html
    assert "data-price-grid" in html and "data-price-cards" in html
    assert "md:hidden" in html and "hidden md:block" in html


def test_window_sizes():
    _unit()
    resp = v.price_calendar(_req(data={"tage": "31"}))
    assert resp.status_code == 200
    links = re.compile(r'href="/dashboard/stays/preise/[0-9a-f-]{36}/')
    assert len(links.findall(_html(resp))) == 31 * 2  # таблица + карточки
    assert len(links.findall(_html(v.price_calendar(_req(data={"tage": "99"}))))) == 14 * 2


def test_past_von_clamped_and_garbage_params_ok():
    _unit()
    for params in ({"von": "2001-01-01"}, {"von": "2026-13-45", "tage": "x"}, {"kat": "nope"}):
        assert v.price_calendar(_req(data=params)).status_code == 200


def test_grid_query_budget_independent_of_units():
    def count(n):
        StayUnit.objects.all().delete()
        for _ in range(n):
            _unit()
        req = _req()
        with CaptureQueriesContext(connection) as ctx:
            v.price_calendar(req)
        return len(ctx.captured_queries)

    assert count(3) == count(6)


def test_preview_writes_nothing():
    unit = _unit()
    req = _req(data={**_bulk(unit), "vorschau": "1", "tage": "14"})
    with CaptureQueriesContext(connection) as ctx:
        resp = v.price_calendar(req)
    sql = " ".join(q["sql"] for q in ctx.captured_queries if "stays_nightrate" in q["sql"])
    assert "INSERT" not in sql and "UPDATE" not in sql and "DELETE" not in sql
    assert not NightRate.objects.exists()
    html = _html(resp)
    assert "Betroffene Nächte: 3" in html and 'name="fingerprint"' in html


def test_apply_after_preview_writes_and_redirects():
    unit = _unit()
    action, _ = nr.parse_action(_bulk(unit))
    plan = nr.build_plan([unit], nr.select_days(_day(1), _day(3), range(7)), action)
    req = _req(
        "post",
        "/dashboard/stays/preise/uebernehmen/",
        {**_bulk(unit), "fingerprint": plan.fingerprint(action), "tage": "14"},
    )
    resp = v.price_calendar_apply(req)
    assert resp.status_code == 302 and "next" not in resp.url
    assert resp.url.startswith(reverse("stays:price-calendar"))
    assert set(NightRate.objects.values_list("price_cents", flat=True)) == {12340}


def test_apply_stale_fingerprint_writes_nothing():
    unit = _unit()
    req = _req("post", "/dashboard/stays/preise/uebernehmen/", {**_bulk(unit), "fingerprint": "x"})
    v.price_calendar_apply(req)
    assert not NightRate.objects.exists()
    assert any("geändert" in str(m) for m in get_messages(req))


@pytest.mark.parametrize("role", [Membership.ROLE_STAFF])
def test_staff_reads_but_cannot_write(role):
    unit = _unit()
    html = _html(v.price_calendar(_req(data={**_bulk(unit), "vorschau": "1"}, role=role)))
    assert "data-price-bulk" not in html and 'name="fingerprint"' not in html
    assert "data-price-grid" in html
    with pytest.raises(PermissionDenied):
        v.price_calendar_apply(_req("post", "/x/", {**_bulk(unit), "fingerprint": "x"}, role=role))
    with pytest.raises(PermissionDenied):
        v.price_day(
            _req("post", "/x/", {"price": "50", "day_present": "1"}, role=role),
            pk=unit.pk,
            day=_day(1).isoformat(),
        )
    assert not NightRate.objects.exists()


def test_admin_can_write():
    unit = _unit()
    req = _req(data={**_bulk(unit), "vorschau": "1"}, role=Membership.ROLE_ADMIN)
    assert "data-price-bulk" in _html(v.price_calendar(req))


def test_apply_get_is_405_and_anonymous_redirected(client):
    from django.contrib.auth.models import AnonymousUser

    req = RequestFactory().get("/dashboard/stays/preise/uebernehmen/")
    req.user = _user()
    assert v.price_calendar_apply(req).status_code == 405
    anon = RequestFactory().get("/dashboard/stays/preise/")
    anon.user = AnonymousUser()
    assert v.price_calendar(anon).status_code == 302


def test_day_fragment_and_page():
    unit = _unit()
    day = _day(2).isoformat()
    frag = v.price_day(_req(data={"box": "1"}), pk=unit.pk, day=day)
    assert "<html" not in _html(frag) and 'name="state"' in _html(frag)
    assert frag["Cache-Control"] == "private, no-store"
    page = v.price_day(_req(), pk=unit.pk, day=day)
    assert "<html" in _html(page)
    for bad in ("2026-13-01", "nope", (timezone.localdate() - timedelta(days=1)).isoformat()):
        with pytest.raises(Http404):
            v.price_day(_req(), pk=unit.pk, day=bad)
    with pytest.raises(Http404):
        v.price_day(_req(), pk=uuid.uuid4(), day=day)


def _state(unit, day):
    night = NightRate.objects.filter(unit=unit, day=day).first()
    return nr.state_fingerprint(unit.pk, day, nr.DayState.of(night))


def test_day_post_sets_and_resets():
    unit = _unit()
    day = _day(2)
    data = {"price": "77,50", "stop_sell": "1", "day_present": "1", "state": _state(unit, day)}
    v.price_day(_req("post", "/x/", data), pk=unit.pk, day=day.isoformat())
    row = NightRate.objects.get(unit=unit, day=day)
    assert row.price_cents == 7750 and row.stop_sell
    # пустая цена + снятый флажок при сентинеле → нейтрально → строка удалена
    data = {"price": "", "day_present": "1", "state": _state(unit, day)}
    v.price_day(_req("post", "/x/", data), pk=unit.pk, day=day.isoformat())
    assert not NightRate.objects.filter(unit=unit, day=day).exists()


def test_day_post_stale_state_refused():
    unit = _unit()
    day = _day(2)
    old = _state(unit, day)
    NightRate.objects.create(unit=unit, day=day, price_cents=5000)
    req = _req("post", "/x/", {"price": "60", "day_present": "1", "state": old})
    v.price_day(req, pk=unit.pk, day=day.isoformat())
    assert NightRate.objects.get(unit=unit, day=day).price_cents == 5000


def test_day_post_ignores_next():
    unit = _unit()
    day = _day(2)
    data = {"price": "60", "day_present": "1", "state": _state(unit, day), "next": "//evil.com"}
    resp = v.price_day(_req("post", "/x/", data), pk=unit.pk, day=day.isoformat())
    assert resp.url.startswith(reverse("stays:price-calendar"))


def test_nav_entry_and_entry_links():
    from apps.core import nav_registry

    assert "stays:price-calendar" in [e.url_name for e in nav_registry.ENTRIES]
    body = open("templates/stays/_belegungsplan_body.html").read()
    assert "stays:price-calendar" in body
    units_tpl = open("templates/stays/units.html").read()
    assert units_tpl.count("stays:price-calendar") >= 2 and "?kat={{ u.pk }}" in units_tpl


def test_screen_is_behind_stays_module_gate():
    """Модульный гейт — по префиксу (ModuleGatingMiddleware): экран под /dashboard/stays/."""
    from apps.core.modules import REGISTRY

    spec = next(m for m in REGISTRY if m.key == "stays")
    path = reverse("stays:price-calendar")
    assert any(path.startswith(p) for p in spec.url_prefixes)
