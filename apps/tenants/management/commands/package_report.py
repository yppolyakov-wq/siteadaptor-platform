"""T-8.32a: что потолок пакета гасит у каждого бизнеса — до деплоя, только чтение.

    python manage.py package_report [--tenant <schema>] [--only-lite] [--json]

По каждому тенанту: пакет (выведенный из профиля), модули, которые сейчас включены и
погаснут потолком, данные в этих модулях (их не удаляем — при подъёме пакета снова
видны) и листинги каталога города, которые уйдут при следующей реконсиляции.
План docs/t8-32ab-package-gate-plan-2026-10-23.md §5."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from apps.core import modules, packages
from apps.tenants.models import Tenant

#: модуль → модель, чьи записи станут невидимыми (вывод — служебный, для оператора).
DATA = {
    "blog": "events.BlogPost",
    "crm": "crm.CustomerNote",
    "orders": "orders.Order",
    "booking": "booking.Booking",
    "stays": "stays.StayBooking",
    "events": "events.Ticket",
    "loyalty": "loyalty.LoyaltyProgram",
    "reviews": "reviews.Review",
}

#: модуль → вид листинга каталога города, который уйдёт вместе с ним.
LISTING_KIND = {"stays": "stay", "events": "event", "booking": "service"}


def _count(label: str) -> int | None:
    from django.apps import apps

    try:
        return apps.get_model(label).objects.count()
    except Exception:  # noqa: BLE001 — отчёт не падает на одном тенанте
        return None


def _without_ceiling(tenant, key: str) -> bool:
    """Активность модуля, как если бы потолка пакета не было (зеркало is_module_active)."""
    spec = modules.get_module(key)
    if spec is None:
        return False
    if spec.core:
        return True
    if not modules.is_entitled(tenant, spec):
        return False
    if key in (getattr(tenant, "disabled_modules", None) or []):
        return False
    return all(_without_ceiling(tenant, dep) for dep in spec.depends_on)


def report_for(tenant) -> dict:
    package = packages.package_of(tenant)
    lost = [
        s.key
        for s in modules.optional_modules()
        if _without_ceiling(tenant, s.key) and not modules.is_module_active(tenant, s.key)
    ]
    data = {}
    if lost:
        with schema_context(tenant.schema_name):
            for key in lost:
                if key in DATA:
                    n = _count(DATA[key])
                    if n:
                        data[DATA[key]] = n
    listings = {}
    kinds = [LISTING_KIND[k] for k in lost if k in LISTING_KIND]
    if kinds:
        from apps.aggregator.models import AggregatorListing

        for kind in kinds:
            n = AggregatorListing.objects.filter(
                tenant_schema=tenant.schema_name, listing_kind=kind, is_active=True
            ).count()
            if n:
                listings[kind] = n
    return {
        "schema": tenant.schema_name,
        "name": tenant.name,
        "package": package.key,
        "demo": bool(getattr(tenant, "is_demo", False)),
        "modules_lost": lost,
        "data_hidden": data,
        "listings_leaving": listings,
    }


class Command(BaseCommand):
    help = "Показать, что потолок пакета гасит у бизнесов (только чтение)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="")
        parser.add_argument("--only-lite", action="store_true")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, tenant, only_lite, as_json, **opts):
        qs = Tenant.objects.exclude(schema_name="public").order_by("schema_name")
        if tenant:
            qs = qs.filter(schema_name=tenant)
        rows = []
        for t in qs:
            if only_lite and not packages.package_of(t).lite:
                continue
            rows.append(report_for(t))
        if as_json:
            self.stdout.write(_dumps(rows))
            return
        affected = 0
        for r in rows:
            flag = " [demo]" if r["demo"] else ""
            self.stdout.write(f"{r['schema']:30} {r['package']:9}{flag}")
            if r["modules_lost"]:
                self.stdout.write(f"    modules off: {', '.join(r['modules_lost'])}")
            if r["data_hidden"]:
                affected += 0 if r["demo"] else 1
                parts = ", ".join(f"{k}: {v}" for k, v in r["data_hidden"].items())
                self.stdout.write(self.style.WARNING(f"    data hidden: {parts}"))
            if r["listings_leaving"]:
                parts = ", ".join(f"{k}: {v}" for k, v in r["listings_leaving"].items())
                self.stdout.write(f"    city listings leaving: {parts}")
        self.stdout.write(
            f"\nTotal: {len(rows)}; real businesses with data under the ceiling: {affected}"
        )


def _dumps(rows) -> str:
    return json.dumps(rows, ensure_ascii=False, indent=2)
