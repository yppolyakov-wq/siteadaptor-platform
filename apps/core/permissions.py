"""KA-12 E6.7: права сотрудников — единый реестр и проверка.

План — docs/ka-12-e6-7-staff-permissions-plan-2026-10-25.md (редакция 2). Ключ вида
``<раздел>.<действие>``. Роли остаются три (owner/admin/staff); у owner всё.
Inhaber-Vorbehalt (Abo, Recht/Impressum, IBAN, владение, удаление бизнеса, импорт с
чужого сайта) — НЕ права: он остаётся на ``roles.is_owner`` и не выдаётся никому.

E6.7a: только пресеты ролей — ровно сегодняшний доступ (паритет держит
``tests/test_perm_parity.py``). Хранение выданных прав (core/0013), подписи для экрана
прав и выдача администратором — следующие шаги (E6.7c/d).
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .models import Membership

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Perm:
    key: str
    group: str
    requires: tuple = ()
    sensitive: bool = False  # 🔒 в UI; выдаёт только владелец (ревью §15.10)


def _p(key, group, requires=(), sensitive=False):
    return Perm(key, group, tuple(requires), sensitive)


_ALL = (
    # Verkäufe
    _p("verkaeufe.view", "verkaeufe"),
    _p("verkaeufe.edit", "verkaeufe", ["verkaeufe.view"]),
    _p("verkaeufe.storno", "verkaeufe", ["verkaeufe.edit"]),
    _p("rezeption.edit", "verkaeufe", ["verkaeufe.view"]),
    _p("ablaeufe.view", "verkaeufe"),
    _p("ablaeufe.edit", "verkaeufe", ["ablaeufe.view"]),
    # Geld
    _p("geld.erstatten", "geld", ["verkaeufe.edit"], sensitive=True),
    _p("geld.korrektur", "geld", ["verkaeufe.edit"], sensitive=True),
    _p("geld.richtlinie", "geld", ["ablaeufe.edit"], sensitive=True),
    _p("geld.rabatt", "geld", ["verkaeufe.edit"], sensitive=True),
    _p("geld.preis", "geld", ["verkaeufe.edit"], sensitive=True),
    _p("geld.bezahlt", "geld", ["verkaeufe.edit"], sensitive=True),
    _p("geld.einloesen", "geld", sensitive=True),
    _p("geld.zahlungslink", "geld", ["verkaeufe.view"], sensitive=True),
    # Sortiment
    _p("sortiment.view", "sortiment"),
    _p("sortiment.edit", "sortiment", ["sortiment.view"]),
    _p("sortiment.delete", "sortiment", ["sortiment.edit"]),
    _p("preise.view", "sortiment"),
    _p("preise.edit", "sortiment", ["preise.view"]),
    _p("lager.view", "sortiment"),
    _p("lager.edit", "sortiment", ["lager.view"]),
    _p("lager.export", "sortiment", ["lager.view"]),
    _p("veranstaltung.absagen", "sortiment", ["sortiment.edit"], sensitive=True),
    # Kunden
    _p("kunden.view", "kunden"),
    _p("kunden.kontakte", "kunden", ["kunden.view"], sensitive=True),
    _p("kunden.export", "kunden", ["kunden.view"], sensitive=True),
    _p("kunden.dsgvo", "kunden", ["kunden.view"], sensitive=True),
    # Marketing
    _p("marketing.view", "marketing"),
    _p("marketing.edit", "marketing", ["marketing.view"]),
    _p("marketing.delete", "marketing", ["marketing.edit"]),
    _p("nachrichten.view", "marketing"),
    _p("nachrichten.edit", "marketing", ["nachrichten.view"]),
    _p("kanaele.view", "marketing"),
    _p("kanaele.edit", "marketing", ["kanaele.view"], sensitive=True),
    _p("stadtportal.view", "marketing", sensitive=True),
    # Website
    _p("website.view", "website"),
    _p("website.edit", "website", ["website.view"]),
    _p("domains.view", "website"),
    _p("domains.edit", "website", ["domains.view"], sensitive=True),
    # Zahlen & Finanzen
    _p("finanzen.kennzahlen", "finanzen"),
    _p("finanzen.berichte", "finanzen", ["finanzen.kennzahlen"]),
    _p("finanzen.journal", "finanzen", ["finanzen.berichte"]),
    _p("finanzen.edit", "finanzen", ["finanzen.journal"]),
    _p("finanzen.export", "finanzen", ["finanzen.journal"], sensitive=True),
    _p("finanzen.korrektur", "finanzen", ["finanzen.edit"], sensitive=True),
    _p("finanzen.bank", "finanzen", ["finanzen.journal"], sensitive=True),
    # Einstellungen
    _p("einstellungen.view", "einstellungen"),
    _p("einstellungen.edit", "einstellungen", ["einstellungen.view"]),
    _p("funktionen.view", "einstellungen"),
    _p("funktionen.edit", "einstellungen", ["funktionen.view"], sensitive=True),
    _p("betriebsferien.ganz", "einstellungen", sensitive=True),
    _p("team.view", "team"),
    _p("team.edit", "team", ["team.view"], sensitive=True),
    _p("team.delete", "team", ["team.edit"], sensitive=True),
)

PERMS: dict[str, Perm] = {p.key: p for p in _ALL}

GROUPS = (
    "verkaeufe",
    "geld",
    "sortiment",
    "kunden",
    "marketing",
    "website",
    "finanzen",
    "einstellungen",
    "team",
)

# Сегодня только у владельца (KA-H8/H11/KA-D7/B2-4/E1.12/E4.1a/Д3/В5/W9-10).
_OWNER_ONLY_TODAY = frozenset(
    {
        "geld.korrektur",
        "geld.richtlinie",
        "veranstaltung.absagen",
        "kunden.kontakte",
        "kunden.export",
        "kunden.dsgvo",
        "kanaele.edit",
        "stadtportal.view",
        "finanzen.bank",
        "betriebsferien.ganz",
        "team.view",
        "team.edit",
        "team.delete",
    }
)
# Сегодня у owner и admin (KA-12 B6 / Z-4, KA-D7, KA-H4).
_ADMIN_TODAY = frozenset({"preise.edit", "finanzen.export", "finanzen.korrektur", "geld.erstatten"})

PRESETS: dict[str, frozenset] = {
    Membership.ROLE_ADMIN: frozenset(PERMS) - _OWNER_ONLY_TODAY,
    Membership.ROLE_STAFF: frozenset(PERMS) - _OWNER_ONLY_TODAY - _ADMIN_TODAY,
}


def _strict() -> bool:
    return bool(getattr(settings, "PERMS_STRICT", settings.DEBUG))


def check_key(key: str) -> None:
    """Опечатка в ключе — ошибка разработки: в DEBUG/тестах падаем сразу."""
    if key not in PERMS:
        raise ImproperlyConfigured(f"Unbekanntes Recht: {key!r}")


def _closure(keys) -> frozenset:
    """Замыкание вниз по ``requires``: без ``view`` нет и ``edit``."""
    keys = set(keys)
    changed = True
    while changed:
        changed = False
        for key in list(keys):
            if any(req not in keys for req in PERMS[key].requires):
                keys.discard(key)
                changed = True
    return frozenset(keys)


def for_role(role: str) -> frozenset:
    """Эффективные права роли без индивидуальной настройки."""
    if role == Membership.ROLE_OWNER:
        return frozenset(PERMS)
    return _closure(PRESETS.get(role, frozenset()))


def effective(user) -> frozenset:
    """Права пользователя в текущей схеме. Аноним/нет Membership → пусто (fail-closed)."""
    if not getattr(user, "is_authenticated", False) or getattr(user, "pk", None) is None:
        return frozenset()
    role = Membership.objects.filter(user=user).values_list("role", flat=True).first()
    return for_role(role) if role else frozenset()


def has_perm(user, key: str) -> bool:
    if key not in PERMS:
        if _strict():
            check_key(key)
        logger.error("has_perm: unbekanntes Recht %r", key)
        return False
    return key in effective(user)
