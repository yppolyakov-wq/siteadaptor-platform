"""AIS W4-3 фаза 1: клиент Google Places — FieldMask, ключ только в заголовке, клампы,
маппинг дней, отказ на мусорный id без запроса (план ais-w4-3-google-profile-plan-2026-11-06)."""

import uuid
from types import SimpleNamespace
from unittest import mock

import pytest
import requests
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.core import setup_google
from apps.tenants import google_places as gp
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

PID = "ChIJN1t_tDeuEmsRUsoyG83frY4"


def _resp(data, status=200):
    return SimpleNamespace(status_code=status, json=lambda: data)


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setattr(gp, "api_key", lambda: "SECRET-KEY")


def test_search_mask_key_header_and_clamps():
    data = {
        "places": [
            {
                "id": PID,
                "displayName": {"text": "<b>Bäckerei</b>" + "x" * 200},
                "formattedAddress": "Hauptstr. 1",
            },
            {"id": "bad id!", "displayName": {"text": "kaputt"}},
        ]
    }
    with mock.patch.object(gp.requests, "request", return_value=_resp(data)) as req:
        hits = gp.search_places("Bäckerei", "Hilden")
    args, kw = req.call_args
    assert args[:2] == ("POST", gp.SEARCH_URL)
    assert (
        kw["headers"]["X-Goog-FieldMask"] == "places.id,places.displayName,places.formattedAddress"
    )
    assert kw["headers"]["X-Goog-Api-Key"] == "SECRET-KEY"
    assert "SECRET-KEY" not in str(kw.get("json")) and kw["json"]["maxResultCount"] == 5
    assert [h.place_id for h in hits] == [PID] and len(hits[0].name) == 120


def test_details_mask_never_asks_for_photos():
    with mock.patch.object(gp.requests, "request", return_value=_resp({})) as req:
        gp.place_details(PID)
    mask = req.call_args.kwargs["headers"]["X-Goog-FieldMask"]
    assert "photo" not in mask and mask == gp.DETAILS_MASK


def test_bad_place_id_makes_no_request():
    with mock.patch.object(gp.requests, "request") as req, pytest.raises(gp.PlacesError):
        gp.place_details("../evil")
    req.assert_not_called()


def test_details_clean_values_and_hours_mapping():
    data = {
        "addressComponents": [
            {"longText": "Hauptstraße", "types": ["route"]},
            {"longText": "12", "types": ["street_number"]},
            {"longText": "40721", "types": ["postal_code"]},
            {"longText": "Hilden", "types": ["locality"]},
        ],
        "nationalPhoneNumber": "02103 12345",
        "websiteUri": "http://insecure.example",
        "regularOpeningHours": {
            "periods": [
                {
                    "open": {"day": 0, "hour": 9, "minute": 0},
                    "close": {"day": 0, "hour": 13, "minute": 0},
                },
                {
                    "open": {"day": 1, "hour": 7, "minute": 30},
                    "close": {"day": 1, "hour": 18, "minute": 0},
                },
                {
                    "open": {"day": 1, "hour": 19, "minute": 0},
                    "close": {"day": 1, "hour": 22, "minute": 0},
                },
                {
                    "open": {"day": 5, "hour": 22, "minute": 0},
                    "close": {"day": 6, "hour": 2, "minute": 0},
                },
            ]
        },
    }
    with mock.patch.object(gp.requests, "request", return_value=_resp(data)):
        got = gp.place_details(PID)
    assert got.address == "Hauptstraße 12, 40721 Hilden" and got.city == "Hilden"
    assert got.phone == "02103 12345" and got.website == ""  # только https
    assert got.hours == {"6": ["09:00", "13:00"], "0": ["07:30", "18:00"]}  # Sonntag → 6
    assert got.hours_partial  # второй интервал и ночная смена отброшены — «bitte prüfen»


def test_https_site_kept_and_credentials_dropped():
    for uri, want in (
        ("https://baeckerei.example/", "https://baeckerei.example/"),
        ("https://user:pw@evil.example/", ""),
        ("javascript:alert(1)", ""),
    ):
        with mock.patch.object(gp.requests, "request", return_value=_resp({"websiteUri": uri})):
            assert gp.place_details(PID).website == want


@pytest.mark.parametrize(
    "side",
    [requests.ConnectionError("boom"), None],
)
def test_errors_never_leak_the_key(side):
    kw = {"side_effect": side} if side else {"return_value": _resp({"error": "x"}, status=403)}
    with mock.patch.object(gp.requests, "request", **kw), pytest.raises(gp.PlacesError) as exc:
        gp.search_places("a", "b")
    assert "SECRET-KEY" not in str(exc.value)


def test_without_key_no_request(monkeypatch):
    monkeypatch.setattr(gp, "api_key", lambda: "")
    with mock.patch.object(gp.requests, "request") as req, pytest.raises(gp.PlacesError):
        gp.search_places("a", "b")
    req.assert_not_called()


# ── фаза 2: приёмник мастера — лимиты, кэш, применение только отмеченного ──


HOURS = {"0": ["08:00", "18:00"]}
DATA = gp.PlaceData(
    PID, address="Neue Str. 1, 40721 Hilden", city="Hilden", phone="02103 1", hours=HOURS
)


@pytest.fixture
def isolated(monkeypatch, settings):
    import django.core.cache as dj_cache
    from django.core.cache.backends.locmem import LocMemCache

    from apps.core import ratelimit

    settings.ROOT_URLCONF = "config.urls_tenant"
    local = LocMemCache(f"w43-{uuid.uuid4().hex}", {})
    monkeypatch.setattr(dj_cache, "cache", local)
    monkeypatch.setattr(ratelimit, "cache", local)
    return local


@pytest.fixture
def v4(db):
    return TenantFactory(
        schema_name="public",
        slug="w43",
        business_type="bakery",
        published_at=None,
        site_config={"onboarding": {"v": 2, "flow": "v4"}},
        address="Alte Str. 9",
        contact_phone="",
    )


def _post(tenant, data, user=None):
    request = RequestFactory().post("/dashboard/setup/google/", data, REMOTE_ADDR="10.0.0.1")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    if user is None:
        name = uuid.uuid4().hex[:8]
        user = get_user_model().objects.create_user(username=f"g-{name}", email=f"g-{name}@t.de")
    request.user = user
    return setup_google.setup_google(request), request


def _hit():
    return [gp.PlaceHit(PID, "Bäckerei", "Hilden")]


@pytest.mark.django_db
def test_flow_search_pick_apply_only_checked(isolated, v4):
    user = get_user_model().objects.create_user(username="g-own", email="g-own@t.de")
    with mock.patch.object(gp, "search_places", return_value=_hit()):
        _post(v4, {"action": "search", "g_name": "Bäckerei"}, user)
    with mock.patch.object(gp, "place_details", return_value=DATA):
        _post(v4, {"action": "pick", "place_id": PID}, user)
    resp, req = _post(
        v4, {"action": "apply", "g_field": ["phone", "hours"], "address": "evil"}, user
    )
    fresh = Tenant.objects.get(pk=v4.pk)
    assert resp.status_code == 302
    assert fresh.google_place_id == PID and fresh.contact_phone == "02103 1"
    assert fresh.opening_hours_structured == HOURS
    assert fresh.address == "Alte Str. 9"  # не отмечено — не тронуто (и POST-подделка игнор)


@pytest.mark.django_db
def test_prefilled_owner_field_is_unchecked(isolated, v4):
    user = get_user_model().objects.create_user(username="g-ck", email="g-ck@t.de")
    with mock.patch.object(gp, "search_places", return_value=_hit()):
        _post(v4, {"action": "search", "g_name": "Bäckerei"}, user)
    with mock.patch.object(gp, "place_details", return_value=DATA):
        _resp, req = _post(v4, {"action": "pick", "place_id": PID}, user)
    rows = {r["key"]: r for r in setup_google.context(req)["google_rows"]}
    assert rows["address"]["checked"] is False and rows["phone"]["checked"] is True


@pytest.mark.django_db
def test_pick_only_own_search_hits(isolated, v4):
    with mock.patch.object(gp, "place_details") as details:
        _post(v4, {"action": "pick", "place_id": PID})
    details.assert_not_called()


@pytest.mark.django_db
def test_apply_without_cache_writes_nothing(isolated, v4):
    _post(v4, {"action": "apply", "g_field": ["phone"]})
    assert Tenant.objects.get(pk=v4.pk).google_place_id == ""


@pytest.mark.django_db
def test_rate_limit_before_google_and_refund_on_error(isolated, v4):
    with mock.patch.object(gp, "search_places", side_effect=gp.PlacesError("http 500")) as s:
        for _ in range(setup_google.SEARCH_NET[0] + 2):
            _post(v4, {"action": "search", "g_name": "Bäckerei"})
    assert s.call_count == setup_google.SEARCH_NET[0] + 2  # сбой Google — попытки возвращены
    with mock.patch.object(gp, "search_places", return_value=[]) as s:
        for _ in range(setup_google.SEARCH_NET[0] + 2):
            _post(v4, {"action": "search", "g_name": "Bäckerei"})
    assert s.call_count == setup_google.SEARCH_NET[0]  # лимит — без запроса в Google


@pytest.mark.django_db
def test_without_key_no_block_and_404(isolated, v4, monkeypatch):
    monkeypatch.setattr(gp, "api_key", lambda: "")
    with pytest.raises(Http404):
        _post(v4, {"action": "search", "g_name": "x"})
    from apps.core import setup_google as sg

    assert sg.enabled(v4) is False


@pytest.mark.django_db
def test_hit_name_is_escaped_in_the_step(isolated, v4):
    from django.template.loader import render_to_string

    html = render_to_string(
        "tenant/setup/_google_profile.html",
        {"google_hits": [{"place_id": PID, "name": "<script>x</script>", "address": ""}]},
    )
    assert "<script>x</script>" not in html and "&lt;script&gt;" in html


@pytest.mark.django_db
def test_switching_place_clears_old_rating(isolated, v4):
    v4.google_place_id, v4.google_rating, v4.google_rating_count = "Other_place_123", 4.9, 300
    v4.save()
    user = get_user_model().objects.create_user(username="g-rt", email="g-rt@t.de")
    with mock.patch.object(gp, "search_places", return_value=_hit()):
        _post(v4, {"action": "search", "g_name": "Bäckerei"}, user)
    with mock.patch.object(gp, "place_details", return_value=DATA):
        _post(v4, {"action": "pick", "place_id": PID}, user)
    _post(v4, {"action": "apply", "g_field": ["phone"]}, user)
    fresh = Tenant.objects.get(pk=v4.pk)
    assert fresh.google_place_id == PID and fresh.google_rating is None


@pytest.mark.django_db
def test_nothing_checked_links_nothing(isolated, v4):
    user = get_user_model().objects.create_user(username="g-no", email="g-no@t.de")
    with mock.patch.object(gp, "search_places", return_value=_hit()):
        _post(v4, {"action": "search", "g_name": "Bäckerei"}, user)
    with mock.patch.object(gp, "place_details", return_value=DATA):
        _post(v4, {"action": "pick", "place_id": PID}, user)
    _post(v4, {"action": "apply"}, user)
    assert Tenant.objects.get(pk=v4.pk).google_place_id == ""


def test_overlong_website_is_dropped_not_truncated():
    uri = "https://shop.example/" + "a" * 300
    with mock.patch.object(gp.requests, "request", return_value=_resp({"websiteUri": uri})):
        assert gp.place_details(PID).website == ""


@pytest.mark.django_db
def test_unexpected_google_answer_refunds_and_does_not_500(isolated, v4):
    with mock.patch.object(gp, "search_places", side_effect=TypeError("odd json")):
        resp, _req = _post(v4, {"action": "search", "g_name": "Bäckerei"})
    assert resp.status_code == 302
    from django.db import connection

    from apps.core import ratelimit

    assert not ratelimit.hit("gplaces-search-t", connection.schema_name, limit=1, window=60)
