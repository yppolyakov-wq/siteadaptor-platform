"""CA1: тумблер ЛК клиента — дефолт по типу бизнеса для СУЩЕСТВУЮЩИХ тенантов.

Новый опциональный модуль customer_account иначе был бы активен у всех (его нет
в disabled_modules). Решение владельца: ВКЛ для транзакционных типов, ВЫКЛ для
чистых витрин. Здесь дозаписываем «customer_account» в disabled_modules тем
тенантам, чей business_type НЕ в recommended_for модуля (через
modules.default_disabled_for — единый источник правды). Новые тенанты получают
это через create_business. Идемпотентно.
"""

from django.db import migrations


def disable_for_showrooms(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    from apps.core import modules

    for tenant in Tenant.objects.all():
        if "customer_account" not in modules.default_disabled_for(tenant.business_type):
            continue  # транзакционный тип → оставляем включённым
        disabled = list(tenant.disabled_modules or [])
        if "customer_account" not in disabled:
            disabled.append("customer_account")
            tenant.disabled_modules = disabled
            tenant.save(update_fields=["disabled_modules"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("tenants", "0016_tenant_opening_hours_structured")]
    operations = [migrations.RunPython(disable_for_showrooms, noop)]
