"""Универсальный движок Extras (#7): доп-услуги к брони на все архетипы.

Extra (apps.core.models) задаётся бизнесом со scope (stays/booking/events/all).
Гость отмечает Extras при бронировании → снимок [{label, price_cents}] кладётся
в JSON-поле брони, сумма идёт в total и finance. Снимок переживает изменение/
удаление Extra (исторические брони неизменны).
"""


def active_for(scope, *, entity_kind="", entity_id=""):
    """Активные Extras, применимые к архетипу scope (+ scope=all).

    MX-2: адресность — scope-wide (entity_kind="") ∪ опции ИМЕННО этой сущности.
    Без entity_kind поведение прежнее: адресные чужих сущностей не показываются
    (иначе «аренда байка» всплыла бы у каждого события тенанта — дефект D3)."""
    from django.db.models import Q

    from .models import Extra

    qs = Extra.objects.filter(is_active=True).filter(scope__in=[scope, Extra.SCOPE_ALL])
    if entity_kind and entity_id:
        qs = qs.filter(Q(entity_kind="") | Q(entity_kind=entity_kind, entity_id=str(entity_id)))
    else:
        qs = qs.filter(entity_kind="")
    return list(qs.order_by("sort_order", "label"))


def snapshot(ids, scope, *, nights=1, entity_kind="", entity_id=""):
    """Снимок выбранных Extras по их id → [{id, label, price_cents, unit_cents, per_night}].

    nights — множитель для per_night-позиций (stays); price_cents — итог строки
    (unit_cents × ночи), потребители суммы не меняются. `id`/`unit_cents`/`per_night`
    (MX-0) нужны сводному учёту доп-продаж и честному пересчёту при переносе дат;
    старые снимки без этих ключей остаются валидными (total_cents/retotal fail-safe).
    Чужой scope/неактивные/мусорные id игнорируются (защита от подмены формы)."""
    if not ids:
        return []
    wanted = {str(i) for i in ids}
    out = []
    for extra in active_for(scope, entity_kind=entity_kind, entity_id=entity_id):
        if str(extra.pk) in wanted:
            mult = max(1, int(nights)) if extra.per_night else 1
            out.append(
                {
                    "id": str(extra.pk),
                    "label": extra.label,
                    "price_cents": extra.price_cents * mult,
                    "unit_cents": extra.price_cents,
                    "per_night": extra.per_night,
                    # DC-8: ставка НДС допа в снимке (завтрак 19 % рядом с
                    # проживанием 7 % — Aufteilungsgebot). None = ставка сделки.
                    "vat_rate": str(extra.vat_rate) if extra.vat_rate is not None else None,
                }
            )
    return out


def retotal(snap, *, nights):
    """MX-0: пересчитать per-night строки снимка под НОВОЕ число ночей.

    Продление брони 2→5 ночей обязано пересчитать «завтрак ×ночь», иначе итог
    врёт (доказано тестом: 530 € вместо 575 €). Пересчитываются только строки,
    несущие unit_cents+per_night (снимки после MX-0); легаси-строки без этих
    ключей возвращаются как есть — цена не угадывается задним числом."""
    mult = max(1, int(nights))
    out = []
    for e in snap or []:
        if not isinstance(e, dict):
            continue
        if e.get("per_night") and isinstance(e.get("unit_cents"), int):
            e = {**e, "price_cents": e["unit_cents"] * mult}
        out.append(e)
    return out


def total_cents(snap) -> int:
    """Сумма снимка Extras (центы)."""
    return sum(int(e.get("price_cents", 0)) for e in (snap or []))
