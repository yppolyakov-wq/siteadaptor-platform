"""SHP-1: единый читатель способов получения заказа.

План `docs/ful-fulfilment-modes-plan-2026-11-09.md`. Все, кто спрашивает «как бизнес отдаёт
товар и сколько это стоит» (корзина, покупка по акции, предложение, готовность, страница
«/versand/», фиды), читают ЗДЕСЬ, а не поля Tenant.

Переход без смены поведения: пока у бизнеса нет ни одной строки `ShippingMethod`, способы
строятся в памяти из прежних полей Tenant (самовывоз — всегда; курьер — при
`delivery_enabled`), и `quote` курьера считает ровно как `services.delivery_quote` (замок
паритета). Строки появляются, когда владелец сохраняет способы на новом экране (SHP-3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.db import connection
from django.utils.translation import gettext_lazy as _

from . import carriers
from .models import ShippingMethod

_NONE = {"deliverable": False, "fee_cents": 0, "min_cents": 0, "free_cents": 0}


@dataclass(frozen=True)
class Parcel:
    """SHP-1b: профиль посылки корзины. ``known_g`` — сумма веса позиций с весом,
    ``unknown_qty`` — штук без веса (их вес даёт способ: ``default_item_g``),
    ``longest_cm`` — самая длинная сторона среди позиций С размерами (позиция без
    размеров считается влезающей — длинные товары владелец размечает), ``bulky`` — есть
    Sperrgut."""

    known_g: int = 0
    unknown_qty: int = 0
    longest_cm: int = 0
    bulky: bool = False

    def weight_for(self, method) -> int | None:
        """Вес посылки для способа (с упаковкой) или None — вес не определить."""
        if self.unknown_qty and not method.default_item_g:
            return None
        return (
            self.known_g
            + self.unknown_qty * int(method.default_item_g or 0)
            + int(method.packaging_g or 0)
        )


def parcel_for(items) -> Parcel:
    """SHP-1b: профиль посылки из позиций корзины ``[(product, variant|None, qty), …]``.

    Вес: вариант → товар → неизвестно (считается в ``unknown_qty``). Длинная сторона —
    по размерам товара. Sperrgut — флажок товара."""
    known = unknown = longest = 0
    bulky = False
    for product, variant, qty in items:
        qty = max(0, int(qty or 0))
        if not qty or product is None:
            continue
        weight = getattr(variant, "shipping_weight_g", None) if variant is not None else None
        if weight is None:
            weight = getattr(product, "shipping_weight_g", None)
        if weight is None:
            unknown += qty
        else:
            known += int(weight) * qty
        sides = [getattr(product, f, None) or 0 for f in ("length_cm", "width_cm", "height_cm")]
        longest = max(longest, *sides)
        bulky = bulky or bool(getattr(product, "bulky", False))
    return Parcel(known_g=known, unknown_qty=unknown, longest_cm=longest, bulky=bulky)


def _rows(tenant) -> list[ShippingMethod] | None:
    """Все строки способов схемы ``tenant`` (одним запросом, мемо на объекте тенанта) или
    None — читать таблицу нельзя: соединение не в схеме этого бизнеса (public, beat,
    агрегатор) — тогда честно прежние настройки, а не чужие строки и не ошибка SQL."""
    schema = getattr(connection, "schema_name", "") or ""
    own = getattr(tenant, "schema_name", None)
    if schema == "public":
        # в проде таблицы способов в public нет (TENANT-апп); в тестах все таблицы там
        if not _table_in_public():
            return None
    elif own is not None and own != schema:
        return None
    cached = getattr(tenant, "_shipping_rows", None)
    if cached is None:
        cached = list(ShippingMethod.objects.all())
        try:
            tenant._shipping_rows = cached
        except Exception:  # noqa: BLE001 — неизменяемый тенант: без мемо
            pass
    return cached


_PUBLIC_TABLE: list[bool] = []


def _table_in_public() -> bool:
    """Есть ли таблица способов в public (один раз на процесс): нет в проде, есть в тестах."""
    if not _PUBLIC_TABLE:
        _PUBLIC_TABLE.append(
            ShippingMethod._meta.db_table in connection.introspection.table_names()
        )
    return _PUBLIC_TABLE[0]


def forget(tenant) -> None:
    """Сбросить мемо после записи способов (писатель экрана SHP-3)."""
    try:
        tenant.__dict__.pop("_shipping_rows", None)
    except Exception:  # noqa: BLE001
        pass


def stored(tenant, *, active_only: bool = True) -> list[ShippingMethod]:
    """Сохранённые способы схемы (без перехода на прежние поля)."""
    rows = _rows(tenant) or []
    return [m for m in rows if m.active] if active_only else list(rows)


def is_legacy(method) -> bool:
    """Способ построен из прежних полей Tenant (не строка таблицы)."""
    return bool(getattr(method, "_legacy", False))


def legacy_methods(tenant) -> list[ShippingMethod]:
    """Способы из прежних полей Tenant — НЕ сохраняются (`_state.adding`)."""
    out = [
        ShippingMethod(
            kind=ShippingMethod.KIND_PICKUP,
            locations=list(getattr(tenant, "pickup_points", None) or []),
            min_order_cents=int(getattr(tenant, "pickup_min_cents", 0) or 0),
            sort_order=0,
        )
    ]
    if getattr(tenant, "delivery_enabled", False):
        out.append(
            ShippingMethod(
                kind=ShippingMethod.KIND_COURIER,
                fee_cents=int(getattr(tenant, "delivery_fee_cents", 0) or 0),
                free_from_cents=int(getattr(tenant, "delivery_free_cents", 0) or 0),
                min_order_cents=int(getattr(tenant, "delivery_min_cents", 0) or 0),
                zones=list(getattr(tenant, "delivery_zones", None) or []),
                restrict_to_zones=bool(getattr(tenant, "delivery_restrict_to_zones", False)),
                area_text=getattr(tenant, "delivery_area", "") or "",
                sort_order=1,
            )
        )
    for method in out:
        method._legacy = True
    return out


def methods(tenant, *, active_only: bool = True) -> list[ShippingMethod]:
    """Способы бизнеса в порядке владельца: сохранённые, иначе прежние настройки.

    Строки есть (даже все выключены) — действуют только они: выключить всё может лишь
    писатель, а он этого не допускает (SHP-3). Строк нет — прежние поля Tenant."""
    rows = _rows(tenant)
    if not rows:
        return legacy_methods(tenant)
    if not active_only:
        return list(rows)
    # решение владельца: самовывоз — ОДИН способ со списком адресов; лишние строки
    # самовывоза не предлагаются (иначе выбор адреса относился бы не к тому способу)
    out, pickup_seen = [], False
    for m in rows:
        if not m.active:
            continue
        if m.kind == ShippingMethod.KIND_PICKUP:
            if pickup_seen:
                continue
            pickup_seen = True
        out.append(m)
    return out


def by_kind(items, kind: str) -> list[ShippingMethod]:
    return [m for m in items if m.kind == kind]


def label(method: ShippingMethod) -> str:
    """Подпись способа для покупателя: имя владельца, иначе по типу и компании."""
    own = method.name_localized()
    if own:
        return own
    if is_legacy(method):
        # прежние настройки (строк нет): подписи, что покупатель видел до SHP — «Abholung» /
        # «Lieferung» (доставка тогда значила и курьера, и посылку)
        return str(_("Pickup") if method.kind == ShippingMethod.KIND_PICKUP else _("Delivery"))
    if method.kind == ShippingMethod.KIND_CARRIER:
        carrier = carriers.get(method.carrier)
        name = str(carrier.name) if carrier else str(_("Versand"))
        if method.service == ShippingMethod.SERVICE_POINT:
            return str(_("%(carrier)s an eine Abholstelle") % {"carrier": name})
        return str(_("Versand mit %(carrier)s") % {"carrier": name})
    return str(method.get_kind_display())


def _zone(zones, plz: str):
    """Зона с самым длинным совпавшим PLZ-префиксом (как `services._zone_for_plz`)."""
    from .services import _plz_prefixes  # лениво: services позже позовёт этот модуль

    digits = re.sub(r"\D", "", str(plz or ""))
    best, best_len = None, -1
    for zone in zones or []:
        if not isinstance(zone, dict):
            continue
        for prefix in _plz_prefixes(zone.get("plz", "")):
            if digits and digits.startswith(prefix) and len(prefix) > best_len:
                best, best_len = zone, len(prefix)
    return best


def _int(value, fallback: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return fallback


def weight_fee(method: ShippingMethod, weight_g: int) -> int | None:
    """Цена по весу: первая строка, где вес ≤ max_g; тяжелее всех строк — None."""
    tiers = []
    for row in method.weight_tiers or []:
        if isinstance(row, dict) and _int(row.get("max_g"), 0) > 0:
            tiers.append((_int(row.get("max_g"), 0), _int(row.get("fee_cents"), 0)))
    for max_g, fee in sorted(tiers):
        if weight_g <= max_g:
            return fee
    return None


def quote(method: ShippingMethod, subtotal_cents: int, plz: str = "", *, parcel=None) -> dict:
    """{deliverable, fee_cents, min_cents, free_cents} способа для корзины.

    Курьер — зоны PLZ (зона переопределяет сбор/порог/минимум; при «только в зонах» без
    совпадения — недоступен); Paketdienst — плоская цена или по весу (вес не определить или
    тяжелее последней строки — недоступен, никогда не 0 €). Ограничения веса/длины и Sperrgut
    (кроме способов `bulky_ok`) скрывают курьера и Paketdienst; самовывоз их не знает.
    «frei ab» обнуляет сбор. ``parcel`` — `Parcel` корзины (None — без проверок веса)."""
    if method.kind == ShippingMethod.KIND_PICKUP:
        fee = int(method.fee_cents or 0)
        free = int(method.free_from_cents or 0)
        if free and subtotal_cents >= free:
            fee = 0
        return {
            "deliverable": True,
            "fee_cents": fee,
            "min_cents": int(method.min_order_cents or 0),
            "free_cents": free,
        }
    weight = parcel.weight_for(method) if parcel is not None else None
    if parcel is not None:
        if parcel.bulky and not method.bulky_ok:
            return dict(_NONE)
        # вес не определить, а предел задан — честно «не предлагаем» (никогда наугад)
        if method.max_weight_g and (weight is None or weight > method.max_weight_g):
            return dict(_NONE)
        if method.max_length_cm and parcel.longest_cm > method.max_length_cm:
            return dict(_NONE)
    fee = int(method.fee_cents or 0)
    free = int(method.free_from_cents or 0)
    minimum = int(method.min_order_cents or 0)
    if method.kind == ShippingMethod.KIND_COURIER:
        zone = _zone(method.zones, plz)
        if zone is None and method.zones and method.restrict_to_zones:
            return dict(_NONE)
        if zone is not None:
            if zone.get("fee_cents") not in (None, ""):
                fee = _int(zone["fee_cents"], fee)
            if zone.get("free_cents") not in (None, ""):
                free = _int(zone["free_cents"], free)
            if zone.get("min_cents") not in (None, ""):
                minimum = _int(zone["min_cents"], minimum)
    elif method.pricing == ShippingMethod.PRICING_WEIGHT:
        if weight is None:
            return dict(_NONE)
        tier_fee = weight_fee(method, weight)
        if tier_fee is None:
            return dict(_NONE)
        fee = tier_fee
    if free and subtotal_cents >= free:
        fee = 0
    return {"deliverable": True, "fee_cents": fee, "min_cents": minimum, "free_cents": free}
