from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0031_combo_vat_rate")]

    operations = [
        migrations.AddField(
            model_name="product",
            name="card_style",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
    ]
