from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("aggregator", "0026_t8_7_follow"),
    ]

    operations = [
        migrations.AddField(
            model_name="aggregatorlisting",
            name="variant_terms",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
