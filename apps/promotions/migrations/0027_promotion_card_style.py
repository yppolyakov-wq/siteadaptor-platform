from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("promotions", "0026_promotion_status_choices")]

    operations = [
        migrations.AddField(
            model_name="promotion",
            name="card_style",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
    ]
