from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("aggregator", "0012_aggregatorlisting_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="aggregatorlisting",
            name="featured_payment_ref",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
