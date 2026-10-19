"""pytest-django настройка для tenants-приложения.

django-tenants управляет схемами вручную: миграции каждой схемы запускаются
через `migrate_schemas`, а стандартная pytest-django fixture `db` ставит
только public-схему. Этого достаточно для тестов Tenant/Domain, которые
живут в public.

Тесты, которые реально создают tenant-схемы (`auto_create_schema=True`),
помечены `transaction=True` и сами зачищают за собой через
`DROP SCHEMA ... CASCADE`.
"""

import pytest


@pytest.fixture
def isolated_ratelimit(monkeypatch):
    """Счётчик лимита частоты — в приватном LocMem-кэше теста (xdist делит один Redis)."""
    import uuid

    from django.core.cache.backends.locmem import LocMemCache

    from apps.core import ratelimit

    store = LocMemCache(f"rl-test-tenants-{uuid.uuid4()}", {})
    monkeypatch.setattr(ratelimit, "cache", store)
    return store
