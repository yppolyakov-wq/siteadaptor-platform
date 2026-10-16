# T-8.26 (Р-5): флаг внутреннего/тестового тенанта (SHARED, аддитивно).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tenants", "0036_t8_22_city_category")]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="is_internal",
            field=models.BooleanField(default=False),
        ),
    ]
