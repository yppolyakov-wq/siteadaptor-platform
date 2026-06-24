import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0005_ticket_extras"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="registration_fields",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.CreateModel(
            name="EventWaitlistEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(blank=True, max_length=200)),
                ("email", models.EmailField(max_length=254)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("party_size", models.PositiveSmallIntegerField(default=1)),
                ("notified", models.BooleanField(db_index=True, default=False)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="waitlist",
                        to="events.event",
                    ),
                ),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.AddConstraint(
            model_name="eventwaitlistentry",
            constraint=models.UniqueConstraint(
                fields=["event", "email"], name="uniq_event_waitlist_email"
            ),
        ),
    ]
