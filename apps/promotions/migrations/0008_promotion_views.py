from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("promotions", "0007_loyalty"),
    ]

    operations = [
        migrations.AddField(
            model_name="promotion",
            name="views",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
