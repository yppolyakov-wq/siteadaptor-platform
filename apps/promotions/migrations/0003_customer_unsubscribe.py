import uuid

from django.db import migrations, models


def _backfill_tokens(apps, schema_editor):
    """AddField даёт всем существующим строкам один и тот же default —
    раздаём каждому клиенту собственный токен."""
    Customer = apps.get_model("promotions", "Customer")
    for customer in Customer.objects.all():
        customer.unsubscribe_token = uuid.uuid4()
        customer.save(update_fields=["unsubscribe_token"])


class Migration(migrations.Migration):
    dependencies = [
        ("promotions", "0002_promotion_pricing_media"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="unsubscribed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="customer",
            name="unsubscribe_token",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False),
        ),
        migrations.RunPython(_backfill_tokens, migrations.RunPython.noop),
    ]
