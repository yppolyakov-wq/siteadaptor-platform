"""T-8.20: пересобрать поисковый индекс каталога города (смена правила индекса без миграции)."""

from django.core.management.base import BaseCommand

from apps.aggregator import search_index
from apps.aggregator.models import AggregatorListing


class Command(BaseCommand):
    help = "Пересобрать search_vector/search_text у листингов каталога города."

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="", help="только листинги этого бизнеса")

    def handle(self, *args, **opts):
        qs = AggregatorListing.objects.all()
        if opts["schema"]:
            qs = qs.filter(tenant_schema=opts["schema"])
        n = search_index.refresh(qs)
        self.stdout.write(self.style.SUCCESS(f"Индекс обновлён: {n} листингов"))
