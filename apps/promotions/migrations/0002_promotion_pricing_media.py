from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("promotions", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="promotion",
            name="compare_at_price",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="promotion",
            name="images",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="promotion",
            name="show_countdown",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="promotion",
            name="strikethrough_old_price",
            field=models.BooleanField(default=True),
        ),
    ]
