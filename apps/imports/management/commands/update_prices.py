"""M21.7: цены и фасовки по артикулам из CSV (прайс-лист владельца).

    python manage.py update_prices --schema haanerteeladen --file /tmp/preise.csv
    python manage.py update_prices --schema haanerteeladen --file /tmp/preise.csv --apply

CSV через «;»: артикул;фасовка;цена;действие (пусто | nur | loeschen). Правила —
``apps/catalog/price_list.py`` (те же, что у мастера импорта, тип «Preisliste»).
Без ``--apply`` — только «было → станет». Ошибка в строке не останавливает остальные;
запись — одной транзакцией.
"""

import csv
import io

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_tenants.utils import get_tenant_model, schema_context

from apps.catalog import price_list

HEADER_WORDS = ("artikel", "art", "sku", "art.-nr.")


class Command(BaseCommand):
    help = "Цены и фасовки по артикулам из CSV (артикул;фасовка;цена;действие)."

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True)
        parser.add_argument("--file", required=True, help="CSV через «;» (UTF-8)")
        parser.add_argument("--apply", action="store_true", help="Записать (иначе показ).")

    def handle(self, *args, **opts):
        try:
            with open(opts["file"], encoding="utf-8-sig") as fh:
                text = fh.read()
        except OSError as exc:
            raise CommandError(f"file: {exc}") from exc
        tenant = get_tenant_model().objects.filter(schema_name=opts["schema"]).first()
        if tenant is None:
            raise CommandError(f"business {opts['schema']!r} not found")
        rows = [
            r for r in csv.reader(io.StringIO(text), delimiter=";") if any(c.strip() for c in r)
        ]
        if rows and rows[0][0].strip().lower() in HEADER_WORDS:
            rows = rows[1:]  # строка заголовков
        errors = 0
        with schema_context(tenant.schema_name), transaction.atomic():
            for n, row in enumerate(rows, 1):
                code, size, price, action = (list(row) + ["", "", "", ""])[:4]
                try:
                    change = price_list.apply_row(code, size, price, action)
                except price_list.PriceListError as exc:
                    errors += 1
                    self.stdout.write(f"  ! {n}: {code.strip()} — {exc}")
                else:
                    self.stdout.write(f"  {change.code} {change.name}: {change.text}")
            if not opts["apply"]:
                transaction.set_rollback(True)
        self.stdout.write(f"rows: {len(rows)}, errors: {errors}")
        self.stdout.write("saved" if opts["apply"] else "dry-run: nothing written (use --apply)")
