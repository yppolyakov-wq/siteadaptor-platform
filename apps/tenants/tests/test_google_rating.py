"""GK-11: Google-рейтинг (Places API) — сервис, beat, кабинет, витрина.

Кэш на Tenant (targeted update_fields); без ключа фича молчит; ошибка одного
тенанта не роняет beat-проход; витрина рендерит только при кэше."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.utils import timezone

from apps.tenants import google_places, tasks
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_fetch_rating_requires_key(settings):
    settings.GOOGLE_PLACES_API_KEY = ""
    with pytest.raises(RuntimeError):
        google_places.fetch_rating("ChIJtest")


def test_fetch_rating_parses_response(settings, monkeypatch):
    settings.GOOGLE_PLACES_API_KEY = "k"
    seen = {}

    def _get(url, headers=None, timeout=None):
        seen["url"] = url
        seen["mask"] = headers["X-Goog-FieldMask"]
        return _Resp({"rating": 4.9, "userRatingCount": 11})

    monkeypatch.setattr(google_places.requests, "get", _get)
    assert google_places.fetch_rating("ChIJ test/id") == (4.9, 11)
    assert "ChIJ%20test%2Fid" in seen["url"]  # place_id квотится в path
    assert seen["mask"] == "rating,userRatingCount"


def test_beat_refreshes_stale_and_survives_errors(settings, monkeypatch):
    settings.GOOGLE_PLACES_API_KEY = "k"
    fresh = TenantFactory(
        google_place_id="ChIJfresh",
        google_rating=Decimal("4.10"),
        google_rating_updated_at=timezone.now(),
    )
    stale = TenantFactory(
        google_place_id="ChIJstale",
        google_rating_updated_at=timezone.now() - timedelta(days=30),
    )
    broken = TenantFactory(
        google_place_id="ChIJbroken",
        google_rating_updated_at=None,
    )
    TenantFactory(google_place_id="")  # без ID — вне выборки

    def _fetch(place_id):
        if place_id == "ChIJbroken":
            raise RuntimeError("quota")
        return 4.9, 11

    monkeypatch.setattr(google_places, "fetch_rating", _fetch)
    assert tasks.refresh_google_ratings() == 1  # только stale; broken не уронил проход

    stale.refresh_from_db()
    assert stale.google_rating == Decimal("4.9") and stale.google_rating_count == 11
    fresh.refresh_from_db()
    assert fresh.google_rating == Decimal("4.10")  # свежий кэш не трогали
    broken.refresh_from_db()
    assert broken.google_rating is None  # ошибка — кэш прежний


def test_beat_silent_without_key(settings):
    settings.GOOGLE_PLACES_API_KEY = ""
    TenantFactory(google_place_id="ChIJx")
    assert tasks.refresh_google_ratings() == 0


def _trust_html(tenant):
    req = RequestFactory().get("/")
    req.tenant = tenant
    return render_to_string(
        "storefront/sections/_trust.html",
        {
            "request": req,
            "site": {"trust": {"since": "", "marks": []}, "testimonials": []},
            "section_row": {"key": "trust", "style": ""},
        },
    )


def test_trust_band_shows_google_rating_only_when_cached():
    with_google = TenantFactory.build(google_rating=Decimal("4.90"), google_rating_count=11)
    html = _trust_html(with_google)
    assert "4,90" in html or "4.90" in html
    assert "Google-Bewertung" in html
    assert _trust_html(TenantFactory.build()).strip() == ""  # без кэша секция пуста
