"""SHP-3: единственный писатель способов доставки (экран «Lieferung & Abholung» и мастер).

План `docs/ful-fulfilment-modes-plan-2026-11-09.md`. Правила:
* первое сохранение переносит прежние настройки в строки (`materialize`) — ничего не теряется;
* все суммы — `core.money.parse_amount` (тысячи/запятая; мусор — ошибка, а не 0 €), потолки
  на суммы, вес, число строк зон/весов/адресов (ревью базы SHP-1 §6);
* выключить последний способ нельзя, пока магазин принимает заказы (покупатель не смог бы
  получить заказ); удалять способы нельзя вовсе (только выключать);
* после записи — зеркало прежнего флага `Tenant.delivery_enabled` (= есть включённая
  доставка) для читателей, ещё не переведённых на список (Widerruf, «zzgl. Versand»,
  готовность, заявки) — до SHP-5.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction
from django.utils.translation import gettext as _

from apps.core.money import parse_amount, to_cents

from . import carriers, shipping
from .models import ShippingMethod

MAX_FEE_CENTS = 100_000  # 1000 € — больше почти наверняка опечатка
MAX_ROWS = 20  # строк зон / весов / пунктов самовывоза
MAX_WEIGHT_G = 1_000_000


class LastMethod(Exception):
    """Нельзя выключить последний способ получения."""


@dataclass
class Parsed:
    values: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)


def _money(post, name, label, parsed: Parsed) -> int:
    raw = (post.get(name) or "").strip()
    if not raw:
        return 0
    try:
        value = parse_amount(raw)
    except ValueError:
        value = None
        parsed.errors.append(_("%(field)s: Betrag nicht erkannt.") % {"field": label})
    cents = to_cents(value) if value is not None else 0
    if cents > MAX_FEE_CENTS:
        parsed.errors.append(_("%(field)s: höchstens 1000 €.") % {"field": label})
        return 0
    return cents


def _int(raw, *, low=1, high=MAX_WEIGHT_G):
    try:
        value = int(str(raw or "").strip())
    except (TypeError, ValueError):
        return None
    return value if low <= value <= high else None


def _kg_to_g(raw):
    """«2», «2,5», «31.5» кг → граммы; пусто/мусор → None."""
    text = str(raw or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        grams = round(float(text) * 1000)
    except ValueError:
        return None
    return grams if 0 < grams <= MAX_WEIGHT_G else None


def _lines(raw) -> list[list[str]]:
    out = []
    for line in str(raw or "").splitlines():
        if line.strip():
            out.append([part.strip() for part in line.split("|")])
        if len(out) >= MAX_ROWS:
            break
    return out


def parse(post, kind: str) -> Parsed:
    """Поля способа из POST формы (без записи). Нерелевантные типу поля игнорируются."""
    parsed = Parsed()
    v = parsed.values
    v["name"] = (post.get("name") or "").strip()[:80]
    v["delivery_time"] = (post.get("delivery_time") or "").strip()[:60]
    v["min_order_cents"] = _money(post, "min_order", _("Mindestbestellwert"), parsed)
    v["fee_cents"] = _money(post, "fee", _("Preis"), parsed)
    v["free_from_cents"] = _money(post, "free_from", _("Kostenlos ab"), parsed)
    v["area_text"] = (post.get("area_text") or "").strip()[:2000]
    if kind == ShippingMethod.KIND_PICKUP:
        v["locations"] = [
            {"name": row[0][:120], "address": (row[1] if len(row) > 1 else "")[:200]}
            for row in _lines(post.get("locations"))
            if row[0]
        ]
    if kind == ShippingMethod.KIND_COURIER:
        zones = []
        for row in _lines(post.get("zones")):
            plz = row[0][:200]
            if not plz:
                continue
            zone = {"plz": plz}
            for idx, key in ((1, "fee_cents"), (2, "free_cents"), (3, "min_cents")):
                if len(row) > idx and row[idx]:
                    try:
                        amount = parse_amount(row[idx])
                    except ValueError:
                        amount = None
                    if amount is None or to_cents(amount) > MAX_FEE_CENTS:
                        parsed.errors.append(
                            _("Liefergebiet %(plz)s: Betrag nicht erkannt.") % {"plz": plz}
                        )
                        continue
                    zone[key] = to_cents(amount)
            zones.append(zone)
        v["zones"] = zones
        v["restrict_to_zones"] = bool(post.get("restrict_to_zones"))
    if kind == ShippingMethod.KIND_CARRIER:
        carrier = (post.get("carrier") or "").strip()
        if carriers.get(carrier) is None:
            parsed.errors.append(_("Bitte einen Versanddienst wählen."))
            carrier = "other"
        v["carrier"] = carrier
        service = post.get("service") or ShippingMethod.SERVICE_HOME
        point_ok = bool(carriers.get(carrier) and carriers.get(carrier).pickup_point)
        if service == ShippingMethod.SERVICE_POINT and not point_ok:
            parsed.errors.append(_("Dieser Versanddienst hat keine Abholstellen."))
            service = ShippingMethod.SERVICE_HOME
        v["service"] = (
            service
            if service in (ShippingMethod.SERVICE_HOME, ShippingMethod.SERVICE_POINT)
            else ShippingMethod.SERVICE_HOME
        )
        pricing = post.get("pricing") or ShippingMethod.PRICING_FLAT
        v["pricing"] = (
            pricing
            if pricing in (ShippingMethod.PRICING_FLAT, ShippingMethod.PRICING_WEIGHT)
            else "flat"
        )
        tiers = []
        for row in _lines(post.get("weight_tiers")):
            grams = _kg_to_g(row[0])
            if grams is None or len(row) < 2:
                parsed.errors.append(
                    _("Gewichtsstufe „%(row)s“ nicht erkannt.") % {"row": " | ".join(row)}
                )
                continue
            try:
                amount = parse_amount(row[1])
            except ValueError:
                amount = None
            if amount is None or to_cents(amount) > MAX_FEE_CENTS:
                parsed.errors.append(
                    _("Gewichtsstufe „%(row)s“ nicht erkannt.") % {"row": " | ".join(row)}
                )
                continue
            tiers.append({"max_g": grams, "fee_cents": to_cents(amount)})
        tiers.sort(key=lambda t: t["max_g"])
        v["weight_tiers"] = tiers
        if v["pricing"] == ShippingMethod.PRICING_WEIGHT and not tiers:
            parsed.errors.append(_("Für den Preis nach Gewicht mindestens eine Stufe angeben."))
        v["packaging_g"] = _int(post.get("packaging_g"), low=0) or 0
        v["default_item_g"] = _int(post.get("default_item_g"), low=0) or 0
        v["max_weight_g"] = _kg_to_g(post.get("max_weight_kg"))
        v["max_length_cm"] = _int(post.get("max_length_cm"), high=1000)
        v["bulky_ok"] = bool(post.get("bulky_ok"))
    return parsed


def materialize(tenant) -> None:
    """Первое сохранение: перенести прежние настройки в строки (только если строк нет)."""
    if shipping.has_stored():
        return
    for method in shipping.legacy_methods(tenant):
        method._legacy = False
        method.save()
    shipping.forget(tenant)


def _orders_open(tenant) -> bool:
    try:
        return bool(tenant.is_module_active("orders") or tenant.is_module_active("jobs"))
    except Exception:  # noqa: BLE001 — неизвестно → строже (не даём выключить всё)
        return True


def mirror_legacy(tenant) -> None:
    """Зеркало прежнего флага доставки для ещё не переведённых читателей (до SHP-5)."""
    shipping.forget(tenant)
    on = any(m.kind != ShippingMethod.KIND_PICKUP for m in shipping.stored(tenant))
    if bool(getattr(tenant, "delivery_enabled", False)) != on:
        tenant.delivery_enabled = on
        tenant.save(update_fields=["delivery_enabled", "updated_at"])


@transaction.atomic
def create(tenant, kind: str, values: dict) -> ShippingMethod:
    if kind not in (
        ShippingMethod.KIND_PICKUP,
        ShippingMethod.KIND_COURIER,
        ShippingMethod.KIND_CARRIER,
    ):
        raise ValueError(kind)
    materialize(tenant)
    last = (
        ShippingMethod.objects.order_by("-sort_order").values_list("sort_order", flat=True).first()
    )
    method = ShippingMethod(kind=kind, sort_order=(last or 0) + 1)
    for key, value in values.items():
        setattr(method, key, value)
    method.save()
    mirror_legacy(tenant)
    return method


@transaction.atomic
def update(tenant, method: ShippingMethod, values: dict) -> ShippingMethod:
    for key, value in values.items():
        setattr(method, key, value)
    method.save()
    mirror_legacy(tenant)
    return method


@transaction.atomic
def set_active(tenant, method: ShippingMethod, on: bool) -> None:
    """Включить/выключить. Последний включённый способ при открытых заказах — LastMethod."""
    materialize(tenant)
    method = ShippingMethod.objects.select_for_update().get(pk=method.pk)
    if not on and method.active and _orders_open(tenant):
        others = ShippingMethod.objects.filter(active=True).exclude(pk=method.pk).exists()
        if not others:
            raise LastMethod
    method.active = bool(on)
    method.save(update_fields=["active", "updated_at"])
    mirror_legacy(tenant)


@transaction.atomic
def move(tenant, method: ShippingMethod, direction: int) -> None:
    """Сдвинуть способ вверх (-1) или вниз (+1) — порядок в корзине."""
    rows = list(ShippingMethod.objects.select_for_update().order_by("sort_order", "created_at"))
    ids = [m.pk for m in rows]
    if method.pk not in ids:
        return
    i = ids.index(method.pk)
    j = i + (1 if direction > 0 else -1)
    if not 0 <= j < len(rows):
        return
    rows[i], rows[j] = rows[j], rows[i]
    for pos, row in enumerate(rows):
        if row.sort_order != pos:
            row.sort_order = pos
            row.save(update_fields=["sort_order", "updated_at"])
    shipping.forget(tenant)
