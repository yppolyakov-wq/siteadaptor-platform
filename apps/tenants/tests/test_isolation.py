"""Тесты изоляции данных между арендаторами (schema-per-tenant).

Главная гарантия мульти-тенантности: данные, записанные в схему одного
арендатора, невидимы из схемы другого и из public. Используем встроенную
модель User (django.contrib.auth в TENANT_APPS → таблица в каждой схеме).
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django_tenants.utils import schema_context

from apps.tenants.models import Domain, Tenant


def _make_tenant(schema_name: str) -> Tenant:
    tenant = Tenant(
        schema_name=schema_name,
        name=schema_name,
        slug=schema_name.replace("_", "-"),
        business_type="bakery",
    )
    tenant.auto_create_schema = True
    tenant.save()
    return tenant


def _drop_tenant(tenant: Tenant):
    with connection.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA IF EXISTS "{tenant.schema_name}" CASCADE')
    Domain.objects.filter(tenant=tenant).delete()
    Tenant.objects.filter(pk=tenant.pk).delete()


@pytest.mark.django_db(transaction=True)
def test_data_written_in_one_tenant_is_invisible_in_another():
    User = get_user_model()
    tenant_a = _make_tenant("iso_tenant_a")
    tenant_b = _make_tenant("iso_tenant_b")
    try:
        # Пишем пользователя ТОЛЬКО в схему A.
        with schema_context(tenant_a.schema_name):
            User.objects.create(username="alice_a", email="alice@a.test")

        # A видит alice.
        with schema_context(tenant_a.schema_name):
            assert User.objects.filter(username="alice_a").exists()

        # B НЕ видит alice — изоляция схем.
        with schema_context(tenant_b.schema_name):
            assert not User.objects.filter(username="alice_a").exists()

        # public тоже не видит данные арендатора.
        with schema_context("public"):
            assert not User.objects.filter(username="alice_a").exists()
    finally:
        _drop_tenant(tenant_a)
        _drop_tenant(tenant_b)


@pytest.mark.django_db(transaction=True)
def test_each_tenant_has_independent_rows():
    User = get_user_model()
    tenant_a = _make_tenant("iso_tenant_c")
    tenant_b = _make_tenant("iso_tenant_d")
    try:
        with schema_context(tenant_a.schema_name):
            User.objects.create(username="owner", email="owner@a.test")
        with schema_context(tenant_b.schema_name):
            User.objects.create(username="owner", email="owner@b.test")

        # Один и тот же username сосуществует — это РАЗНЫЕ таблицы в разных схемах.
        with schema_context(tenant_a.schema_name):
            assert User.objects.get(username="owner").email == "owner@a.test"
        with schema_context(tenant_b.schema_name):
            assert User.objects.get(username="owner").email == "owner@b.test"
    finally:
        _drop_tenant(tenant_a)
        _drop_tenant(tenant_b)
