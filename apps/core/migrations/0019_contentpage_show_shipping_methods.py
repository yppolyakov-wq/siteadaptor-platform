from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0018_content_page"),
    ]

    operations = [
        migrations.AddField(
            model_name="contentpage",
            name="show_shipping_methods",
            field=models.BooleanField(default=True),
        ),
    ]
