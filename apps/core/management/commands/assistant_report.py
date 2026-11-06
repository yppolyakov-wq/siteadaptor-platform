"""AIS A-6b: отчёт качества помощника по бизнесам — только коды и числа.

    python manage.py assistant_report [--schema <schema>] [--days 30] [--json]
    python manage.py assistant_report --schema <schema> --samples 20   # непонятые фразы

Без `--schema` — по всем бизнесам с историей за период (без public). `--samples` — вопросы,
которые помощник не понял: только с `--schema`, после повторного `pii.scrub`, ≤ 120 символов, без автора. Команда —
для оператора платформы на сервере; экрана нет. План — docs/ais-a6-quality-plan-2026-11-06.md §4.
"""

from __future__ import annotations

import json
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context


class Command(BaseCommand):
    help = "Качество помощника кабинета: исходы по обработчикам, пакеты, отказы (без текста)."

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="")
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--samples", type=int, default=0)

    def handle(self, *args, **opts):
        from apps.core import assistant_quality
        from apps.tenants.models import Tenant

        days = max(1, min(int(opts["days"]), 90))
        if opts["samples"] and not opts["schema"]:
            raise CommandError("--samples только вместе с --schema.")
        if opts["schema"]:
            if not Tenant.objects.filter(schema_name=opts["schema"]).exists():
                raise CommandError(f"Схема не найдена: {opts['schema']}")
            schemas = [opts["schema"]]
        else:
            schemas = list(
                Tenant.objects.exclude(schema_name=get_public_schema_name())
                .order_by("schema_name")
                .values_list("schema_name", flat=True)
            )
        since = timezone.now() - timedelta(days=days)
        reports = []
        for schema in schemas:
            with schema_context(schema):
                # без --schema бизнесы без истории не читаем (счётчики — тысячи ключей на бизнес)
                if not opts["schema"] and not assistant_quality.has_turns(since):
                    continue
                report = assistant_quality.summarize(schema, since, days)
                if opts["samples"]:
                    report["samples"] = assistant_quality.samples(schema, since, opts["samples"])
            if report["turns"] or report["counters"] or opts["schema"]:
                reports.append(report)
        if opts["json"]:
            self.stdout.write(json.dumps(reports, ensure_ascii=False, indent=2))
            return
        for r in reports:
            self._print(r, days)
        if not reports:
            self.stdout.write(f"Нет обращений к помощнику за {days} дн.")

    def _print(self, r: dict, days: int) -> None:
        w = self.stdout.write
        w(f"== {r['schema']} · {days} дн. · ходов {r['turns']} · непонято {r['misses']}")
        for route, codes in r["routes"].items():
            total = sum(codes.values())
            parts = ", ".join(f"{c} {n * 100 // total} %" for c, n in sorted(codes.items()))
            w(f"  {route:<11} {total:>4}  {parts}")
        a = r["actions"]
        w(
            f"  пакеты: предложено {a['proposed']}, применено {a['applied']}, "
            f"откачено {a['undone']}; ср. отброшено {r['avg_dropped']}; "
            f"уточнений {r['clarify_rounds']}"
        )
        if r["counters"]:
            w("  счётчики: " + ", ".join(f"{k}={v}" for k, v in r["counters"].items()))
        for s in r.get("samples", []):
            w(f"  – {s}")
