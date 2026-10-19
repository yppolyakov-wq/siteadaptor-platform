"""Фикстуры тестов агрегатора."""

import uuid

import pytest
from django.core.cache.backends.locmem import LocMemCache


@pytest.fixture
def isolated_ratelimit(monkeypatch):
    """Счётчик лимита частоты — в приватном LocMem-кэше теста.

    CI гоняет тесты параллельно (`-n auto`) на ОДНОМ Redis, а десятки тестов
    зовут `cache.clear()`: чужой воркер мог обнулить ключ `rl:*` между
    запросами, и тест видел 200 вместо 429 (CI #2683). Изоляция снимает гонку.
    """
    from apps.core import ratelimit

    # имя уникально: LocMem с одинаковым именем делит одно хранилище между тестами
    store = LocMemCache(f"rl-test-aggregator-{uuid.uuid4()}", {})
    monkeypatch.setattr(ratelimit, "cache", store)
    return store
