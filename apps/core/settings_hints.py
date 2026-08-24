"""SR-5 (R5c A+B, решение владельца «делаем оба»): живые подписи экранов
настроек — ОДИН слой для подменю сайдбара (вариант А) и страницы-обзора
`/dashboard/einstellungen/` (вариант Б).

Бюджет: подписи считаются на КАЖДЫЙ рендер сайдбара → только чтение полей уже
загруженного тенанта + site_config + вычисления в памяти; единственный запрос —
count(Membership). Всё под fail-safe: упавший источник даёт статичную подпись
(""), а не 500 (паттерн digest._safe).
"""

from __future__ import annotations

from django.utils.translation import gettext as _
from django.utils.translation import ngettext


def _safe(fn, default=""):
    try:
        return fn()
    except Exception:  # noqa: BLE001 — подпись не роняет сайдбар
        return default


def _languages(tenant) -> str:
    locs = list(tenant.active_locales)
    if len(locs) <= 1:
        return _("Nur Deutsch")
    n = len(locs) - 1
    return _("Deutsch + %(n)s weitere") % {"n": n}


def _team(tenant) -> str:
    from apps.core.models import Membership

    n = Membership.objects.count()
    if not n:
        return ""
    return ngettext("%(n)s Mitglied", "%(n)s Mitglieder", n) % {"n": n}


def _payments(tenant) -> str:
    parts = []
    if tenant.payments_enabled:
        parts.append("Stripe")
    if tenant.vorkasse_enabled and tenant.bank_iban:
        parts.append(_("Vorkasse"))
    if not parts:
        return _("Zahlung vor Ort")
    if getattr(tenant, "delivery_enabled", False):
        parts.append(_("Lieferung"))
    return ", ".join(str(p) for p in parts)


def _notifications(tenant) -> str:
    from apps.telegram.notify import owner_chat_id

    # владельцу важно видеть, ЧТО подключено; матрицу событий не пересчитываем
    channels = [_("E-Mail")]
    if _safe(lambda: bool(owner_chat_id(tenant)), False):
        channels.append("Telegram")
    return " + ".join(str(c) for c in channels)


def _integrations(tenant) -> str:
    ok, warn = [], []
    (ok if tenant.payments_enabled else warn).append("Stripe")
    from apps.telegram.notify import owner_chat_id

    (ok if _safe(lambda: bool(owner_chat_id(tenant)), False) else warn).append("Telegram")
    if getattr(tenant, "google_place_id", ""):
        ok.append("Google")
    if not ok:
        return ""
    return " · ".join(f"{name} ●" for name in ok)


def _modules(tenant) -> str:
    from apps.core import modules

    n = len(modules.active_modules(tenant))
    return _("%(n)s Module aktiv") % {"n": n}


def _billing(tenant) -> str:
    status = tenant.subscription_status or ""
    if status == "trial":
        return _("Testphase")
    if status == "active":
        return _("Aktiv")
    return ""


def _finder(tenant) -> str:
    cfg = (tenant.site_config or {}).get("finder") or {}
    if not cfg.get("enabled"):
        return ""
    n = len(cfg.get("questions") or [])
    if not n:
        return _("Aktiv")
    return _("Aktiv · %(n)s Fragen") % {"n": n}


# url_name записи настроек → функция подписи. Ключей нет = статичное описание
# (ничего не рисуем — имени пункта достаточно).
_HINTS = {
    "languages": _languages,
    "team": _team,
    "payment-settings": _payments,
    "notifications-settings": _notifications,
    "integrations-home": _integrations,
    "modules": _modules,
    "billing": _billing,
    "finder-settings": _finder,
}


def hints_for(tenant) -> dict[str, str]:
    """{url_name: живая подпись} для записей настроек; пустые значения выкинуты."""
    if tenant is None:
        return {}
    out = {}
    for url_name, fn in _HINTS.items():
        val = _safe(lambda f=fn: f(tenant))
        if val:
            out[url_name] = str(val)
    return out
