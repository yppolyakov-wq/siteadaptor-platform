"""Общие фикстуры всех тестов."""

import pytest


@pytest.fixture(autouse=True)
def _fresh_ai_config_cache():
    """AI-CFG: кэш настроек ИИ живёт в процессе и пережил бы откат БД между тестами."""
    from apps.ai import config

    config.reset_cache()
    yield
    config.reset_cache()


@pytest.fixture(autouse=True)
def _no_hidden_schema_creation(monkeypatch):
    """Тенант из фабрики без схемы не получает её «по дороге».

    Перечитанный из БД тенант снова несёт auto_create_schema=True (атрибут класса),
    и любой его save() создавал схему всеми миграциями. Схема нужна тесту — фабрика
    с auto_create_schema=True, такие имена сюда не попадают.
    """
    from django.db import connection

    from apps.tenants.models import Tenant
    from apps.tenants.tests import factories

    # Раньше connection.tenant «случайно» выставлял скрытый create_schema соседнего
    # теста; теперь его нет — задаём то же состояние явно (public, как после него).
    if not hasattr(connection, "tenant"):
        connection.set_schema_to_public()

    original = Tenant.create_schema

    def create_schema(self, *args, **kwargs):
        if self.schema_name in factories.SCHEMALESS:
            # Конечное состояние соединения — как после настоящего create_schema
            # (он заканчивается на public): часть кода читает connection.tenant.
            from django.db import connection

            connection.set_schema_to_public()
            return False
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Tenant, "create_schema", create_schema)
    yield
    factories.SCHEMALESS.clear()
