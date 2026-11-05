"""AIS-W W4-0: кому закрылась бы касса при включённом гейте готовности — до включения.

    python manage.py readiness_report [--tenant <schema>] [--json]
    python manage.py readiness_report --stamp-exempt [--apply]

По каждому бизнесу (в его схеме): активные направления, невыполненное обязательное, закрыл бы
гейт продажу, были ли продажи за 90 дней. `--stamp-exempt` помечает исключением бизнесы,
которые УЖЕ продают (продажи за 90 дней) и закрылись бы гейтом — решение владельца: работающим
магазинам исключение, а не закрытие. Без `--apply` ничего не пишет. План
docs/ais-w4-0-readiness-plan-2026-11-05.md §4."""

from __future__ import annotations

import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.core import directions, readiness
from apps.tenants.models import Tenant

#: Модели сделок: «бизнес продаёт» = хоть одна запись за окно.
SALES_MODELS = ("orders.Order", "booking.Booking", "stays.StayBooking", "events.Ticket")
SALES_WINDOW_DAYS = 90


def _recent_sales() -> bool:
    from django.apps import apps

    since = timezone.now() - timedelta(days=SALES_WINDOW_DAYS)
    for label in SALES_MODELS:
        try:
            if apps.get_model(label).objects.filter(created_at__gte=since).exists():
                return True
        except Exception:  # noqa: BLE001 — отчёт не падает на одном бизнесе
            continue
    return False


def report_for(tenant) -> dict:
    with schema_context(tenant.schema_name):
        active = [d.key for d in directions.active(tenant)]
        base_missing = [r["key"] for r in readiness.missing(tenant, direction="")]
        closed = {}
        for key in active:
            if not readiness.sell_ready(tenant, key):
                closed[key] = [
                    r["key"]
                    for r in readiness.missing(tenant, direction=key)
                    if r["direction"] == key
                ]
        sales = _recent_sales()
    return {
        "schema": tenant.schema_name,
        "business_type": tenant.business_type or "",
        "demo": bool(tenant.is_demo),
        "exempt": readiness.is_exempt(tenant),
        "directions": active,
        "base_missing": base_missing,
        "would_close": closed,
        "recent_sales": sales,
    }


class Command(BaseCommand):
    help = "AIS-W W4-0: кому закрылась бы касса гейтом готовности (+ исключения работающим)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="", help="только эта схема")
        parser.add_argument("--json", action="store_true")
        parser.add_argument(
            "--stamp-exempt",
            action="store_true",
            help="пометить исключением бизнесы с продажами, которым гейт закрыл бы кассу",
        )
        parser.add_argument("--apply", action="store_true", help="записать (иначе — dry-run)")

    def handle(self, *args, **opts):
        qs = Tenant.objects.exclude(schema_name="public").order_by("schema_name")
        if opts["tenant"]:
            qs = qs.filter(schema_name=opts["tenant"])
        rows = [report_for(t) for t in qs]
        real = [r for r in rows if not r["demo"]]
        closing = [r for r in real if r["would_close"] and not r["exempt"]]
        to_stamp = [r for r in closing if r["recent_sales"]]

        if opts["stamp_exempt"]:
            for row in to_stamp:
                self.stdout.write(f"exempt: {row['schema']} ({', '.join(row['would_close'])})")
                if opts["apply"]:
                    tenant = Tenant.objects.get(schema_name=row["schema"])
                    config = dict(tenant.site_config or {})
                    config["readiness"] = {"exempt": True}
                    tenant.site_config = config
                    tenant.save(update_fields=["site_config", "updated_at"])
            mode = "записано" if opts["apply"] else "dry-run, ничего не записано"
            self.stdout.write(f"Исключений: {len(to_stamp)} ({mode}).")
            return

        if opts["json"]:
            self.stdout.write(json.dumps(rows, indent=2, ensure_ascii=False))
            return
        for row in rows:
            flag = " [demo]" if row["demo"] else (" [exempt]" if row["exempt"] else "")
            close = (
                "; ".join(f"{k}: {', '.join(v) or 'база'}" for k, v in row["would_close"].items())
                or "—"
            )
            self.stdout.write(
                f"{row['schema']}{flag} · {row['business_type']} · "
                f"направления: {', '.join(row['directions']) or '—'} · закрыл бы: {close}"
            )
        self.stdout.write(
            f"Реальных бизнесов, которым закрылась бы касса: {len(closing)} "
            f"(из них уже продают — {len(to_stamp)}, им положено исключение)."
        )
