"""Д3-1 (GBP-Sync): клиент Google, выбор локации, экран «Google-Profil».

План — docs/d3-gbp-sync-plan-2026-10-18.md §7–§9 (замки 24–26 + X7). Живого API до
одобрения Google нет — все обмены с Google застаблены."""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
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
def google(monkeypatch, settings):
    """Подмена Google: токен, аккаунты, локации. `state['status']` — ответ API;
    `state['accounts']`/`state['locations']` — подмена тела ответа."""
    settings.GOOGLE_OAUTH_CLIENT_ID = "cid"
    settings.GOOGLE_OAUTH_CLIENT_SECRET = "csecret"
    state = {"status": 200, "token_status": 200, "calls": [], "posted": []}

    def _post(url, **kw):
        state["calls"].append(("POST", url))
        state["posted"].append(kw.get("data") or {})
        if state["token_status"] != 200:
            return _Resp({"error": f"echo {SECRET_RT}"}, state["token_status"])
        return _Resp({"access_token": SECRET_AT})

    def _get(url, **kw):
        state["calls"].append(("GET", url))
        if state["status"] != 200:
            return _Resp({"error": {"message": f"echo {SECRET_AT}"}}, state["status"])
        if url == gbp.ACCOUNTS_URL:
            if "accounts" in state:
                return _Resp(state["accounts"])
            return _Resp({"accounts": [{"name": "accounts/11", "accountName": "Bäckerei"}]})
        if "locations" in state:
            body = state["locations"]
            return _Resp(body(url, kw) if callable(body) else body)
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


def test_missing_platform_client_is_not_configured_without_http(google, settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = ""
    with pytest.raises(gbp.GbpError) as exc:
        gbp.access_token({"refresh_token": "rt"})
    assert exc.value.code == "not_configured"
    assert google["calls"] == []


def test_undecryptable_refresh_token_is_not_sent(google):
    # Шифротекст, который decrypted_config не смог расшифровать (сменили ключ).
    with pytest.raises(gbp.GbpError) as exc:
        gbp.access_token({"refresh_token": "gAAAAABlegacy-ciphertext"})
    assert exc.value.code == "not_configured"
    assert google["calls"] == []


@pytest.mark.parametrize(
    "accounts,locations",
    [
        ({"accounts": "oops"}, None),
        ({"accounts": {"name": "accounts/1"}}, None),
        (None, {"locations": "oops"}),
        (None, {"locations": [{"name": "locations/2", "storefrontAddress": {"addressLines": 7}}]}),
        (None, {"locations": [{"name": "locations/2", "storefrontAddress": "x"}]}),
        (None, {"locations": [None, 5, "x"]}),
    ],
)
def test_malformed_google_json_never_crashes(google, accounts, locations):
    if accounts is not None:
        google["accounts"] = accounts
    if locations is not None:
        google["locations"] = locations
    result = gbp.all_locations({"refresh_token": "rt"})
    assert isinstance(result, list)


@pytest.mark.parametrize(
    "value",
    [
        "accounts/1/locations/2\nx",
        "accounts/\u0661/locations/2",
        "accounts/1/locations/\u0662",
        "accounts/1/locations/2x",
    ],
)
def test_location_regex_is_strict_ascii(value):
    with pytest.raises(gbp.GbpError):
        gbp.location_ids({"location": value})


def test_location_rows_with_non_ascii_digits_skipped(google):
    google["locations"] = {"locations": [{"name": "locations/\u0662", "title": "x"}]}
    assert gbp.all_locations({"refresh_token": "rt"}) == []


def test_locations_follow_next_page_token(google):
    def body(url, kw):
        if kw.get("params", {}).get("pageToken") == "p2":
            return {"locations": [{"name": "locations/3", "title": "B"}]}
        return {"locations": [{"name": "locations/2", "title": "A"}], "nextPageToken": "p2"}

    google["locations"] = body
    names = [loc["name"] for loc in gbp.all_locations({"refresh_token": "rt"})]
    assert names == ["accounts/11/locations/2", "accounts/11/locations/3"]


def test_one_failing_account_does_not_hide_the_others(google, monkeypatch):
    google["accounts"] = {
        "accounts": [{"name": "accounts/1"}, {"name": "accounts/2", "accountName": "Zwei"}]
    }
    real_get = gbp.requests.get

    def _get(url, **kw):
        if url.endswith("accounts/1/locations"):
            google["calls"].append(("GET", url))
            return _Resp({}, 403)
        return real_get(url, **kw)

    monkeypatch.setattr(gbp.requests, "get", _get)
    (loc,) = gbp.all_locations({"refresh_token": "rt"})
    assert loc["account"] == "Zwei"


def test_token_endpoint_error_never_leaks_refresh_token(owner, channel, google, isolated_ratelimit):
    google["token_status"] = 400
    resp = views.gbp_sync(_req("post", "/dashboard/channels/google/", owner, {"action": "load"}))
    channel.refresh_from_db()
    blob = resp.content.decode() + repr(channel.config.get("gbp_sync"))
    assert SECRET_RT not in blob
    assert channel.config["gbp_sync"]["last_error_code"] == "auth"
    assert google["posted"][0]["refresh_token"] == SECRET_RT  # расшифрован только в запросе


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
    assert channel.config["refresh_token"] == before["refresh_token"]
    assert "location" not in channel.config
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


def test_load_rate_limited(owner, channel, google, isolated_ratelimit):
    views.gbp_sync(_req("post", "/dashboard/channels/google/", owner, {"action": "load"}))
    request = _req("post", "/dashboard/channels/google/", owner, {"action": "load"})
    views.gbp_sync(request)
    gets = [c for c in google["calls"] if c[0] == "GET"]
    assert len(gets) == 2  # второй клик в ту же минуту в Google не идёт
    from django.contrib.messages import get_messages

    assert any("einen Moment" in str(m) for m in get_messages(request))


def test_rate_limited_hides_stale_error_banner(owner, channel, google, isolated_ratelimit):
    google["status"] = 403
    views.gbp_sync(_req("post", "/dashboard/channels/google/", owner, {"action": "load"}))
    resp = views.gbp_sync(_req("post", "/dashboard/channels/google/", owner, {"action": "load"}))
    assert "data-gbp-error" not in resp.content.decode()


def test_success_clears_last_status(owner, channel, google, isolated_ratelimit):
    google["status"] = 403
    views.gbp_sync(_req("post", "/dashboard/channels/google/", owner, {"action": "load"}))
    google["status"] = 200
    isolated_ratelimit.clear()
    views.gbp_sync(_req("post", "/dashboard/channels/google/", owner, {"action": "load"}))
    channel.refresh_from_db()
    state = channel.config["gbp_sync"]
    assert state["last_error_code"] == "" and not state["last_status"]


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
        "/dashboard/channels/toggle/",
    ],
)
def test_staff_blocked_by_middleware(django_user_model, path):
    from apps.core.models import Membership

    staff = django_user_model.objects.create_user(username=f"s{uuid.uuid4().hex[:6]}", password="x")
    Membership.objects.create(user=staff, role=Membership.ROLE_STAFF)
    request = RequestFactory().get(path)
    request.user = staff
    request.tenant = TenantFactory.build(schema_name="t_gbp")
    from apps.core.tests.gates import ok, open_as

    resp = open_as(request, ok)
    assert resp.status_code == 403


# --- входы ---------------------------------------------------------------------------------


def test_nav_registry_has_entry():
    from apps.core import view_perms
    from apps.core.nav_registry import ENTRIES

    entry = next(e for e in ENTRIES if e.url_name == "gbp-sync")
    assert entry.palette_only  # E6.7e: скрытие у сотрудника — из права kanaele.edit
    assert view_perms.rule_for("gbp-sync").read == "kanaele.edit"
    assert entry.nav_key == "channels"


def test_config_writers_keep_each_others_keys(channel):
    """M2: все писатели конфига идут через блокирующий merge — чужие ключи целы."""
    from apps.publishing import oauth

    Channel.update_config(channel.pk, lambda c: c.__setitem__("location", "accounts/1/locations/2"))
    oauth.store_token(Channel.GOOGLE_BUSINESS, "public", "new-token")
    channel.refresh_from_db()
    assert channel.config["location"] == "accounts/1/locations/2"
    assert channel.config["refresh_token"] != SECRET_RT  # перезаписан, но зашифрован


def test_staff_sees_channels_read_only(django_user_model):
    from apps.core.models import Membership

    staff = django_user_model.objects.create_user(username=f"s{uuid.uuid4().hex[:6]}", password="x")
    Membership.objects.create(user=staff, role=Membership.ROLE_STAFF)
    html = views.channels(_req("get", "/dashboard/channels/", staff)).content.decode()
    assert "data-channels-readonly" in html
    assert reverse("channel-oauth-start", args=["google_business"]) not in html


def test_channels_page_links_to_sync(owner):
    html = views.channels(_req("get", "/dashboard/channels/", owner)).content.decode()
    assert reverse("gbp-sync") in html
