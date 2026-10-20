"""Фикстуры тестов общего бота платформы."""

import pytest


@pytest.fixture(autouse=True)
def isolated_ratelimit(monkeypatch):
    """Счётчик лимита частоты — в приватном LocMem-кэше теста (xdist делит один Redis)."""
    import uuid

    from django.core.cache.backends.locmem import LocMemCache

    from apps.core import ratelimit

    store = LocMemCache(f"rl-test-platform-bot-{uuid.uuid4()}", {})
    monkeypatch.setattr(ratelimit, "cache", store)
    return store


@pytest.fixture(autouse=True)
def _schemas_exist(monkeypatch):
    """Тенанты фабрики без схем: links.bind() сохраняет Tenant, и django-tenants иначе
    создавал бы схему с полными миграциями (минуты на тест). В проде схема есть всегда."""
    monkeypatch.setattr("django_tenants.models.schema_exists", lambda name: True)


@pytest.fixture(autouse=True)
def _fresh_bot_config():
    """Настройки бота кэшируются в процессе — тест не должен видеть значения соседа
    (строки PlatformSecret откатываются, а кэш нет)."""
    from apps.platform_bot import config

    config.reset_cache()
    yield
    config.reset_cache()
