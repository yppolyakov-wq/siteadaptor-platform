"""KA-12 GA-1 (Gastro): правила онлайн-брони столов.

Сегодня любая онлайн-бронь стола ждёт подтверждения владельца, а компания любого
размера бронируется одним кликом. Ресторану нужны три исхода по числу гостей:

- **INSTANT** — до `instant_max` гостей: бронь подтверждена сразу;
- **REQUEST** — до `online_max`: «Gruppenanfrage», держит места как обычная
  ожидающая бронь, подтверждает только владелец (оплата депозита — нет);
- **CALL** — больше `online_max`: брони нет, гостя просят позвонить/написать.

Правило хранится в `site_config["booking"]["tables"]` (presence-minimal): без него
поведение прежнее — всё запрос, без лимита. Действует только для ресурсов типа
«Tisch» и только на витрине: ручная запись со стойки и поток услуг (friseur и т.п.)
не затрагиваются. Снимок «большая компания» — `Booking.is_large_party`: вебхук и
beat работают без живого конфига.
"""

INSTANT = "instant"
REQUEST = "request"
CALL = "call"


def rules(tenant) -> dict:
    """Нормализованное правило столов ({} — правила нет)."""
    from apps.tenants import siteconfig

    cfg = getattr(tenant, "site_config", None)
    booking = cfg.get("booking") if isinstance(cfg, dict) else None
    return siteconfig.normalize_booking(booking).get("tables") or {}


def decide(tenant, resource, party: int) -> str | None:
    """Исход онлайн-брони стола; None — правило не действует (прежнее поведение)."""
    from .models import Resource

    if getattr(resource, "type", "") != Resource.TYPE_TABLE:
        return None
    rule = rules(tenant)
    if not rule:
        return None
    if party > rule["online_max"]:
        return CALL
    if party <= rule["instant_max"]:
        return INSTANT
    return REQUEST


def online_max(tenant, resource) -> int:
    """Верхняя граница поля «Gäste» на витрине (50 — прежний предел)."""
    from .models import Resource

    if getattr(resource, "type", "") != Resource.TYPE_TABLE:
        return 50
    return rules(tenant).get("online_max", 50)


def resource_requires_confirm(resource) -> bool:
    """Ресурс настроен «Manuell bestätigen» (анти-фрод владельца)."""
    return bool(getattr(resource, "require_manual_confirm", False))


def needs_manual_confirm(booking) -> bool:
    """Единственная точка «подтверждает только владелец»: ресурс так настроен или
    бронь — Gruppenanfrage. Оплата депозита/Mehrfachkarte такую бронь не подтверждает."""
    return resource_requires_confirm(getattr(booking, "resource", None)) or bool(
        getattr(booking, "is_large_party", False)
    )
