"""T-8.10d D-0: `manage.py search_log_report` — сводка журнала поиска (только чтение)."""

import csv
import json
import sys

from django.core.management.base import BaseCommand

from apps.aggregator import search_report


class Command(BaseCommand):
    help = "Report on the city catalogue search log: empty, multi-word and inferred searches."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--surface", default="", choices=["", "portal", "entdecken", "mcp"])
        parser.add_argument("--city", default="")
        parser.add_argument("--top", type=int, default=20)
        parser.add_argument("--min-searches", type=int, default=search_report.MIN_SEARCHES_TOP)
        parser.add_argument("--format", default="text", choices=["text", "json", "csv"])

    def handle(self, *args, **opts):
        report = search_report.build(
            days=opts["days"],
            surface=opts["surface"],
            city=opts["city"],
            top=opts["top"],
            min_searches=max(2, opts["min_searches"]),
        )
        fmt = opts["format"]
        if fmt == "json":
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return
        if fmt == "csv":
            writer = csv.writer(sys.stdout)
            writer.writerow(["list", "query", "searches", "lang"])
            for name in ("top_zero", "top_multiword_low"):
                for item in report[name]:
                    writer.writerow([name, item["query"], item["searches"], item["lang"]])
            return
        pct = lambda v: f"{v * 100:.1f} %"  # noqa: E731
        lines = [
            f"Searches ({report['days']} days): {report['searches']}",
            f"  no results:            {pct(report['zero_share'])}",
            f"  typo matches only:     {pct(report['trigram_share'])}",
            f"  filters only:          {pct(report['filters_only_share'])}",
            f"  filters from text:     {pct(report['auto_share'])} {report['auto_keys']}",
            f"  multi-word:            {pct(report['multiword_share'])}",
            f"  multi-word, ≤3 hits:   {pct(report['multiword_low_share'])}",
            f"  by surface: {report['by_surface']}",
            f"  by language: {report['by_lang']}",
            f"  subscriptions: {report['follow_kinds']}",
            f"AI phrase search (D-2) recommended: {'yes' if report['d2_recommended'] else 'no'}",
            "Top searches without results:",
            *[f"  {i['searches']:>5}  {i['query']} [{i['lang']}]" for i in report["top_zero"]],
            "Top multi-word searches with few results:",
            *[
                f"  {i['searches']:>5}  {i['query']} [{i['lang']}]"
                for i in report["top_multiword_low"]
            ],
        ]
        self.stdout.write("\n".join(lines))
