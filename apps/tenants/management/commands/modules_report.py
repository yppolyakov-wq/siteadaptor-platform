"""AIS-M M-1e: исторические пресеты модулей у живых бизнесов.

    python manage.py modules_report [--tenant <schema>] [--json] [--apply]

По умолчанию — только отчёт. `--apply` включает модули тем, кто держит исторический
пресет (класс preset); выбор владельца (класс owner) не трогается. Демо, public и
недопровиженные пропускаются (демо пересеет сидер)."""

from __future__ import annotations

import json
from collections import Counter

from django.core.management.base import BaseCommand

from apps.core import module_report
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Report/fix historic module presets (AIS-M M-1e)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="only this schema")
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **opts):
        qs = Tenant.objects.order_by("schema_name")
        if opts["tenant"]:
            qs = qs.filter(schema_name=opts["tenant"])
        rows, skipped = [], Counter()
        for tenant in qs:
            reason = module_report.skip_reason(tenant)
            if reason:
                skipped[reason] += 1
                continue
            row = module_report.report_for(tenant)
            if opts["apply"] and row["class"] == module_report.CLASS_PRESET:
                row["applied"] = module_report.apply_for(tenant)
            rows.append(row)
        summary = dict(Counter(r["class"] for r in rows))
        if opts["json"]:
            out = {"summary": summary, "skipped": dict(skipped), "tenants": rows}
            self.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))
            return
        for r in rows:
            line = f"{r['schema']:<30} {r['type']:<14} {r['class']:<7}"
            if r["enable"]:
                line += " +" + ",".join(r["enable"])
            if r.get("applied"):
                line += "  ✓ applied"
            if r["base_off"]:
                line += "  (off by owner: " + ",".join(r["base_off"]) + ")"
            self.stdout.write(line)
        self.stdout.write(f"Total: {summary} · skipped: {dict(skipped)}")
        if not opts["apply"] and summary.get(module_report.CLASS_PRESET):
            self.stdout.write("To apply: --apply")
