"""Универсальный движок Extras (#7): доп-услуги к брони на все архетипы.

Extra (apps.core.models) задаётся бизнесом со scope (stays/booking/events/all).
Гость отмечает Extras при бронировании → снимок [{label, price_cents}] кладётся
в JSON-поле брони, сумма идёт в total и finance. Снимок переживает изменение/
удаление Extra (исторические брони неизменны).
"""


def active_for(scope):
    """Активные Extras, применимые к архетипу scope (+ scope=all)."""
    from .models import Extra

    return list(
        Extra.objects.filter(is_active=True)
        .filter(scope__in=[scope, Extra.SCOPE_ALL])
        .order_by("sort_order", "label")
    )


def snapshot(ids, scope, *, nights=1):
    """Снимок выбранных Extras по их id → [{label, price_cents}].

    nights — множитель для per_night-позиций (stays). Чужой scope/неактивные/
    мусорные id игнорируются (защита от подмены формы)."""
    if not ids:
        return []
    wanted = {str(i) for i in ids}
    out = []
    for extra in active_for(scope):
        if str(extra.pk) in wanted:
            mult = max(1, int(nights)) if extra.per_night else 1
            out.append({"label": extra.label, "price_cents": extra.price_cents * mult})
    return out


def total_cents(snap) -> int:
    """Сумма снимка Extras (центы)."""
    return sum(int(e.get("price_cents", 0)) for e in (snap or []))
