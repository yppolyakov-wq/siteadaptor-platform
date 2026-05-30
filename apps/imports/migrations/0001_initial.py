import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ImportJob",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("resource_type", models.CharField(default="product", max_length=50)),
                ("status", models.CharField(db_index=True, default="uploaded", max_length=20)),
                ("source_file", models.FileField(upload_to="imports/")),
                ("column_mapping", models.JSONField(blank=True, default=dict)),
                ("options", models.JSONField(blank=True, default=dict)),
                ("total_rows", models.IntegerField(default=0)),
                ("processed_rows", models.IntegerField(default=0)),
                ("ok_rows", models.IntegerField(default=0)),
                ("error_rows", models.IntegerField(default=0)),
                ("error_summary", models.TextField(blank=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ImportRow",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("line_no", models.IntegerField()),
                ("raw", models.JSONField(default=dict)),
                ("status", models.CharField(default="pending", max_length=20)),
                ("errors", models.JSONField(blank=True, default=list)),
                ("created_object_id", models.CharField(blank=True, max_length=100)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rows",
                        to="imports.importjob",
                    ),
                ),
            ],
            options={
                "ordering": ["line_no"],
            },
        ),
        migrations.AddIndex(
            model_name="importrow",
            index=models.Index(fields=["job", "status"], name="importrow_job_status_idx"),
        ),
    ]
