"""AIS W4-5a: «Verkauf öffnen» — короткие вопросы по направлению вместо форм.

План — docs/ais-w4-5-verkauf-oeffnen-plan-2026-11-06.md (+ правки architect). Правила:
* каждый вопрос пишет УЗКИМ писателем (только своё поле; частичный POST ничего не стирает);
* правда — данные: «да» видно по самой настройке; отметка `site_config["verkauf"]["no"]`
  хранит только ответ «нет» со значением по умолчанию — чтобы не спрашивать снова. Отметка
  НИКОГДА не делает пункт готовности выполненным (`readiness` смотрит только данные);
* отметки пишет один писатель `_mark` под `select_for_update`;
* вопрос, на который нельзя ответить здесь (нет IBAN), показывает ссылку, а не переключатель.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

YES, NO = "ja", "nein"
PERM = "einstellungen.edit"


@dataclass(frozen=True)
class Question:
    key: str
    direction: str
    label: str
    yes: str
    no: str
    current: Callable  # (tenant) -> bool
    write: Callable  # (tenant, on: bool) -> None
    applies: Callable = lambda t: True
    #: ответить здесь нельзя — нужна ссылка на экран (тогда без переключателя)
    blocked: Callable = lambda t: ""
    more_url: str = ""
    more_label: str = ""
    note: Callable = lambda t: ""


def _orders(t) -> bool:
    return bool(t.is_module_active("orders"))  # сбой — строка «konnte nicht geladen werden»


def _delivery_write(t, on):
    from apps.orders.views import set_delivery_enabled

    set_delivery_enabled(t, on)


def _vorkasse_write(t, on):
    from apps.orders.views import set_vorkasse_enabled

    set_vorkasse_enabled(t, on)


def _delivery_note(t) -> str:
    if not getattr(t, "delivery_enabled", False):
        return ""
    zones = bool(getattr(t, "delivery_zones", None))
    fee = int(getattr(t, "delivery_fee_cents", 0) or 0)
    # вне зон действует общий сбор (`orders.services.delivery_quote`): 0 € без ограничения
    # по зонам = бесплатно везде, даже если зоны есть
    if not fee and not (zones and getattr(t, "delivery_restrict_to_zones", False)):
        return str(_("Lieferung ist derzeit überall kostenlos — Gebiete und Gebühren festlegen."))
    return ""


def _vorkasse_blocked(t) -> str:
    if getattr(t, "bank_iban", ""):
        return ""
    return str(_("Zuerst die Bankverbindung eintragen (nur Inhaber)."))


QUESTIONS: tuple[Question, ...] = (
    Question(
        "waren.delivery",
        "waren",
        _("Liefern Sie auch?"),
        _("Ja, ich liefere"),
        _("Nein, nur Abholung"),
        current=lambda t: bool(getattr(t, "delivery_enabled", False)),
        write=_delivery_write,
        applies=_orders,
        more_url="payment-settings",
        more_label=_("Liefergebiete und Gebühren"),
        note=_delivery_note,
    ),
    Question(
        "waren.vorkasse",
        "waren",
        _("Vorkasse per Überweisung anbieten?"),
        _("Ja, Vorkasse anbieten"),
        _("Nein"),
        current=lambda t: bool(getattr(t, "vorkasse_enabled", False)),
        write=_vorkasse_write,
        applies=_orders,
        blocked=_vorkasse_blocked,
        more_url="payment-settings",
        more_label=_("Zahlarten und Bankverbindung"),
    ),
)
BY_KEY = {q.key: q for q in QUESTIONS}


def _marks(tenant) -> set[str]:
    raw = (getattr(tenant, "site_config", None) or {}).get("verkauf") or {}
    return set(raw.get("no") or []) if isinstance(raw, dict) else set()


def state(tenant, q: Question) -> str:
    """yes | no | open — «да» по данным, «нет» по отметке (данные всё равно сильнее)."""
    if q.current(tenant):
        return YES
    return NO if q.key in _marks(tenant) else "open"


def questions_for(request, direction: str = "") -> list[dict]:
    from apps.core import assistant

    tenant = request.tenant
    out = []
    for q in QUESTIONS:
        if direction and q.direction != direction:
            continue
        try:
            if not q.applies(tenant):
                continue
            blocked = q.blocked(tenant)
            row = {
                "key": q.key,
                "anchor": anchor(q.key),
                "direction": q.direction,
                "label": q.label,
                "yes": q.yes,
                "no": q.no,
                "state": state(tenant, q),
                "blocked": blocked,
                "note": q.note(tenant),
                "more": assistant.link(request, q.more_url) if q.more_url else None,
                "more_label": q.more_label,
            }
        except Exception:  # noqa: BLE001 — сломанный вопрос не роняет экран, но и не прячется
            logger.exception("sell question %s failed", q.key)
            row = {"key": q.key, "anchor": anchor(q.key), "label": q.label, "state": "error"}
        out.append(row)
    return out


def anchor(key: str) -> str:
    return "q-" + key.replace(".", "-")


def open_count(request, direction: str = "") -> int:
    return sum(1 for q in questions_for(request, direction) if q["state"] == "open")


class AnswerError(Exception):
    pass


def answer(request, key: str, choice: str) -> None:
    """Записать ответ. Бросает AnswerError — неизвестный вопрос, нет права, ответ здесь
    невозможен (тогда ничего не записано)."""
    from apps.core.permissions import has_perm

    q = BY_KEY.get(key)
    if q is None or choice not in (YES, NO):
        raise AnswerError("unknown")
    tenant = request.tenant
    if not has_perm(request.user, PERM) or not q.applies(tenant):
        raise AnswerError("forbidden")
    on = choice == YES
    if on and q.blocked(tenant):  # «нет» безопасно всегда — его можно ответить и без IBAN
        raise AnswerError("blocked")
    from django.db import transaction

    from apps.core import readiness

    with transaction.atomic():  # тумблер и отметка — вместе или никак
        q.write(tenant, on)
        _mark(tenant, key, no=not on)
    readiness.invalidate(tenant)


def _mark(tenant, key: str, *, no: bool) -> None:
    """Единственный писатель `site_config["verkauf"]` — из ЗАБЛОКИРОВАННОЙ строки (вторая
    вкладка мастера не затрёт отметку, отметка не затрёт её)."""
    from django.db import transaction

    with transaction.atomic():
        locked = type(tenant).objects.select_for_update().get(pk=tenant.pk)
        cfg = dict(locked.site_config or {})
        marks = [k for k in ((cfg.get("verkauf") or {}).get("no") or []) if k != key]
        if no:
            marks.append(key)
        if marks:
            cfg["verkauf"] = {"no": marks}
        else:
            cfg.pop("verkauf", None)
        locked.site_config = cfg
        locked.auto_create_schema = False
        locked.save(update_fields=["site_config", "updated_at"])
    tenant.site_config = cfg
