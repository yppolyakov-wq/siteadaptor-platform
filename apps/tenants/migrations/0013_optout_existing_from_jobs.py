"""G6 / F1: лёгкий старт для модуля «jobs» (Aufträge/Angebote).

Модуль для выездных Handwerker — opt-in (universal, по умолчанию выключен у всех
вертикалей, как finance). Чтобы он не «зажёгся» в кабинете у существующих
тенантов при регистрации (F2), заранее дописываем "jobs" в ``disabled_modules``
ВСЕМ существующим тенантам. Новые получат тот же дефолт через onboarding
(``modules.default_disabled_for``); Handwerker включает модуль вручную.
Идемпотентно: повторно ключ не добавляем.
"""

from django.db import migrations

MODULE_KEY = "jobs"


def optout_existing(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    for tenant in Tenant.objects.all():
        disabled = list(tenant.disabled_modules or [])
        if MODULE_KEY not in disabled:
            disabled.append(MODULE_KEY)
            tenant.disabled_modules = disabled
            tenant.save(update_fields=["disabled_modules"])


def undo_optout(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    for tenant in Tenant.objects.all():
        disabled = list(tenant.disabled_modules or [])
        if MODULE_KEY in disabled:
            disabled.remove(MODULE_KEY)
            tenant.disabled_modules = disabled
            tenant.save(update_fields=["disabled_modules"])


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0012_optout_existing_from_stays"),
    ]

    operations = [
        migrations.RunPython(optout_existing, undo_optout),
    ]
