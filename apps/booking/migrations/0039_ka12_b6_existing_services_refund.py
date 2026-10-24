"""KA-12 B6: существующие услуги сохраняют прежние условия — поздняя отмена
возвращает деньги («Immer erstatten»). «Anzahlung einbehalten» — дефолт только
НОВЫХ услуг (решение В-2); у старых владелец включает удержание сам."""

from django.db import migrations


def forwards(apps, schema_editor):
    Service = apps.get_model("booking", "Service")
    Service.objects.update(late_cancel="refund")


class Migration(migrations.Migration):
    dependencies = [("booking", "0038_ka12_b6_cancel_policy")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
