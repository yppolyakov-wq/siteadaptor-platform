from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("promotions", "0003_customer_unsubscribe"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="source_channel",
            field=models.CharField(blank=True, db_index=True, default="", max_length=50),
            preserve_default=False,
        ),
    ]
