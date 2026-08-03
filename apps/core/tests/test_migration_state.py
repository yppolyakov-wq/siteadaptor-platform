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


def test_schema_created_but_never_migrated_is_loud_not_silent():
    """Схема есть, таблиц в ней нет (провижининг умер на полпути).

    Самый опасный режим команды: `search_path` тенанта включает public, где
    `django_migrations` ЕСТЬ. Читай загрузчик её — команда отрапортовала бы «всё
    применено» про схему вообще без таблиц, то есть соврала бы ровно там, ради
    чего написана. Проверено и на стенде: в такой схеме применённых 0.
    """
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("CREATE SCHEMA probe_unmigrated")
    TenantFactory(schema_name="probe_unmigrated")

    body = _run()
    assert "СХЕМЫ ОТСУТСТВУЮТ" not in body  # схема существует — диагноз другой
    assert "Всё применено" not in body
    # Имя схемы обязано быть в выводе: без него «не применена» могло бы прийти
    # откуда угодно и тест ловил бы не то.
    assert "probe_unmigrated" in body


def test_all_flag_lists_healthy_schemas():
    """Без --all вывод короткий (только проблемы); с --all видно и здоровые."""
    assert "public: ок" not in _run()
    assert "public: ок" in _run("--all")
