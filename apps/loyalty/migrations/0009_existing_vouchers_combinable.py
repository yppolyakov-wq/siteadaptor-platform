"""Решение владельца 2026-10-30: коды, выпущенные ДО правила «скидки не суммируются»,
сохраняют прежнее поведение — действуют поверх акций. Новые коды — по умолчанию нет."""

from django.db import migrations


def mark_existing(apps, schema_editor):
    Voucher = apps.get_model("loyalty", "Voucher")
    Voucher.objects.filter(combinable=False).update(combinable=True)


class Migration(migrations.Migration):
    dependencies = [("loyalty", "0008_voucher_combinable")]

    operations = [migrations.RunPython(mark_existing, migrations.RunPython.noop)]
