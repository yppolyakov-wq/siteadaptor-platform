"""AIS W4-3 фаза 1: клиент Google Places — FieldMask, ключ только в заголовке, клампы,
маппинг дней, отказ на мусорный id без запроса (план ais-w4-3-google-profile-plan-2026-11-06)."""

from types import SimpleNamespace
from unittest import mock

import pytest
import requests

from apps.tenants import google_places as gp

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
