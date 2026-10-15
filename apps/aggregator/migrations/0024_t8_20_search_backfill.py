"""T-8.20: заполнить поисковый индекс у уже существующих листингов.

Осознанно зовёт рабочий индексатор (`search_index.refresh_listing`): индекс строится
«по текущему правилу». Смена правила позже — `manage.py rebuild_search_index`.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    from apps.aggregator import search_index

    Listing = apps.get_model("aggregator", "AggregatorListing")
    for listing in Listing.objects.all().iterator():
        search_index.refresh_listing(listing)


class Migration(migrations.Migration):
    dependencies = [("aggregator", "0023_t8_20_search")]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
