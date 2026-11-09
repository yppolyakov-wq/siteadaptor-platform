"""SHP-7: магазины, у которых доставка ещё в прежних полях бизнеса — только чтение.

    python manage.py shipping_report [--tenant <schema>] [--json] [--with-demo]

До SHP-1 у бизнеса была одна «Lieferung» (плоская цена + PLZ-зоны). После переезда она
читается как «Kurier in der Stadt» — пока владелец сам не сохранит способы доставки.
Отправку ПОСЫЛКАМИ (DHL/Hermes …) не включаем никому сами: отчёт показывает, у кого
текст условий похож на отправку по стране, — решение за владельцем бизнеса (план
docs/ful-fulfilment-modes-plan-2026-11-09.md). Отчёт ничего не меняет."""

from __future__ import annotations

import json
import re

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from apps.tenants.models import Tenant

#: слова в условиях доставки, похожие на отправку по стране (подсказка оператору)
PARCEL_HINT = re.compile(
    r"\b(dhl|hermes|dpd|gls|ups|post|paket|versand|deutschlandweit|bundesweit)\b", re.I
)


def report_for(tenant) -> dict | None:
    """Строка отчёта или None, если бизнесу переезжать нечего."""
    from apps.orders.models import ShippingMethod

    if not getattr(tenant, "delivery_enabled", False):
        return None
    with schema_context(tenant.schema_name):
        try:
            stored = ShippingMethod.objects.exists()
        except Exception:  # noqa: BLE001 — отчёт не падает на одной схеме
            stored = None
    if stored:
        return None
    area = (getattr(tenant, "delivery_area", "") or "").strip()
    return {
        "schema": tenant.schema_name,
        "name": tenant.name,
        "demo": bool(getattr(tenant, "is_demo", False)),
        "fee_cents": tenant.delivery_fee_cents,
        "zones": len(tenant.delivery_zones or []),
        "area": area[:120],
        "looks_like_parcel": bool(PARCEL_HINT.search(area)),
        "schema_missing": stored is None,
    }


class Command(BaseCommand):
    help = "Бизнесы с доставкой в прежних полях: кому предложить Paketdienst (только чтение)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="одна схема")
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--with-demo", action="store_true", help="включить демо-бизнесы")

    def handle(self, *args, **opts):
        qs = Tenant.objects.exclude(schema_name="public").order_by("schema_name")
        if opts.get("tenant"):
            qs = qs.filter(schema_name=opts["tenant"])
        rows = []
        for tenant in qs.iterator():
            if getattr(tenant, "is_demo", False) and not opts.get("with_demo"):
                continue
            row = report_for(tenant)
            if row:
                rows.append(row)
        if opts.get("json"):
            self.stdout.write(json.dumps(rows, ensure_ascii=False, indent=2))
            return
        if not rows:
            self.stdout.write("Переезжать нечего: у всех бизнесов способы доставки сохранены.")
            return
        for row in rows:
            mark = "📦?" if row["looks_like_parcel"] else "  "
            self.stdout.write(
                f"{mark} {row['schema']:<24} {row['name'][:30]:<30} "
                f"{row['fee_cents'] / 100:>6.2f} € zones={row['zones']}  {row['area']}"
            )
        parcel = sum(1 for r in rows if r["looks_like_parcel"])
        self.stdout.write(
            f"\nИтого {len(rows)}; похоже на отправку посылками — {parcel} (📦?). "
            "Ничего не изменено: способ «Versand per Paketdienst» включает владелец бизнеса "
            "в «Einstellungen › Zahlung & Lieferung»."
        )
