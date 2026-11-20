"""FB-33 M2b-2b C1 (L3): свои вопросы FAQ товара и номера — только аддитивные миграции.

`catalog/0046` и `stays/0049`: два AddField с `db_default` (старые контейнеры во время деплоя
пишут строки без новых столбцов), без RunPython и без переноса данных.
"""

import importlib

import pytest
from django.db import connection, migrations

pytestmark = pytest.mark.django_db

MIGRATIONS = {
    "apps.catalog.migrations.0046_fb33_product_faq": "product",
    "apps.stays.migrations.0049_fb33_unit_faq": "stayunit",
}


@pytest.mark.parametrize("path", sorted(MIGRATIONS))
def test_migration_is_additive_with_db_default(path):
    ops = importlib.import_module(path).Migration.operations
    assert [type(op) for op in ops] == [migrations.AddField, migrations.AddField]
    by_name = {op.name: op for op in ops}
    assert set(by_name) == {"faq", "faq_i18n"}
    assert {op.model_name for op in ops} == {MIGRATIONS[path]}
    assert by_name["faq"].field.db_default == [] and by_name["faq"].field.default is list
    assert by_name["faq_i18n"].field.db_default == {}
    assert by_name["faq_i18n"].field.default is dict
    assert all(op.field.blank for op in ops)


@pytest.mark.parametrize(
    "table", ["catalog_product", "stays_stayunit"], ids=["product", "stayunit"]
)
def test_columns_have_database_defaults(table):
    """Строка, записанная без новых столбцов (старый код), получает [] и {} от базы."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT column_name, column_default, is_nullable FROM information_schema.columns "
            "WHERE table_name = %s AND column_name IN ('faq', 'faq_i18n') "
            "AND table_schema = current_schema()",
            [table],
        )
        rows = {name: (default, nullable) for name, default, nullable in cur.fetchall()}
    assert set(rows) == {"faq", "faq_i18n"}
    assert "'[]'" in rows["faq"][0] and "'{}'" in rows["faq_i18n"][0]
    assert rows["faq"][1] == rows["faq_i18n"][1] == "NO"


def test_models_default_to_empty_lists():
    from apps.catalog.tests.factories import ProductFactory
    from apps.stays.models import StayUnit

    product = ProductFactory()
    unit = StayUnit.objects.create(name="FeWo", price_cents=9000)
    for obj in (product, unit):
        obj.refresh_from_db()
        assert obj.faq == [] and obj.faq_i18n == {}
