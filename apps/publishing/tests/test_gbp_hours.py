"""Д3-2 (GBP-Sync): часы работы между нашим профилем и Google — замки 1–9 плана
docs/d3-gbp-sync-plan-2026-10-18.md §9. Решение владельца В-3: обе стороны ручными
кнопками с предпросмотром, без автосинхронизации; особые часы — только чтение."""

from __future__ import annotations

import uuid

import pytest
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.publishing import gbp, gbp_hours, views
from apps.publishing.models import Channel
from apps.tenants.openinghours import normalize
from apps.tenants.tests.factories import TenantFactory

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_tenant")]

WEEK = {"0": ["09:00", "18:00"], "1": ["09:00", "18:30"], "5": ["08:15", "13:00"]}


def _p(day, oh, om, ch, cm, close_day=None):
    return {
        "openDay": day,
        "openTime": {"hours": oh, "minutes": om},
        "closeDay": close_day or day,
        "closeTime": {"hours": ch, "minutes": cm},
    }


# --- 1–5: чистое преобразование ------------------------------------------------------------


def test_to_periods_exact_with_minutes_and_closed_days_omitted():
    periods = gbp_hours.to_periods(WEEK)
    assert periods == [
        _p("MONDAY", 9, 0, 18, 0),
        _p("TUESDAY", 9, 0, 18, 30),
        _p("SATURDAY", 8, 15, 13, 0),
    ]


def test_roundtrip_on_all_demo_kits():
    from apps.tenants.demo_kits import KITS

    seen = 0
    for kit in KITS.values():
        if not kit.opening_hours:
            continue
        ours = normalize({str(d): list(r) for d, r in kit.opening_hours.items()})
        back, lossy = gbp_hours.from_periods(gbp_hours.to_periods(ours))
        assert lossy == set() and back == ours, kit.slug
        seen += 1
    assert seen > 5


def test_google_omits_zero_fields():
    # TimeOfDay без нулевых полей: {"hours": 9} == 09:00, {} == 00:00.
    back, lossy = gbp_hours.from_periods(
        [
            {
                "openDay": "MONDAY",
                "openTime": {"hours": 9},
                "closeDay": "MONDAY",
                "closeTime": {"hours": 17},
            }
        ]
    )
    assert back == {"0": ["09:00", "17:00"]} and lossy == set()


def test_split_shift_is_lossy():
    back, lossy = gbp_hours.from_periods([_p("MONDAY", 8, 0, 12, 0), _p("MONDAY", 14, 0, 18, 0)])
    assert lossy == {0} and "0" not in back


def test_overnight_is_lossy():
    back, lossy = gbp_hours.from_periods([_p("FRIDAY", 20, 0, 2, 0, close_day="SATURDAY")])
    assert lossy == {4} and back == {}


def test_24h_is_lossy():
    back, lossy = gbp_hours.from_periods([_p("SUNDAY", 0, 0, 24, 0)])
    assert lossy == {6} and back == {}


@pytest.mark.parametrize(
    "junk",
    [None, "x", [None, 5, "a"], [{"openDay": "FUNDAY"}], [{"openDay": "MONDAY", "openTime": "9"}]],
)
def test_malformed_periods_never_crash(junk):
    back, _lossy = gbp_hours.from_periods(junk)
    assert isinstance(back, dict)


def test_diff_marks_changed_and_lossy_rows():
    google = [
        _p("MONDAY", 9, 0, 18, 0),
        _p("TUESDAY", 10, 0, 18, 30),
        _p("WEDNESDAY", 8, 0, 12, 0),
        _p("WEDNESDAY", 14, 0, 18, 0),
    ]
    d = gbp_hours.diff(WEEK, google)
    rows = {r["wd"]: r for r in d.rows}
    assert not rows[0]["changed"]
    assert rows[1]["changed"]
    assert rows[2]["lossy"] and "08:00–12:00" in rows[2]["google"]
    assert rows[5]["changed"]  # у нас суббота открыта, в Google — нет
    assert not d.equal and d.lossy_days == {2}


# --- 6–9: отправка/забор ---------------------------------------------------------------


@pytest.fixture
def api(monkeypatch):
    state = {"periods": [], "special": 0, "patched": [], "gets": 0}

    def get_hours(token, v1):
        state["gets"] += 1
        return {"periods": list(state["periods"]), "special_count": state["special"]}

    def patch(token, v1, periods):
        state["patched"].append((v1, periods))

    monkeypatch.setattr(gbp, "access_token", lambda config: "tok")
    monkeypatch.setattr(gbp, "get_hours", get_hours)
    monkeypatch.setattr(gbp, "patch_regular_hours", patch)
    return state


CONFIG = {"refresh_token": "rt", "location": "accounts/1/locations/2"}


def test_push_with_empty_hours_refused_without_http(api):
    tenant = TenantFactory.build(opening_hours_structured={})
    with pytest.raises(gbp_hours.HoursError) as exc:
        gbp_hours.push(tenant, CONFIG)
    assert exc.value.code == "empty"
    assert api["gets"] == 0 and api["patched"] == []


def test_push_patches_only_regular_hours(monkeypatch, settings):
    calls = []

    class _R:
        status_code = 200

        def json(self):
            return {}

    def _patch(url, **kw):
        calls.append((url, kw))
        return _R()

    monkeypatch.setattr(gbp.requests, "patch", _patch)
    gbp.patch_regular_hours("tok", "locations/2", gbp_hours.to_periods(WEEK))
    (url, kw) = calls[0]
    assert url == f"{gbp.INFO_API}/locations/2"
    assert kw["params"] == {"updateMask": "regularHours"}
    assert set(kw["json"]) == {"regularHours"}
    assert "specialHours" not in repr(kw)


def test_push_blocked_when_google_has_lossy_days_until_confirmed(api):
    api["periods"] = [_p("MONDAY", 8, 0, 12, 0), _p("MONDAY", 14, 0, 18, 0)]
    tenant = TenantFactory.build(opening_hours_structured=WEEK)
    with pytest.raises(gbp_hours.HoursError) as exc:
        gbp_hours.push(tenant, CONFIG)
    assert exc.value.code == "lossy" and api["patched"] == []
    gbp_hours.push(tenant, CONFIG, confirm=True)
    assert api["patched"] == [("locations/2", gbp_hours.to_periods(WEEK))]


def test_pull_with_empty_google_hours_refused(api):
    tenant = TenantFactory.build(opening_hours_structured=WEEK)
    with pytest.raises(gbp_hours.HoursError) as exc:
        gbp_hours.pull_apply(tenant, CONFIG)
    assert exc.value.code == "google_empty"


def test_apply_pull_writes_only_hours_keeps_lossy_days_and_refreshes(api, monkeypatch):
    tenant = TenantFactory(schema_name=f"t_h{uuid.uuid4().hex[:6]}", auto_create_schema=False)
    tenant.opening_hours_structured = {"0": ["09:00", "18:00"], "2": ["10:00", "16:00"]}
    tenant.save(update_fields=["opening_hours_structured"])
    # Параллельная запись другой колонки (W7a) не должна быть затёрта снимком.
    type(tenant).objects.filter(pk=tenant.pk).update(site_config={"probe": 1})
    api["periods"] = [
        _p("MONDAY", 7, 0, 15, 0),
        _p("WEDNESDAY", 8, 0, 12, 0),
        _p("WEDNESDAY", 14, 0, 18, 0),
        _p("FRIDAY", 9, 0, 17, 0),
    ]
    refreshed = []
    monkeypatch.setattr(
        "apps.aggregator.tasks.refresh_tenant_fields", lambda t: refreshed.append(t.pk)
    )
    d = gbp_hours.pull_apply(tenant, CONFIG)
    tenant.refresh_from_db()
    assert tenant.opening_hours_structured == {
        "0": ["07:00", "15:00"],
        "2": ["10:00", "16:00"],  # день с потерями у Google — остаётся наш
        "4": ["09:00", "17:00"],
    }
    assert tenant.site_config == {"probe": 1}
    assert refreshed == [tenant.pk]
    assert d.lossy_days == {2}


# --- экран ---------------------------------------------------------------------------------


@pytest.fixture
def owner(django_user_model):
    from apps.core.models import Membership

    user = django_user_model.objects.create_user(username=f"o{uuid.uuid4().hex[:6]}", password="x")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    return user


@pytest.fixture
def channel():
    from apps.secrets import crypto

    return Channel.objects.create(
        type=Channel.GOOGLE_BUSINESS,
        is_enabled=True,
        config={"refresh_token": crypto.encrypt("rt"), "location": "accounts/1/locations/2"},
    )


def _req(user, data, tenant=None):
    request = RequestFactory().post("/dashboard/channels/google/zeiten/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant or TenantFactory.build(
        schema_name="t_gbph", opening_hours_structured=WEEK
    )
    return request


def test_preview_renders_diff_and_special_hours_read_only(owner, channel, api, isolated_ratelimit):
    api["periods"] = [_p("MONDAY", 9, 0, 18, 0)]
    api["special"] = 3
    resp = views.gbp_hours(_req(owner, {"action": "preview"}))
    html = resp.content.decode()
    assert resp.status_code == 200
    assert "data-hours-diff" in html
    assert "data-gbp-special" in html
    assert api["patched"] == []


def test_push_needs_confirm_then_records_state(owner, channel, api, isolated_ratelimit):
    api["periods"] = [_p("MONDAY", 8, 0, 12, 0), _p("MONDAY", 14, 0, 18, 0)]
    resp = views.gbp_hours(_req(owner, {"action": "push"}))
    assert api["patched"] == []
    assert 'name="confirm"' in resp.content.decode()
    isolated_ratelimit.clear()
    views.gbp_hours(_req(owner, {"action": "push", "confirm": "overwrite"}))
    assert len(api["patched"]) == 1
    channel.refresh_from_db()
    assert channel.config["gbp_sync"]["hours_pushed_at"]
    assert channel.config["refresh_token"]  # чужие ключи целы


def test_google_error_shows_code_no_500(owner, channel, monkeypatch, isolated_ratelimit):
    def boom(config):
        raise gbp.GbpError("not_approved", 403)

    monkeypatch.setattr(gbp, "access_token", boom)
    request = _req(owner, {"action": "preview"})
    resp = views.gbp_hours(request)
    assert resp.status_code == 200
    assert 'data-gbp-error="not_approved"' in resp.content.decode()


def test_hours_actions_rate_limited(owner, channel, api, isolated_ratelimit):
    for _ in range(gbp_hours.ACTION_LIMIT + 1):
        request = _req(owner, {"action": "preview"})
        views.gbp_hours(request)
    assert api["gets"] == gbp_hours.ACTION_LIMIT
    assert any("einen Moment" in str(m) for m in get_messages(request))


def test_unknown_action_and_get_rejected(owner, channel, api, isolated_ratelimit):
    request = RequestFactory().get("/dashboard/channels/google/zeiten/")
    request.user = owner
    assert views.gbp_hours(request).status_code == 405
    resp = views.gbp_hours(_req(owner, {"action": "nope"}))
    assert resp.status_code == 302 and api["gets"] == 0


def test_settings_shows_google_link_only_when_connected(owner, channel):
    from django.urls import reverse

    from apps.core import views as core_views

    request = RequestFactory().get("/dashboard/settings/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = owner
    request.tenant = TenantFactory.build(schema_name="t_gbph")
    html = core_views.settings_view(request).content.decode()
    assert reverse("gbp-sync") + "#zeiten" in html
    Channel.objects.filter(pk=channel.pk).update(config={})
    html = core_views.settings_view(request).content.decode()
    assert reverse("gbp-sync") + "#zeiten" not in html
