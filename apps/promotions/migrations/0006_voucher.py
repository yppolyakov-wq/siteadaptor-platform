import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("promotions", "0005_waitlistentry"),
    ]

    operations = [
        migrations.CreateModel(
            name="Voucher",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=12, unique=True)),
                ("label", models.CharField(max_length=120)),
                ("max_uses", models.PositiveIntegerField(default=1)),
                ("used_count", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
