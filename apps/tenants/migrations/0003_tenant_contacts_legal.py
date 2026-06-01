from django.db import migrations, models


def _char(**kw):
    return models.CharField(blank=True, default="", **kw)


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0002_tenant_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="contact_email",
            field=models.EmailField(blank=True, default="", max_length=254),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="tenant",
            name="contact_phone",
            field=_char(max_length=30),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="tenant",
            name="website_url",
            field=models.URLField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="tenant",
            name="opening_hours",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="tenant",
            name="map_url",
            field=models.URLField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="tenant",
            name="vat_id",
            field=_char(max_length=30),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="tenant",
            name="register_entry",
            field=_char(max_length=120),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="tenant",
            name="legal_responsible",
            field=_char(max_length=200),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="tenant",
            name="impressum",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="tenant",
            name="privacy_policy",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="tenant",
            name="withdrawal_policy",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
    ]
