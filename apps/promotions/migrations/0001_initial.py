import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Customer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=200)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("note", models.TextField(blank=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Promotion",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("title", models.JSONField(default=dict)),
                ("description", models.JSONField(default=dict)),
                ("promo_type", models.CharField(choices=[("discount", "Discount"), ("reservation", "Reservation")], default="reservation", max_length=20)),
                ("discount_percent", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("price_override", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("available_quantity", models.IntegerField(blank=True, null=True)),
                ("max_per_customer", models.PositiveSmallIntegerField(default=1)),
                ("reservation_ttl_hours", models.PositiveIntegerField(default=24)),
                ("auto_confirm", models.BooleanField(default=False)),
                ("status", models.CharField(db_index=True, default="draft", max_length=20)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="promotions",
                        to="catalog.product",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Reservation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reference_code", models.CharField(max_length=12, unique=True)),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("status", models.CharField(db_index=True, default="pending", max_length=20)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("fulfilled_at", models.DateTimeField(blank=True, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("note", models.TextField(blank=True)),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reservations",
                        to="promotions.customer",
                    ),
                ),
                (
                    "promotion",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reservations",
                        to="promotions.promotion",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="customer",
            index=models.Index(fields=["email"], name="customer_email_idx"),
        ),
        migrations.AddIndex(
            model_name="promotion",
            index=models.Index(fields=["status", "starts_at"], name="promo_status_starts_idx"),
        ),
        migrations.AddIndex(
            model_name="promotion",
            index=models.Index(fields=["status", "ends_at"], name="promo_status_ends_idx"),
        ),
        migrations.AddIndex(
            model_name="reservation",
            index=models.Index(fields=["status", "expires_at"], name="resv_status_expires_idx"),
        ),
        migrations.AddIndex(
            model_name="reservation",
            index=models.Index(fields=["promotion", "status"], name="resv_promo_status_idx"),
        ),
    ]
