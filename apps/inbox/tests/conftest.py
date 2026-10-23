"""Фикстуры тестов inbox: ИИ (T-8.10g) — только фейк, сети нет."""

import pytest

from apps.ai.providers import fake


@pytest.fixture
def ai_on(settings, monkeypatch):
    """ИИ включён на фейковом маршруте; любой HTTP-вызов — провал теста."""

    def _blocked(*args, **kwargs):
        raise AssertionError("network call in AI tests")

    monkeypatch.setattr("requests.sessions.Session.request", _blocked)
    monkeypatch.setattr("apps.ai.api._sleep", lambda attempt: None)
    fake.reset()
    settings.AI_ENABLED = True
    settings.AI_REQUIRE_EU = False
    settings.AI_ROUTE_FAST = ["fake"]
    settings.AI_ROUTE_STRONG = ["fake"]
    settings.AI_FAKE_MODE = "ok"
    # AI-1: переписка с клиентом выключена по умолчанию — тесты задачи включают её явно.
    settings.AI_TASKS_ENABLED = [*settings.AI_TASKS_ENABLED, "inbox_reply_draft"]
    yield settings
    fake.reset()


@pytest.fixture
def isolated_ratelimit(monkeypatch):
    """Счётчик лимита частоты — в приватном LocMem-кэше теста (xdist делит один Redis)."""
    from django.core.cache.backends.locmem import LocMemCache

    from apps.core import ratelimit

    store = LocMemCache("rl-test-inbox", {})
    monkeypatch.setattr(ratelimit, "cache", store)
    return store


@pytest.fixture
def ai_cache(monkeypatch):
    """Кэш задач/черновиков ИИ — приватный LocMem: `cache.clear()` общего Redis под
    xdist стирал бы задачи соседних тестов."""
    from django.core.cache.backends.locmem import LocMemCache

    from apps.inbox import ai_reply

    store = LocMemCache(f"ai-reply-test-{id(monkeypatch)}", {})
    monkeypatch.setattr(ai_reply, "cache", store)
    return store
