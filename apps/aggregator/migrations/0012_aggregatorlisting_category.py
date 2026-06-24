from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("aggregator", "0011_stay_event_listings"),
    ]

    operations = [
        migrations.AddField(
            model_name="aggregatorlisting",
            name="category",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddIndex(
            model_name="aggregatorlisting",
            index=models.Index(
                fields=["category", "is_active"], name="agg_category_active_idx"
            ),
        ),
    ]
