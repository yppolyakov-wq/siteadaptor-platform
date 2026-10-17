"""Фикстуры ИИ-слоя: сеть запрещена, фейк чистый, ИИ включён на время теста."""

import pytest

from apps.ai.providers import fake


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Ни один тест apps/ai не ходит к провайдеру: HTTP-адаптеры проверяются через
    подменённый `http.post_json`/Stubber, иначе — фейк."""

    def _blocked(*args, **kwargs):
        raise AssertionError("network call in AI tests")

    monkeypatch.setattr("requests.sessions.Session.request", _blocked)
    monkeypatch.setattr("apps.ai.api._sleep", lambda attempt: None)
    fake.reset()
    yield
    fake.reset()


@pytest.fixture
def ai_on(settings):
    settings.AI_ENABLED = True
    settings.AI_REQUIRE_EU = False
    settings.AI_ROUTE_FAST = ["fake"]
    settings.AI_ROUTE_STRONG = ["fake"]
    settings.AI_FAKE_MODE = "ok"
    return settings
