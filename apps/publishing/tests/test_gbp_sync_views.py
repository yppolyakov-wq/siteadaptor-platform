"""Д3-1 (GBP-Sync): клиент Google, выбор локации, экран «Google-Profil».

План — docs/d3-gbp-sync-plan-2026-10-18.md §7–§9 (замки 24–26 + X7). Живого API до
одобрения Google нет — все обмены с Google застаблены."""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from apps.publishing import gbp, views
from apps.publishing.models import Channel
from apps.tenants.tests.factories import TenantFactory

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_tenant")]

SECRET_RT = "1//refresh-SECRET-xyz"
SECRET_AT = "ya29.access-SECRET-abc"


class _Resp:
    def __init__(self, data=None, status=200):
        self._data = data if data is not None else {}
        self.status_code = status

    def json(self):
        return self._data


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
        config={"refresh_token": crypto.encrypt(SECRET_RT)},
    )


def _req(method, path, user, data=None):
    rf = RequestFactory()
    request = rf.post(path, data or {}) if method == "post" else rf.get(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = TenantFactory.build(schema_name="t_gbp", business_type="bakery")
    return request


@pytest.fixture
def google(monkeypatch):
    """Подмена Google: токен, аккаунты, локации. `state['status']` — ответ API."""
    state = {"status": 200, "calls": []}

    def _post(url, **kw):
        state["calls"].append(("POST", url))
        return _Resp({"access_token": SECRET_AT})

    def _get(url, **kw):
        state["calls"].append(("GET", url))
        if state["status"] != 200:
            return _Resp({"error": {"message": f"echo {SECRET_AT}"}}, state["status"])
        if url == gbp.ACCOUNTS_URL:
            return _Resp({"accounts": [{"name": "accounts/11", "accountName": "Bäckerei"}]})
        return _Resp(
            {
                "locations": [
                    {
                        "name": "locations/22",
                        "title": "Filiale <b>Mitte</b>",
                        "storefrontAddress": {
                            "addressLines": ["Hauptstr. 1"],
                            "locality": "Solingen",
                        },
                    }
                ]
            }
        )

    monkeypatch.setattr(gbp.requests, "post", _post)
    monkeypatch.setattr(gbp.requests, "get", _get)
    return state


# --- клиент --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "auth"),
        (403, "not_approved"),
        (404, "not_found"),
        (429, "quota"),
        (500, "bad_response"),
    ],
)
def test_client_maps_http_errors(google, status, code):
    google["status"] = status
    with pytest.raises(gbp.GbpError) as exc:
        gbp.all_locations({"refresh_token": "rt"})
    assert exc.value.code == code and exc.value.status == status


def test_location_ids_validates_and_derives_v1():
    assert gbp.location_ids({"location": "accounts/1/locations/2"}) == (
        "accounts/1/locations/2",
        "locations/2",
    )
    for bad in (
        "",
        "locations/2",
        "accounts/1/locations/2/../3",
        "https://x/accounts/1/locations/2",
    ):
        with pytest.raises(gbp.GbpError):
            gbp.location_ids({"location": bad})


def test_all_locations_builds_v4_names(google):
    (loc,) = gbp.all_locations({"refresh_token": "rt"})
    assert loc["name"] == "accounts/11/locations/22"
    assert loc["account"] == "Bäckerei"
    assert "Solingen" in loc["address"]


def test_missing_refresh_token_is_not_configured_without_http(google):
    with pytest.raises(gbp.GbpError) as exc:
        gbp.access_token({})
    assert exc.value.code == "not_configured"
    assert google["calls"] == []


# --- экран и выбор локации -----------------------------------------------------------------


def test_urls_routed():
    assert reverse("gbp-sync") == "/dashboard/channels/google/"
    assert reverse("gbp-location") == "/dashboard/channels/google/standort/"


def test_screen_renders_not_connected(owner):
    resp = views.gbp_sync(_req("get", "/dashboard/channels/google/", owner))
    assert resp.status_code == 200
    assert reverse("channel-oauth-start", args=["google_business"]) in resp.content.decode()


def test_load_locations_lists_them_escaped(owner, channel, google, isolated_ratelimit):
    resp = views.gbp_sync(_req("post", "/dashboard/channels/google/", owner, {"action": "load"}))
    html = resp.content.decode()
    assert resp.status_code == 200
    assert 'value="accounts/11/locations/22"' in html
    assert "<b>Mitte</b>" not in html  # внешний текст экранируется


def test_not_approved_shows_hint_and_changes_nothing(owner, channel, google, isolated_ratelimit):
    google["status"] = 403
    before = dict(channel.config)
    resp = views.gbp_sync(_req("post", "/dashboard/channels/google/", owner, {"action": "load"}))
    assert resp.status_code == 200
    assert "noch nicht freigeschaltet" in resp.content.decode()
    channel.refresh_from_db()
    assert channel.config.get("location") == before.get("location")
    assert channel.config["gbp_sync"]["last_error_code"] == "not_approved"


def test_tokens_never_leak(owner, channel, google, isolated_ratelimit, caplog):
    caplog.set_level("DEBUG")
    google["status"] = 500
    resp = views.gbp_sync(_req("post", "/dashboard/channels/google/", owner, {"action": "load"}))
    channel.refresh_from_db()
    blob = resp.content.decode() + caplog.text + repr(channel.config.get("gbp_sync"))
    assert SECRET_AT not in blob and SECRET_RT not in blob


def test_save_location_validates(owner, channel):
    views.gbp_location(
        _req(
            "post",
            "/dashboard/channels/google/standort/",
            owner,
            {"location": "accounts/11/locations/22"},
        )
    )
    channel.refresh_from_db()
    assert channel.config["location"] == "accounts/11/locations/22"
    views.gbp_location(
        _req("post", "/dashboard/channels/google/standort/", owner, {"location": "https://evil/x"})
    )
    channel.refresh_from_db()
    assert channel.config["location"] == "accounts/11/locations/22"


def test_save_location_keeps_other_config(owner, channel):
    views.gbp_location(_req("post", "/", owner, {"location": "accounts/11/locations/22"}))
    channel.refresh_from_db()
    assert channel.config["refresh_token"]  # токен не стёрт


def test_load_rate_limited(owner, channel, google, isolated_ratelimit, settings):
    for _ in range(2):
        views.gbp_sync(_req("post", "/dashboard/channels/google/", owner, {"action": "load"}))
    gets = [c for c in google["calls"] if c[0] == "GET"]
    assert len(gets) == 2  # второй клик в ту же минуту в Google не идёт


def test_anonymous_redirected_and_get_on_action_405(owner):
    anon = views.gbp_sync(_req("get", "/dashboard/channels/google/", AnonymousUser()))
    assert anon.status_code == 302
    assert (
        views.gbp_location(_req("get", "/dashboard/channels/google/standort/", owner)).status_code
        == 405
    )


# --- доступ только владельцу (В-7) ---------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/dashboard/channels/google/",
        "/dashboard/channels/google/standort/",
        "/dashboard/channels/config/",
        "/dashboard/channels/connect/google_business/",
    ],
)
def test_staff_blocked_by_middleware(django_user_model, path):
    from apps.core.middleware import CabinetOwnerAccessMiddleware
    from apps.core.models import Membership

    staff = django_user_model.objects.create_user(username=f"s{uuid.uuid4().hex[:6]}", password="x")
    Membership.objects.create(user=staff, role=Membership.ROLE_STAFF)
    request = RequestFactory().get(path)
    request.user = staff
    request.tenant = TenantFactory.build(schema_name="t_gbp")
    resp = CabinetOwnerAccessMiddleware(lambda r: HttpResponse("ok"))(request)
    assert resp.status_code == 403


# --- входы ---------------------------------------------------------------------------------


def test_nav_registry_has_entry():
    from apps.core.nav_registry import ENTRIES

    entry = next(e for e in ENTRIES if e.url_name == "gbp-sync")
    assert entry.owner_only and entry.palette_only


def test_channels_page_links_to_sync(owner):
    html = views.channels(_req("get", "/dashboard/channels/", owner)).content.decode()
    assert reverse("gbp-sync") in html
