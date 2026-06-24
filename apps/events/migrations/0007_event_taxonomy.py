from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0006_registration_waitlist"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="city",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="event",
            name="category",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="event",
            name="level",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="event",
            name="language",
            field=models.CharField(blank=True, max_length=10),
        ),
    ]
