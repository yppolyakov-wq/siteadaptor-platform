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
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.core import directions, readiness
from apps.tenants.models import Tenant

#: Модели сделок: «бизнес продаёт» = хоть одна запись за окно.
SALES_MODELS = ("orders.Order", "booking.Booking", "stays.StayBooking", "events.Ticket")
SALES_WINDOW_DAYS = 90

logger = logging.getLogger(__name__)


def _recent_sales() -> bool | None:
    """True/False — были ли продажи за окно; None — проверить не удалось.

    Сбой НЕ равен «продаж не было»: иначе работающий магазин не получит исключения и
    касса закроется. None трактуется как «продаёт» (исключение ставится)."""
    from django.apps import apps

    since = timezone.now() - timedelta(days=SALES_WINDOW_DAYS)
    unknown = False
    for label in SALES_MODELS:
        try:
            if apps.get_model(label).objects.filter(created_at__gte=since).exists():
                return True
        except Exception:  # noqa: BLE001 — отчёт не падает на одном бизнесе
            logger.warning("readiness_report: cannot check %s", label, exc_info=True)
            unknown = True
    return None if unknown else False


def report_for(tenant) -> dict:
    """Строка отчёта; сбой бизнеса не роняет отчёт целиком — строка с ошибкой."""
    try:
        return _report_for(tenant)
    except Exception:  # noqa: BLE001
        logger.warning("readiness_report: %s failed", tenant.schema_name, exc_info=True)
        return {
            "schema": tenant.schema_name,
            "business_type": tenant.business_type or "",
            "demo": readiness.is_service_tenant(tenant),
            "errors": ["report"],
            "exempt": readiness.is_exempt(tenant),
            "directions": [],
            "base_missing": [],
            "would_close": {},
            "recent_sales": None,
        }


def _report_for(tenant) -> dict:
    with schema_context(tenant.schema_name):
        active = [d.key for d in directions.active(tenant)]
        base_missing = [r["key"] for r in readiness.missing(tenant, direction="")]
        closed = {}
        for key in active:
            if not readiness.sell_ready(tenant, key):
                closed[key] = [
                    r["key"] for r in readiness.missing(tenant, direction=key, only_direction=True)
                ]
        sales = _recent_sales()
        errors = list(readiness.facts_for(tenant).errors)
    return {
        "schema": tenant.schema_name,
        "business_type": tenant.business_type or "",
        "demo": readiness.is_service_tenant(tenant),
        "errors": errors,
        "exempt": readiness.is_exempt(tenant),
        "directions": active,
        "base_missing": base_missing,
        "would_close": closed,
        "recent_sales": sales,
    }


def needs_exempt(row: dict) -> bool:
    """Исключение: реальный бизнес, которому гейт закрыл бы кассу, и он продаёт (или неясно)."""
    # Ошибка проверки = «не можем доказать готовность»: исключение ставим (fail-closed для
    # отчёта — иначе сбой во время отчёта оставил бы продающий бизнес без исключения).
    return (
        not row["demo"]
        and not row["exempt"]
        and bool(row["would_close"] or row["errors"])
        and row["recent_sales"] is not False
    )


def stamp_exempt(schema_name: str) -> None:
    """Пометить исключением под блокировкой строки (параллельный Save не затрёт флаг)."""
    with transaction.atomic():
        tenant = Tenant.objects.select_for_update().get(schema_name=schema_name)
        config = dict(tenant.site_config or {})
        block = config.get("readiness")
        config["readiness"] = {**(block if isinstance(block, dict) else {}), "exempt": True}
        tenant.site_config = config
        tenant.save(update_fields=["site_config", "updated_at"])


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
        closing = [r for r in real if (r["would_close"] or r["errors"]) and not r["exempt"]]
        to_stamp = [r for r in rows if needs_exempt(r)]

        if opts["stamp_exempt"]:
            for row in to_stamp:
                self.stdout.write(f"exempt: {row['schema']} ({', '.join(row['would_close'])})")
                if opts["apply"]:
                    stamp_exempt(row["schema"])
            mode = "записано" if opts["apply"] else "dry-run, ничего не записано"
            self.stdout.write(f"Исключений: {len(to_stamp)} ({mode}).")
            return

        if opts["json"]:
            self.stdout.write(json.dumps(rows, indent=2, ensure_ascii=False))
            return
        for row in rows:
            flag = " [demo]" if row["demo"] else (" [exempt]" if row["exempt"] else "")
            if row["errors"]:
                flag += f" [error: {', '.join(row['errors'])}]"
            if row["recent_sales"] is None:
                flag += " [sales ?]"
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
