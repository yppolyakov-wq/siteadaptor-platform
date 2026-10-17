"""Фикстуры тестов акций: ИИ (Д1) — только фейк, сети нет."""

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
    yield settings
    fake.reset()
