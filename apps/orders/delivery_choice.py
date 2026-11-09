"""SH-24 → SHP-2: выбор способа получения — ОДИН источник правды для всех продажных
поверхностей (корзина, покупка по акции `/p/<uuid>/kaufen/`, принятие предложения
`/o/<token>/`).

SHP-2 (план `docs/ful-fulfilment-modes-plan-2026-11-09.md`): выбор идёт по СПИСКУ способов
бизнеса (`orders.shipping.methods`) — самовывоз, курьер по городу, транспортные компании
до двери или в пункт выдачи. Поле формы прежнее — `fulfillment`:
* у бизнеса без сохранённых способов значения прежние: `pickup` / `delivery` (форма и
  старые ссылки не меняются; замки SH-24/G4 целы);
* у сохранённых способов значение — id способа; `pickup`/`delivery` по-прежнему понятны
  (первый самовывоз / первая доставка) — устаревшая форма не ломается.

Fail-closed: способ берётся ТОЛЬКО из списка включённых способов этого бизнеса (подмена
поля чужим/выключенным id — ошибка, не тихий самовывоз); выключенный самовывоз выбрать
нельзя; цена считается заново на сервере. Тексты ошибок курьера прежние.
"""

from __future__ import annotations

import re

from django.utils.translation import gettext as _

from . import carriers, shipping
from .models import ShippingMethod

LEGACY_PICKUP, LEGACY_DELIVERY = "pickup", "delivery"
POINT_LABELS = {
    carriers.PACKSTATION: "Packstation",
    carriers.FILIALE: "Postfiliale",
    carriers.PAKETSHOP: "PaketShop",
}


class DeliveryChoice:
    """Результат разбора POST: способ получения, стоимость, адрес, снимок, ошибка."""

    __slots__ = ("delivery", "shipping_cents", "shipping_address", "error", "method", "snapshot")

    def __init__(
        self,
        *,
        delivery=False,
        shipping_cents=0,
        shipping_address="",
        error="",
        method=None,
        snapshot=None,
    ):
        self.delivery = delivery
        self.shipping_cents = shipping_cents
        self.shipping_address = shipping_address
        self.error = error
        self.method = method
        self.snapshot = snapshot or {}

    def __bool__(self) -> bool:  # «выбор пригоден» = ошибки нет
        return not self.error


def key_of(method: ShippingMethod) -> str:
    """Значение поля формы: id сохранённого способа, у прежних настроек — pickup/delivery."""
    if not shipping.is_legacy(method):
        return str(method.pk)
    return LEGACY_PICKUP if method.kind == ShippingMethod.KIND_PICKUP else LEGACY_DELIVERY


def _pick(options, raw: str):
    for m in options:
        if key_of(m) == raw:
            return m
    pickups = shipping.by_kind(options, ShippingMethod.KIND_PICKUP)
    deliveries = [m for m in options if m.kind != ShippingMethod.KIND_PICKUP]
    if raw == LEGACY_DELIVERY and deliveries:
        return deliveries[0]
    # «delivery» у бизнеса без доставки и пустое поле — самовывоз (как SH-24), если он есть
    if raw in ("", LEGACY_PICKUP, LEGACY_DELIVERY) and pickups:
        return pickups[0]
    if raw == "" and len(options) == 1:
        return options[0]
    return None


def _eur(cents: int) -> str:
    return f"{cents / 100:.2f}".replace(".", ",")


def _snapshot(method, *, parcel=None, point=None) -> dict:
    # прежние настройки: подпись «Pickup/Delivery» ничего не добавляет к виду заказа и
    # застыла бы на языке момента заказа — не пишем (ревью SHP-2)
    label = "" if shipping.is_legacy(method) else shipping.label(method)
    time = method.delivery_time_localized() if method.delivery_time and label else ""
    weight = parcel.weight_for(method) if parcel is not None else None
    snap = {
        "shipping_method_id": "" if shipping.is_legacy(method) else str(method.pk),
        "shipping_kind": method.kind,
        "shipping_carrier": method.carrier,
        "shipping_service": method.service,
        "shipping_label": f"{label} · {time}" if time else label,
        "shipping_weight_g": weight,
    }
    if point:
        snap.update(point)
    return snap


def _clean(value, limit: int) -> str:
    """Одна строка без управляющих символов (ревью безопасности SHP-2): перевод строки
    подделал бы строки адреса в карточке/накладной, NUL уронил бы запись (500)."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or "")).strip()[:limit]


def _address(post) -> tuple[str, str, str]:
    return (
        _clean(post.get("street"), 200),
        _clean(post.get("plz"), 10),
        _clean(post.get("city"), 100),
    )


def _point(post, method) -> tuple[dict | None, str, str]:
    """(поля пункта, адрес-текст, ошибка) для доставки в пункт выдачи компании."""
    carrier = carriers.get(method.carrier)
    kinds = carrier.pickup_point if carrier else ()
    kind = (post.get("point_type") or "").strip()
    if kind not in kinds:
        kind = kinds[0] if len(kinds) == 1 else ""
    ref = _clean(post.get("point_ref"), 40)
    plz = _clean(post.get("point_plz"), 10)
    city = _clean(post.get("point_city"), 100)
    postnummer = re.sub(r"\D", "", post.get("postnummer") or "")[:20]
    if not kind or not ref or not plz or not city:
        return None, "", _("Bitte geben Sie die Abholstelle an (Nummer, PLZ und Ort).")
    if kind == carriers.PACKSTATION and not 6 <= len(postnummer) <= 10:
        return None, "", _("Für die Packstation brauchen wir Ihre DHL-PostNummer.")
    lines = [f"{POINT_LABELS.get(kind, kind)} {ref}"]
    if postnummer:
        lines.append(f"PostNummer {postnummer}")
    lines.append(f"{plz} {city}")
    fields = {
        "pickup_point_type": kind,
        "pickup_point_ref": ref,
        "pickup_point_postnummer": postnummer,
    }
    return fields, "\n".join(lines), ""


def resolve(post, tenant, subtotal_cents: int, parcel=None) -> DeliveryChoice:
    """Разобрать выбор способа из POST (см. модуль). ``parcel`` — профиль посылки
    корзины (`shipping.parcel_for`); None — без проверок веса/размеров."""
    options = shipping.methods(tenant)
    method = _pick(options, (post.get("fulfillment") or "").strip())
    if method is None:
        return DeliveryChoice(error=_("Bitte wählen Sie, wie Sie die Bestellung erhalten möchten."))
    if method.kind == ShippingMethod.KIND_PICKUP:
        quote = shipping.quote(method, subtotal_cents, parcel=parcel)
        if quote["min_cents"] and subtotal_cents < quote["min_cents"]:
            return DeliveryChoice(
                error=_("Minimum order for pickup is %(min)s €.")
                % {"min": _eur(quote["min_cents"])}
            )
        return DeliveryChoice(method=method, snapshot=_snapshot(method, parcel=parcel))

    point = None
    if method.service == ShippingMethod.SERVICE_POINT:
        point, address, error = _point(post, method)
        if error:
            return DeliveryChoice(error=error)
        plz = point and _clean(post.get("point_plz"), 10)
    else:
        street, plz, city = _address(post)
        if not (street and plz and city):
            return DeliveryChoice(error=_("Please enter your full delivery address."))
        address = f"{street}\n{plz} {city}"
    quote = shipping.quote(method, subtotal_cents, plz or "", parcel=parcel)
    if not quote["deliverable"]:
        if method.kind == ShippingMethod.KIND_COURIER:
            return DeliveryChoice(
                error=_("Sorry, we don't deliver to postal code %(plz)s.") % {"plz": plz}
            )
        return DeliveryChoice(
            error=_("Diese Versandart ist für Ihre Bestellung leider nicht möglich.")
        )
    if quote["min_cents"] and subtotal_cents < quote["min_cents"]:
        return DeliveryChoice(
            error=_("Minimum order for delivery is %(min)s €.") % {"min": _eur(quote["min_cents"])}
        )
    return DeliveryChoice(
        delivery=True,
        shipping_cents=quote["fee_cents"],
        shipping_address=address,
        method=method,
        snapshot=_snapshot(method, parcel=parcel, point=point),
    )


def _option(method, subtotal_cents: int, parcel) -> dict | None:
    quote = shipping.quote(method, subtotal_cents, parcel=parcel)
    if not quote["deliverable"] and method.kind != ShippingMethod.KIND_COURIER:
        return None  # не влезает/неизвестен вес/Sperrgut — не предлагаем (никогда 0 €)
    # показ — сбор ДО порога «frei ab» (порог применяет JS/сервер к итогу); у цены по весу
    # — сбор за вес этой корзины
    base = shipping.quote(method, 0, parcel=parcel)
    fee = base["fee_cents"] if base["deliverable"] else method.fee_cents
    carrier = carriers.get(method.carrier)
    point = method.kind == ShippingMethod.KIND_CARRIER and (
        method.service == ShippingMethod.SERVICE_POINT
    )
    kinds = list(carrier.pickup_point) if (point and carrier) else []
    return {
        "key": key_of(method),
        "kind": method.kind,
        "label": shipping.label(method),
        "time": method.delivery_time_localized() if method.delivery_time else "",
        "fee_cents": fee,
        "fee_eur": f"{fee / 100:.2f}",
        # показ в списке — по-немецки, с запятой («3,99 €»)
        "fee_text": _eur(fee),
        "free_text": _eur(method.free_from_cents),
        "free_cents": method.free_from_cents,
        "free_eur": f"{method.free_from_cents / 100:.2f}",
        "min_cents": method.min_order_cents,
        "min_eur": f"{method.min_order_cents / 100:.2f}",
        "needs_address": method.kind != ShippingMethod.KIND_PICKUP and not point,
        "point": point,
        "point_types": [(k, POINT_LABELS.get(k, k)) for k in kinds],
        "needs_postnummer": carriers.PACKSTATION in kinds,
        "finder": carrier.finder if (point and carrier) else "",
        "area": method.area_text,
        "locations": method.locations if method.kind == ShippingMethod.KIND_PICKUP else [],
    }


def context(tenant, subtotal_cents: int = 0, parcel=None) -> dict:
    """Данные для партиала `storefront/_fulfillment_choice.html`.

    ``shipping_options`` — включённые способы, которые подходят корзине (слишком тяжёлое/
    громоздкое/без веса — не предлагается). Прежние ключи (`delivery_enabled`, сбор/порог/
    минимум первой доставки) остаются для частей корзины, что их читают (подсказка «ещё X €
    до бесплатной доставки», итог)."""
    if tenant is None:
        return {"delivery_enabled": False, "shipping_options": []}
    options = [
        o for o in (_option(m, subtotal_cents, parcel) for m in shipping.methods(tenant)) if o
    ]
    deliveries = [o for o in options if o["kind"] != ShippingMethod.KIND_PICKUP]
    ctx = {
        "shipping_options": options,
        "delivery_enabled": bool(deliveries),
        "has_pickup": any(o["kind"] == ShippingMethod.KIND_PICKUP for o in options),
        # способы есть, но ни один не берёт эту корзину (вес/размер/Sperrgut) — честно сказать
        "no_shipping_possible": not options,
    }
    if deliveries:
        first = deliveries[0]
        ctx.update(
            {
                "delivery_fee_cents": first["fee_cents"],
                "delivery_fee_eur": first["fee_eur"],
                "delivery_free_cents": first["free_cents"],
                "delivery_free_eur": first["free_eur"],
                "delivery_min_cents": first["min_cents"],
                "delivery_min_eur": first["min_eur"],
            }
        )
    return ctx
