"""Фикстуры тестов публикации."""

import uuid

import pytest


@pytest.fixture
def isolated_ratelimit(monkeypatch):
    """Счётчик лимита частоты — в приватном LocMem-кэше теста (xdist делит один Redis)."""
    from django.core.cache.backends.locmem import LocMemCache

    from apps.core import ratelimit

    store = LocMemCache(f"rl-test-publishing-{uuid.uuid4()}", {})
    monkeypatch.setattr(ratelimit, "cache", store)
    return store
