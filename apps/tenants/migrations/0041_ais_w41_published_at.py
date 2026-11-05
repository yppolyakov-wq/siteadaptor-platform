"""AIS-W W4-1: Tenant.published_at — живые бизнесы считаются опубликованными с даты создания."""

import django.utils.timezone
from django.db import migrations, models
from django.db.models import F


def backfill(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    Tenant.objects.update(published_at=F("created_at"))


class Migration(migrations.Migration):
    dependencies = [("tenants", "0040_ka12_closure_ranges")]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="published_at",
            field=models.DateTimeField(blank=True, default=django.utils.timezone.now, null=True),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
