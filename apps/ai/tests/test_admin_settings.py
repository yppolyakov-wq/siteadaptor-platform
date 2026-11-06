"""AI-CFG-2: экран «KI-Einstellungen» в админке платформы (только суперпользователь)."""

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, override_settings

from apps.ai import config
from apps.ai.admin import AIUsageAdmin
from apps.ai.models import AIConfig, AIUsage
from apps.audit.models import AuditEvent

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _public(settings):
    settings.ROOT_URLCONF = "config.urls_public"
    config.reset_cache()
    yield
    config.reset_cache()


def _req(method="get", data=None, superuser=True):
    user = get_user_model().objects.create_user(
        username=f"ai-{superuser}-{method}", password="pw12345678", is_staff=True
    )
    user.is_superuser = superuser
    user.save()
    req = getattr(RequestFactory(), method)("/admin/ai/aiusage/einstellungen/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    req._messages = FallbackStorage(req)
    req.user = user
    req._dont_enforce_csrf_checks = True
    return req


def _view():
    return AIUsageAdmin(AIUsage, site).settings_view


def test_screen_is_superuser_only_and_renders():
    with pytest.raises(PermissionDenied):
        _view()(_req(superuser=False))
    resp = _view()(_req())
    resp.render()
    html = resp.content.decode()
    assert "data-ai-settings" in html and "search_phrase_filters" in html


@override_settings(
    AI_ENABLED=False, AI_REQUIRE_EU=False, ANTHROPIC_MODEL_FAST="", ANTHROPIC_MODEL_STRONG=""
)
def test_save_writes_admin_values_and_audit():
    data = {
        "AI_ENABLED": "1",
        "AI_ROUTE_FAST_0": "anthropic",
        "AI_ROUTE_STRONG_0": "anthropic",
        "ANTHROPIC_MODEL_FAST": "claude-haiku-5-5",
        "ANTHROPIC_MODEL_STRONG": "claude-sonnet-5-5",
        "tasks_custom": "on",
        "tasks": ["promo_text_check"],
        "AI_PRICES": "claude-haiku-5-5 10 50\nclaude-sonnet-5-5 200 1000",
    }
    resp = _view()(_req("post", data))
    assert resp.status_code == 302
    values = AIConfig.objects.get(pk=1).values
    assert values["AI_ENABLED"] is True and values["AI_ROUTE_FAST"] == ["anthropic"]
    assert values["AI_TASKS_ENABLED"] == ["promo_text_check"]
    assert values["AI_PRICES"]["claude-haiku-5-5"] == [10, 50]
    assert "AI_SEARCH_ENABLED" not in values  # пусто = как .env
    assert AuditEvent.objects.filter(action="ai.config.changed").exists()
    from apps.ai import api

    assert api.is_enabled("promo_text_check")


@override_settings(AI_REQUIRE_EU=False, ANTHROPIC_MODEL_FAST="m", ANTHROPIC_MODEL_STRONG="m")
def test_non_eu_route_with_eu_only_is_refused():
    data = {
        "AI_ENABLED": "1",
        "AI_REQUIRE_EU": "1",
        "AI_ROUTE_FAST_0": "anthropic",
        "AI_ROUTE_STRONG_0": "anthropic",
    }
    _view()(_req("post", data))
    assert not AIConfig.objects.filter(pk=1).exists()


def test_unknown_task_is_refused():
    _view()(_req("post", {"tasks_custom": "on", "tasks": ["delete_everything"]}))
    assert not AIConfig.objects.filter(pk=1).exists()


def test_real_admin_url_resolves():
    from django.urls import resolve, reverse

    url = reverse("admin:ai_settings", urlconf="config.urls_public")
    view = resolve(url, urlconf="config.urls_public").func
    with pytest.raises(PermissionDenied):
        view(_req(superuser=False))
    assert view(_req()).status_code == 200


_TASKS_ENV = {
    "AI_ENABLED": False,
    "AI_REQUIRE_EU": False,
    "AI_ROUTE_FAST": ["anthropic"],
    "AI_ROUTE_STRONG": ["anthropic"],
    "ANTHROPIC_MODEL_FAST": "m",
    "ANTHROPIC_MODEL_STRONG": "m",
    "AI_TASKS_ENABLED": ["promo_text_check"],
}


# Фидбэк владельца 2026-11-06: «ставлю галочки задач — не применяются». Галочки
# учитывались только при переключателе «Aufgaben hier festlegen»; без него Save молча
# оставлял `.env`. Изменённый набор теперь сам становится своим списком.
@override_settings(**_TASKS_ENV)
def test_changed_task_boxes_apply_without_custom_toggle():
    data = {"tasks_present": "1", "tasks": ["promo_text_check", "assistant_answer"]}
    resp = _view()(_req("post", data))
    assert resp.status_code == 302
    values = AIConfig.objects.get(pk=1).values
    assert values["AI_TASKS_ENABLED"] == ["promo_text_check", "assistant_answer"]


@override_settings(**_TASKS_ENV)
def test_unchanged_task_boxes_keep_following_env():
    _view()(_req("post", {"tasks_present": "1", "tasks": ["promo_text_check"]}))
    assert "AI_TASKS_ENABLED" not in AIConfig.objects.get(pk=1).values


@override_settings(**_TASKS_ENV)
def test_unticking_custom_toggle_returns_to_env():
    from apps.ai import config

    config.save({"AI_TASKS_ENABLED": ["assistant_answer"]})
    data = {"tasks_present": "1", "tasks_was_custom": "1", "tasks": ["assistant_answer"]}
    _view()(_req("post", data))
    assert "AI_TASKS_ENABLED" not in AIConfig.objects.get(pk=1).values


def test_screen_marks_task_boxes_for_auto_toggle():
    resp = _view()(_req())
    resp.render()
    html = resp.content.decode()
    assert 'name="tasks_present"' in html and "data-ai-task " in html
