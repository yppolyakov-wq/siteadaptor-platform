import django.db.models.deletion
from django.db import migrations, models

import apps.integrations.webhooks.models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="OutgoingWebhook",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant_schema", models.CharField(db_index=True, max_length=100)),
                ("url", models.URLField()),
                ("secret", models.CharField(default=apps.integrations.webhooks.models._gen_secret, max_length=64)),
                ("event_types", models.JSONField(default=list)),
                ("is_active", models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name="WebhookDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("event_type", models.CharField(db_index=True, max_length=100)),
                ("event_id", models.CharField(db_index=True, max_length=100)),
                ("payload", models.JSONField(default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("delivered", "Delivered"), ("failed", "Failed")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("attempts", models.IntegerField(default=0)),
                ("response_code", models.IntegerField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
                ("next_retry_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                (
                    "webhook",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="webhooks.outgoingwebhook",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="outgoingwebhook",
            index=models.Index(fields=["tenant_schema", "is_active"], name="webhook_tenant_active_idx"),
        ),
        migrations.AddIndex(
            model_name="webhookdelivery",
            index=models.Index(fields=["status", "next_retry_at"], name="webhook_delivery_status_idx"),
        ),
    ]
