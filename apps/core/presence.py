"""LS-2 «Jetzt erreichbar»: живое присутствие бизнеса для мгновенного видео-звонка.

Режимы (site_config["presence"]["mode"], presence-minimal — нет ключа = auto):
auto — по часам работы (Tenant.opening_hours_structured, тот же источник, что
бейдж «Jetzt geöffnet»); on/off — ручной override владельца. Бейдж на витрине —
это CTA wa.me-видеозвонка (LS-1), поэтому без Tenant.whatsapp_number он не
показывается ни в одном режиме. План: docs/ls2-jetzt-erreichbar-plan-2026-07-19.md.
"""

from django.utils import timezone


def mode(tenant) -> str:
    """ "auto" | "on" | "off" — из site_config (мусор → auto)."""
    cfg = getattr(tenant, "site_config", None) or {}
    raw = cfg.get("presence") if isinstance(cfg, dict) else None
    value = raw.get("mode") if isinstance(raw, dict) else None
    return value if value in ("on", "off") else "auto"


def available_now(tenant) -> bool:
    """Доступен ли бизнес прямо сейчас (без учёта номера — чистое присутствие).

    auto: открыт по структурным часам; часов нет → недоступен (владелец без
    часов включает режим on вручную).
    """
    m = mode(tenant)
    if m == "off":
        return False
    if m == "on":
        return True
    from apps.tenants import openinghours

    status = openinghours.open_status(
        getattr(tenant, "opening_hours_structured", None), timezone.localtime()
    )
    return bool(status and status.get("open"))
