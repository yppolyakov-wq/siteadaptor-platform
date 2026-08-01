"""Сверка миграций по всем схемам (2026-08-01).

Повод — аудит того же дня: очередь миграций в памяти проекта разъехалась с
реальностью, потому что обычный `showmigrations` видит только public-схему.
"""

from io import StringIO

import pytest
from django.core.management import call_command

from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _run(*args) -> str:
    out = StringIO()
    call_command("migration_state", *args, stdout=out)
    return out.getvalue()


def test_reports_clean_state_on_migrated_database():
    """Тест-БД мигрирована целиком → команда обязана молчать про отставание."""
    body = _run()
    assert "Всё применено" in body
    assert "не применена" not in body


def test_tenant_row_without_schema_is_named_missing_not_pending():
    """Строка Tenant без схемы (провалившийся провижининг) — отдельный диагноз.

    Сказать про неё «миграции не применены» значило бы отправить владельца
    гонять migrate там, где чинить надо провижининг.
    """
    tenant = TenantFactory()  # auto_create_schema=False — схемы в Postgres нет
    body = _run()
    assert "СХЕМЫ ОТСУТСТВУЮТ" in body
    assert tenant.schema_name in body
    # Отсутствующая схема не идёт в знаменатель «проверено».
    assert "схем проверено: 1" in body


def test_all_flag_lists_healthy_schemas():
    """Без --all вывод короткий (только проблемы); с --all видно и здоровые."""
    assert "public: ок" not in _run()
    assert "public: ок" in _run("--all")
