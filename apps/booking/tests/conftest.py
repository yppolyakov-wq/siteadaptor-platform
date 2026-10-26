"""Фикстуры тестов записи."""

import uuid

import pytest


@pytest.fixture(autouse=True)
def isolated_ratelimit(monkeypatch):
    """Счётчик лимита частоты — в приватном LocMem-кэше теста: xdist-воркеры делят
    один Redis, и счётчики IP вида 10.45.N.7 у разных воркеров совпадали → 429 вместо
    брони (флак test_e44b_variants_s2, 2026-10-26)."""
    from django.core.cache.backends.locmem import LocMemCache

    from apps.core import ratelimit

    store = LocMemCache(f"rl-test-booking-{uuid.uuid4()}", {})
    monkeypatch.setattr(ratelimit, "cache", store)
    return store
