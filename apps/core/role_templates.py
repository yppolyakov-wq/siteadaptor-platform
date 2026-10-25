"""KA-12 E6.7f: шаблоны ролей (Rollenvorlagen) — именованные наборы прав по архетипу.

План — docs/ka-12-e6-7f-role-templates-plan-2026-10-25.md (основа — §A.5 плана E6.7).
Шаблон — не новая роль: явный набор ключей для роли admin или staff, без наследования.
Применение = обычная выдача прав через ``perm_grants.set_member_permissions`` (области,
requires, stale — как у чекбоксов); имя шаблона хранится только для подписи в UI.
"""

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _

from . import permissions as P
from .models import Membership

ADMIN, STAFF = Membership.ROLE_ADMIN, Membership.ROLE_STAFF

GASTRO = ("cafe", "restaurant", "catering", "bakery", "butcher")
HOTEL = ("hotel",)


@dataclass(frozen=True)
class RoleTemplate:
    key: str
    label: str
    hint: str
    role: str
    keys: frozenset
    business_types: tuple = ()  # пусто — для всех типов


_SALES = frozenset({"verkaeufe.view", "verkaeufe.edit"})

TEMPLATES: dict[str, RoleTemplate] = {
    t.key: t
    for t in (
        RoleTemplate(
            "leitung",
            _("Leitung"),
            _("Alles außer Abo, Recht und Bankdaten."),
            ADMIN,
            P.for_role(ADMIN),
        ),
        RoleTemplate(
            "buchhaltung",
            _("Buchhaltung"),
            _("Rechnungen, Journal, Export und Erstattungen."),
            ADMIN,
            frozenset(
                {
                    "verkaeufe.view",
                    "verkaeufe.edit",  # «erstatten» требует правки сделки
                    "kunden.view",
                    "geld.erstatten",
                    "finanzen.kennzahlen",
                    "finanzen.berichte",
                    "finanzen.journal",
                    "finanzen.edit",
                    "finanzen.export",
                    "finanzen.korrektur",
                }
            ),
        ),
        RoleTemplate(
            "mitarbeiter",
            _("Mitarbeiter"),
            _("Verkäufe, Sortiment, Kunden und Nachrichten — ohne Finanzen."),
            STAFF,
            P.for_role(STAFF),
        ),
        RoleTemplate(
            "aushilfe",
            _("Aushilfe / Kasse"),
            _("Verkäufe bearbeiten, kassieren und Gutscheine einlösen."),
            STAFF,
            _SALES | {"geld.einloesen", "geld.bezahlt", "kunden.view"},
        ),
        RoleTemplate(
            "rezeption",
            _("Rezeption"),
            _("An- und Abreise, Buchungen, Gäste und Zahlungen."),
            STAFF,
            _SALES
            | {
                "rezeption.edit",
                "geld.bezahlt",
                "kunden.view",
                "kunden.edit",
                "finanzen.kennzahlen",
            },
            HOTEL,
        ),
        RoleTemplate(
            "housekeeping",
            _("Housekeeping"),
            _("Belegung und Zimmerstatus ansehen."),
            STAFF,
            frozenset({"verkaeufe.view"}),
            HOTEL,
        ),
        RoleTemplate(
            "kueche",
            _("Küche"),
            _("Bestellungen sehen und den Status weitersetzen."),
            STAFF,
            _SALES,
            GASTRO,
        ),
    )
}


def templates_for(tenant, role: str) -> list[RoleTemplate]:
    """Шаблоны роли ``role`` для типа бизнеса тенанта (общие + свои архетипа)."""
    btype = getattr(tenant, "business_type", "") or ""
    return [
        t
        for t in TEMPLATES.values()
        if t.role == role and (not t.business_types or btype in t.business_types)
    ]


def matches(template_key: str, role: str, eff) -> bool:
    """Права совпадают с шаблоном (иначе подпись «angepasst»)."""
    t = TEMPLATES.get(template_key)
    return t is not None and t.role == role and P._closure(t.keys) == frozenset(eff)
