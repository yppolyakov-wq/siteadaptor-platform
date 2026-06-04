from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0003_tenant_contacts_legal"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="auto_redeem_on_scan",
            field=models.BooleanField(default=False),
        ),
    ]
