"""Д1-2 (T-8.10a): эндпоинты «Vorschlag aus dem Foto» и провод в ассистенте.

План — docs/d1-ai-photo-promo-today-plan-2026-10-17.md §7 (замки 1, 11–13)."""

import io
import json
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.test import RequestFactory
from PIL import Image

from apps.promotions import ai_draft, tasks, views
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_tenant")]


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="ki", password="pw12345678")


def _jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (80, 60), (120, 80, 40)).save(buf, "JPEG")
    return SimpleUploadedFile("brot.jpg", buf.getvalue(), content_type="image/jpeg")


def _req(method, path, user, data=None, tenant=None):
    rf = RequestFactory()
    request = rf.post(path, data or {}) if method == "post" else rf.get(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant or TenantFactory.build(business_type="bakery")
    return request


def _run_inline():
    return mock.patch.object(
        tasks.ai_photo_draft, "delay", side_effect=lambda **kw: tasks.ai_photo_draft(**kw)
    )


def _json(resp):
    return json.loads(resp.content)


def test_disabled_no_button_and_endpoint_says_disabled(settings, user):
    settings.AI_ENABLED = False
    html = views.promotion_quick(_req("get", "/promotions/schnell/", user)).content.decode()
    assert "data-ai-photo" not in html
    resp = views.promotion_quick_ai_start(
        _req("post", "/promotions/schnell/ki/", user, {"photo": _jpeg()})
    )
    assert _json(resp) == {"code": "disabled"}


def test_button_shown_when_enabled(ai_on, user):
    html = views.promotion_quick(_req("get", "/promotions/schnell/", user)).content.decode()
    assert "data-ai-photo" in html and 'name="ai_draft"' in html


def test_full_round_trip_and_photo_bytes_removed(ai_on, user, isolated_ratelimit):
    with _run_inline():
        start = _json(
            views.promotion_quick_ai_start(
                _req("post", "/promotions/schnell/ki/", user, {"photo": _jpeg(), "title": "Brot"})
            )
        )
    job = start["job"]
    raw = cache.get(ai_draft._job_key("public", user.pk, job))
    assert "photo" not in raw  # байты фото перезаписаны результатом
    state = _json(
        views.promotion_quick_ai_result(_req("get", f"/promotions/schnell/ki/{job}/", user), job)
    )
    assert state["state"] in ("done", "error")
    assert "photo" not in state and "hint" not in state


def test_photo_removed_even_when_provider_fails(ai_on, user, isolated_ratelimit):
    ai_on.AI_FAKE_MODE = "down"
    with _run_inline():
        job = _json(
            views.promotion_quick_ai_start(
                _req("post", "/promotions/schnell/ki/", user, {"photo": _jpeg()})
            )
        )["job"]
    raw = cache.get(ai_draft._job_key("public", user.pk, job))
    assert raw["state"] == "error" and "photo" not in raw


def test_other_users_job_is_404(ai_on, user, isolated_ratelimit):
    other = get_user_model().objects.create_user(username="fremd", password="pw12345678")
    with _run_inline():
        job = _json(
            views.promotion_quick_ai_start(
                _req("post", "/promotions/schnell/ki/", user, {"photo": _jpeg()})
            )
        )["job"]
    with pytest.raises(Http404):
        views.promotion_quick_ai_result(_req("get", "/x/", other), job)


def test_anonymous_redirected_and_get_on_start_405(ai_on):
    resp = views.promotion_quick_ai_start(_req("post", "/promotions/schnell/ki/", AnonymousUser()))
    assert resp.status_code == 302
    user = get_user_model().objects.create_user(username="ki2", password="pw12345678")
    assert views.promotion_quick_ai_start(_req("get", "/x/", user)).status_code == 405


def test_not_an_image_is_quiet_config_error(ai_on, user, isolated_ratelimit):
    fake_file = SimpleUploadedFile("x.jpg", b"%PDF-1.4 nope", content_type="image/jpeg")
    resp = views.promotion_quick_ai_start(
        _req("post", "/promotions/schnell/ki/", user, {"photo": fake_file})
    )
    assert _json(resp) == {"code": "config"}


def test_button_rate_limit_answers_quota(ai_on, user, isolated_ratelimit):
    with _run_inline():
        for _i in range(ai_draft.RATE_LIMIT):
            views.promotion_quick_ai_start(
                _req("post", "/promotions/schnell/ki/", user, {"photo": _jpeg()})
            )
        resp = views.promotion_quick_ai_start(
            _req("post", "/promotions/schnell/ki/", user, {"photo": _jpeg()})
        )
    assert _json(resp) == {"code": "quota"}


def test_saved_promotion_marks_ai_draft_only_when_flagged(settings, user):
    settings.AI_ENABLED = False
    tenant = TenantFactory(schema_name="ki_shop", slug="ki-shop", business_type="bakery")
    base = {
        "title": "Brot",
        "new_price": "2.50",
        "term": "week",
        "customer_response": "reserve",
        "publish": "draft",
    }
    views.promotion_quick(_req("post", "/promotions/schnell/", user, base, tenant=tenant))
    first = Promotion.objects.get()
    assert "ai_draft" not in (first.metadata or {})
    first.delete()
    views.promotion_quick(
        _req("post", "/promotions/schnell/", user, {**base, "ai_draft": "on"}, tenant=tenant)
    )
    assert Promotion.objects.get().metadata.get("ai_draft") is True


def test_default_term_preselected_by_business_type(settings, user):
    settings.AI_ENABLED = False
    html = views.promotion_quick(
        _req(
            "get", "/promotions/schnell/", user, tenant=TenantFactory.build(business_type="bakery")
        )
    ).content.decode()
    assert 'name="term" value="today" class="peer sr-only" checked' in html


def test_rate_limit_is_per_user_too(ai_on, user, isolated_ratelimit):
    other = get_user_model().objects.create_user(username="kollege", password="pw12345678")
    with _run_inline():
        for _i in range(ai_draft.RATE_LIMIT):
            views.promotion_quick_ai_start(
                _req("post", "/promotions/schnell/ki/", other, {"photo": _jpeg()})
            )
        resp = views.promotion_quick_ai_start(
            _req("post", "/promotions/schnell/ki/", user, {"photo": _jpeg()})
        )
    assert "job" in _json(resp)  # сотрудник не выбрал лимит владельца


def test_broker_down_is_quiet_and_photo_not_left_in_cache(ai_on, user, isolated_ratelimit):
    with (
        mock.patch.object(tasks.ai_photo_draft, "delay", side_effect=ConnectionError("x")),
        mock.patch.object(ai_draft.uuid, "uuid4") as uid,
        mock.patch.object(views, "_ai_schema", return_value="public"),
    ):
        uid.return_value.hex = "deadbeef"
        resp = views.promotion_quick_ai_start(
            _req("post", "/promotions/schnell/ki/", user, {"photo": _jpeg()})
        )
    assert _json(resp) == {"code": "unavailable"}
    assert cache.get(ai_draft._job_key("public", user.pk, "deadbeef")) is None
