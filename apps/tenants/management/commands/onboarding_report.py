"""AIS-0: отчёт «время до живого сайта» по меткам мастера — только чтение.

    python manage.py onboarding_report [--days 30] [--type bakery] [--json]

Старт — создание бизнеса (после подтверждения почты), финиш — завершение мастера.
Демо, внутренние, быстрый старт и импорт не считаются. План
docs/ais-0-onboarding-metric-plan-2026-11-05.md."""

from __future__ import annotations

import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tenants.models import Tenant
from apps.tenants.onboarding_metrics import signup_funnel, summarize, tenant_row


def _fmt(minutes) -> str:
    return "—" if minutes is None else f"{minutes:.0f} min"


class Command(BaseCommand):
    help = "AIS-0: время от создания бизнеса до завершения мастера (медиана, p75, шаги)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30, help="созданные за N дней")
        parser.add_argument("--type", default="", help="только этот business_type")
        parser.add_argument("--json", action="store_true")
        parser.add_argument(
            "--compare",
            default="",
            help="FB-26c: дата YYYY-MM-DD — воронка регистрации ДО и ПОСЛЕ неё",
        )

    def handle(self, *args, **opts):
        since = timezone.now() - timedelta(days=max(opts["days"], 1))
        qs = Tenant.objects.exclude(schema_name="public").filter(created_at__gte=since)
        if opts["type"]:
            qs = qs.filter(business_type=opts["type"])
        rows = [row for row in (tenant_row(t) for t in qs.iterator()) if row]
        groups = {"all": rows}
        for row in rows:
            groups.setdefault(row["business_type"] or "—", []).append(row)
        report = {key: summarize(value) for key, value in groups.items()}
        funnel = self._funnel(since, opts["compare"])
        if opts["json"]:
            self.stdout.write(json.dumps({**report, "signup": funnel}, indent=2, default=str))
            return
        for label, data in funnel.items():
            self.stdout.write(self._funnel_line(label, data))
        for key, data in report.items():
            share = data["share_within_day"]
            self.stdout.write(
                f"{key}: {data['tenants']} Betriebe · fertig {data['completed']} · "
                f"Median {_fmt(data['median_minutes'])} · p75 {_fmt(data['p75_minutes'])} · "
                f"≤24 h {'—' if share is None else f'{share:.0%}'}"
            )
            if key != "all":
                continue
            for step, info in sorted(
                data["steps"].items(), key=lambda item: -(item[1]["median"] or 0)
            ):
                self.stdout.write(
                    f"  {step}: Median {_fmt(info['median'])} · "
                    f"gesehen {info['seen']} · übersprungen {info['skipped']}"
                )

    def _funnel(self, since, compare: str) -> dict:
        """Воронка регистрации за период; с --compare — два периода (до / после даты)."""
        from datetime import datetime

        if not compare:
            return {"Registrierung": signup_funnel(since)}
        try:
            cut = timezone.make_aware(datetime.strptime(compare, "%Y-%m-%d"))
        except ValueError:
            self.stderr.write("--compare: Datum als YYYY-MM-DD")
            return {"Registrierung": signup_funnel(since)}
        return {
            f"Registrierung vor {compare}": signup_funnel(since, cut),
            f"Registrierung ab {compare}": signup_funnel(cut),
        }

    @staticmethod
    def _funnel_line(label: str, data: dict) -> str:
        def pct(value):
            return "—" if value is None else f"{value:.0%}"

        return (
            f"{label}: {data['sent']} Anfragen · bestätigt {data['confirmed']} "
            f"({pct(data['confirm_rate'])}) · Assistent fertig {data['completed']} "
            f"({pct(data['complete_rate'])})"
        )
