import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("promotions", "0004_reservation_source_channel"),
    ]

    operations = [
        migrations.CreateModel(
            name="WaitlistEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(blank=True, max_length=200)),
                ("email", models.EmailField(max_length=254)),
                ("notified", models.BooleanField(db_index=True, default=False)),
                (
                    "promotion",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="waitlist",
                        to="promotions.promotion",
                    ),
                ),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.AddConstraint(
            model_name="waitlistentry",
            constraint=models.UniqueConstraint(
                fields=("promotion", "email"), name="uniq_waitlist_promo_email"
            ),
        ),
    ]
