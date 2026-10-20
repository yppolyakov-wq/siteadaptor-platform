"""T-10 D-1: схема копией шаблона ≡ схема миграциями; устаревший/грязный шаблон не копируется.

Тесты медленные (схема миграциями ~минута) — шаблон строится один раз на модуль; тесты,
которые его портят, возвращают его в исходное состояние.
"""

import pytest
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django_tenants.utils import schema_exists

from apps.tenants import schema_template
from apps.tenants.models import Domain, Tenant

TPL = "zz_tpl_test"
LAST = ("inventory", "0006_maengelanzeige")
PREV = "0005_bestellposition_qty_returned_and_more"
pytestmark = [pytest.mark.django_db(transaction=True)]


def _drop(*schemas):
    connection.set_schema_to_public()
    with connection.cursor() as cursor:
        for schema in schemas:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


@pytest.fixture(scope="module")
def _built(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        _drop(TPL)
        with override_settings(TENANT_TEMPLATE_SCHEMA=TPL):
            call_command("ensure_template_schema")
        yield
        _drop(TPL)


@pytest.fixture
def template(_built):
    with override_settings(TENANT_TEMPLATE_SCHEMA=TPL):
        yield TPL


def _unapply_last():
    """Шаблон «отстал» на миграцию — по-настоящему (откат), а не подделкой записи."""
    call_command(
        "migrate_schemas",
        LAST[0],
        PREV,
        tenant=True,
        schema_name=TPL,
        interactive=False,
        verbosity=0,
    )
    connection.set_schema_to_public()


def _table_exists(schema, table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM pg_tables WHERE schemaname = %s AND tablename = %s", [schema, table]
        )
        return cursor.fetchone() is not None


def _structure(schema: str) -> dict:
    out = schema_template.structure(schema)
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT app, name FROM "{schema}".django_migrations')
        out["migrations"] = sorted(cursor.fetchall())
        cursor.execute(f'SELECT app_label, model FROM "{schema}".django_content_type')
        out["contenttypes"] = sorted(cursor.fetchall())
        cursor.execute(
            f'SELECT ct.app_label, p.codename FROM "{schema}".auth_permission p '
            f'JOIN "{schema}".django_content_type ct ON ct.id = p.content_type_id'
        )
        out["permissions"] = sorted(cursor.fetchall())
    return out


def _tenant(schema: str) -> Tenant:
    tenant = Tenant(
        schema_name=schema,
        name=schema,
        slug=schema.replace("_", "-"),
        business_type="bakery",
    )
    tenant.auto_create_schema = True
    tenant.save()
    return tenant


def _cleanup(*tenants):
    for tenant in tenants:
        _drop(tenant.schema_name)
        Domain.objects.filter(tenant=tenant).delete()
        Tenant.objects.filter(pk=tenant.pk).delete()


def test_clone_equals_migrations_and_template_is_clean(template):
    assert schema_template.is_ready()
    cloned = _tenant("zz_clone_a")
    with override_settings(TENANT_TEMPLATE_SCHEMA=""):
        migrated = _tenant("zz_migr_b")  # путь миграциями
    try:
        a, b = _structure("zz_clone_a"), _structure("zz_migr_b")
        assert a["migrations"], "в копии нет записей django_migrations"
        diffs = {
            key: (sorted(set(a[key]) - set(b[key])), sorted(set(b[key]) - set(a[key])))
            for key in b
            if a[key] != b[key]
        }
        assert diffs == {}
        # Копия — рабочая схема: запись и чтение модели бизнеса.
        from django.contrib.auth import get_user_model
        from django_tenants.utils import schema_context

        with schema_context("zz_clone_a"):
            get_user_model().objects.create(username="owner_clone")
            assert get_user_model().objects.count() == 1
            # Счётчики служебных таблиц скопированы вместе с данными — новая строка
            # (тип содержимого / запись миграции) не упирается в дубль ключа.
            from django.contrib.contenttypes.models import ContentType
            from django.db.migrations.recorder import MigrationRecorder

            ContentType.objects.create(app_label="zz", model="probe")
            MigrationRecorder(connection).record_applied("zz", "0001_probe")
        connection.set_schema_to_public()
        assert schema_template.dirty_tables() == []  # копия шаблон не пачкает
    finally:
        _cleanup(cloned, migrated)


def test_stale_template_is_not_cloned(template):
    _unapply_last()
    try:
        assert schema_template.pending() == [LAST]
        assert not schema_template.is_ready()
        assert schema_template.clone_into("zz_stale_c") is False
        assert not schema_exists("zz_stale_c")
    finally:
        call_command("ensure_template_schema")


def test_migration_after_check_is_applied_for_real(template, monkeypatch):
    """Код новее шаблона (миграция между проверкой и копией) — догоняем без --fake."""
    _unapply_last()
    monkeypatch.setattr(schema_template, "is_ready", lambda: True)
    try:
        assert schema_template.clone_into("zz_late_g") is True
        assert _table_exists("zz_late_g", "inventory_maengelanzeige")
        from apps.core.schema_migrations import pending, tenant_app_labels

        assert pending("zz_late_g", tenant_app_labels()) == []
    finally:
        _drop("zz_late_g")
        monkeypatch.undo()
        call_command("ensure_template_schema")


def test_dirty_template_is_not_cloned_and_command_refuses(template):
    from django.contrib.auth import get_user_model
    from django_tenants.utils import schema_context

    with schema_context(TPL):
        get_user_model().objects.create(username="leak")
    connection.set_schema_to_public()
    assert schema_template.dirty_tables() == ["auth_user"]
    assert schema_template.clone_into("zz_dirty_d") is False
    assert not schema_exists("zz_dirty_d")
    with pytest.raises(SystemExit):
        call_command("ensure_template_schema")
    call_command("ensure_template_schema", force=True)
    assert schema_template.is_ready()


def test_clone_error_leaves_no_schema(template, monkeypatch):
    def boom(source, target):
        with connection.cursor() as cursor:
            cursor.execute('CREATE SCHEMA "zz_err_e"')
        raise RuntimeError("clone failed")

    monkeypatch.setattr(schema_template, "_clone", boom)
    assert schema_template.clone_into("zz_err_e") is False
    assert not schema_exists("zz_err_e")


def test_structure_mismatch_rolls_back(template, monkeypatch):
    """Копия не совпала с шаблоном — откат, схемы нет, вызывающий идёт миграциями."""
    monkeypatch.setattr(schema_template, "structure_diff", lambda a, b: {"columns": ([], [])})
    assert schema_template.clone_into("zz_mis_h") is False
    assert not schema_exists("zz_mis_h")


def test_busy_lock_falls_back(template):
    """Шаблон мигрирует (блокировка у деплоя) — копии нет, без ожидания."""
    from django.db import connections

    other = connections.create_connection("default")
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [schema_template.LOCK_KEY])
        assert schema_template.clone_into("zz_busy_f") is False
        assert not schema_exists("zz_busy_f")
    finally:
        other.close()


def test_template_name_is_reserved(template):
    tenant = Tenant(schema_name=TPL, name="x", slug="zz-tpl-test", business_type="bakery")
    with pytest.raises(ValueError):
        tenant.create_schema()


def test_command_is_idempotent(template):
    call_command("ensure_template_schema")
    assert schema_template.is_ready()


def test_command_off_when_disabled(capsys):
    with override_settings(TENANT_TEMPLATE_SCHEMA=""):
        call_command("ensure_template_schema")
    assert "выключена" in capsys.readouterr().out


def test_migration_state_includes_template(template, capsys):
    _unapply_last()
    try:
        with pytest.raises(SystemExit):
            call_command("migration_state", check=True)
        assert TPL in capsys.readouterr().out
    finally:
        call_command("ensure_template_schema")


def test_reserved_template_schema_survives_failed_signup_cleanup(template):
    """Ревью безопасности: откат регистрации (`delete(force_drop=True)`) шаблон не сносит."""
    tenant = Tenant(schema_name=TPL, name="x", slug="zz-tpl-test", business_type="bakery")
    tenant.auto_create_schema = False
    tenant.save()
    tenant.delete(force_drop=True)
    assert schema_exists(TPL)


def test_signup_slug_cannot_map_to_template():
    from apps.tenants.forms import BusinessSignupForm

    with override_settings(TENANT_TEMPLATE_SCHEMA="_template"):
        form = BusinessSignupForm(
            data={
                "business_name": "X",
                "slug": "-template",
                "business_type": "bakery",
                "city": "Köln",
                "email": "a@example.com",
                "password1": "geheim123",
                "password2": "geheim123",
            }
        )
        assert not form.is_valid() and "slug" in form.errors
        from apps.tenants import quickstart

        assert quickstart._slug_taken("-template")


def test_invalid_template_name_disables_template():
    with override_settings(TENANT_TEMPLATE_SCHEMA='x"; DROP SCHEMA public; --'):
        assert schema_template.name() == ""
        assert not schema_template.enabled()
