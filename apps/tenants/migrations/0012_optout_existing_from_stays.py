"""Track E / E1: лёгкий старт для модуля «stays» (Übernachtung).

Реестр модулей появляется у всех тенантов сразу (храним «выключенное»). Чтобы
новый движок по датам не «зажёгся» в кабинете у пекарен/бутиков при его
регистрации (E2), заранее дописываем "stays" в ``disabled_modules`` всем
СУЩЕСТВУЮЩИМ не-hotel тенантам. Новые тенанты получат тот же дефолт через
onboarding (``modules.default_disabled_for``); существующие hotel — модуль
активен (рекомендован вертикали). Идемпотентно: повторно ключ не добавляем.
"""

from django.db import migrations

MODULE_KEY = "stays"


def optout_existing(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    for tenant in Tenant.objects.exclude(business_type="hotel"):
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
        ("tenants", "0011_tenant_orders_prepay"),
    ]

    operations = [
        migrations.RunPython(optout_existing, undo_optout),
    ]
