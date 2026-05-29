from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="tenant",
            index=models.Index(
                fields=["city", "is_active"], name="tenant_city_active_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="tenant",
            index=models.Index(
                fields=["business_type", "city"], name="tenant_btype_city_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="tenant",
            index=models.Index(
                fields=["subscription_status", "trial_ends_at"],
                name="tenant_substatus_trial_idx",
            ),
        ),
    ]
