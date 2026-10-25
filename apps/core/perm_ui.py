"""KA-12 E6.7d: экран выдачи прав — подписи и построение формы (только чтение).

План — docs/ka-12-e6-7d-permissions-ui-plan-2026-10-25.md. Запись прав — только
``apps.core.perm_grants`` (сервер — источник истины: области выдачи/отзыва, requires,
лимит роли). Здесь — то же правило, но для отрисовки: какой чекбокс отмечен, какой
недоступен и почему. Недоступный чекбокс браузер не отправляет — сервер сохраняет
такие ключи сам (``old - revoke_scope``), поэтому форма несёт сентинел ``perms_present``.
"""

from django.utils.translation import gettext_lazy as _

from . import perm_grants as G
from . import permissions as P
from . import role_templates as RT
from .models import Membership

GROUP_LABELS = {
    "verkaeufe": _("Verkäufe"),
    "geld": _("Geld & Zahlungen"),
    "sortiment": _("Sortiment"),
    "kunden": _("Kunden"),
    "marketing": _("Marketing"),
    "website": _("Website"),
    "finanzen": _("Zahlen & Finanzen"),
    "einstellungen": _("Einstellungen"),
    "team": _("Team"),
}

LABELS = {
    "verkaeufe.view": _("Verkäufe ansehen"),
    "verkaeufe.edit": _("Verkäufe bearbeiten"),
    "verkaeufe.storno": _("Verkäufe stornieren"),
    "rezeption.edit": _("Rezeption: An- und Abreise buchen"),
    "ablaeufe.view": _("Abläufe & Status ansehen"),
    "ablaeufe.edit": _("Abläufe & Status ändern"),
    "geld.erstatten": _("Geld erstatten"),
    "geld.korrektur": _("Rechnungen korrigieren"),
    "geld.richtlinie": _("Storno- und Anzahlungsregeln ändern"),
    "geld.rabatt": _("Rabatt auf einen Verkauf geben"),
    "geld.preis": _("Preis eines Verkaufs ändern"),
    "geld.bezahlt": _("Als bezahlt markieren"),
    "geld.einloesen": _("Gutscheine und Coupons einlösen"),
    "geld.zahlungslink": _("Zahlungslink senden"),
    "sortiment.view": _("Sortiment ansehen"),
    "sortiment.edit": _("Sortiment bearbeiten"),
    "sortiment.delete": _("Sortiment löschen"),
    "preise.view": _("Preise & Verfügbarkeit ansehen"),
    "preise.edit": _("Preise & Verfügbarkeit ändern"),
    "lager.view": _("Lager ansehen"),
    "lager.edit": _("Lager buchen"),
    "lager.export": _("Lager exportieren"),
    "veranstaltung.absagen": _("Veranstaltung absagen"),
    "kunden.view": _("Kunden ansehen"),
    "kunden.edit": _("Kunden bearbeiten"),
    "kunden.kontakte": _("Kontaktdaten der Kunden sehen"),
    "kunden.export": _("Kundendaten exportieren"),
    "kunden.dsgvo": _("Datenschutz-Anfragen bearbeiten"),
    "marketing.view": _("Aktionen & Marketing ansehen"),
    "marketing.edit": _("Aktionen & Marketing bearbeiten"),
    "marketing.delete": _("Aktionen löschen"),
    "nachrichten.view": _("Nachrichten lesen"),
    "nachrichten.edit": _("Nachrichten beantworten"),
    "kanaele.view": _("Kanäle ansehen"),
    "kanaele.edit": _("Kanäle verbinden und trennen"),
    "stadtportal.view": _("Stadtportal-Statistik ansehen"),
    "website.view": _("Website ansehen"),
    "website.edit": _("Website gestalten"),
    "domains.view": _("Domains ansehen"),
    "domains.edit": _("Domains verwalten"),
    "finanzen.kennzahlen": _("Kennzahlen ansehen"),
    "finanzen.berichte": _("Berichte ansehen"),
    "finanzen.journal": _("Journal & Rechnungen ansehen"),
    "finanzen.edit": _("Rechnungen & Ausgaben bearbeiten"),
    "finanzen.export": _("Finanzdaten exportieren (DATEV)"),
    "finanzen.korrektur": _("Buchungen korrigieren"),
    "finanzen.bank": _("Bankumsätze importieren"),
    "einstellungen.view": _("Einstellungen ansehen"),
    "einstellungen.edit": _("Einstellungen ändern"),
    "funktionen.view": _("Funktionen ansehen"),
    "funktionen.edit": _("Funktionen ein- und ausschalten"),
    "betriebsferien.ganz": _("Ganzen Betrieb schließen (Betriebsferien)"),
    "team.view": _("Team ansehen"),
    "team.edit": _("Team verwalten und Rechte vergeben"),
    "team.delete": _("Mitarbeiter entfernen"),
}

REASONS = {
    "role_limit": _("Für diese Rolle nicht möglich."),
    "no_grant": _("Nur vergeben, wer dieses Recht selbst hat — sensible Rechte nur der Inhaber."),
    "no_revoke": _("Nur der Inhaber kann dieses Recht entziehen."),
    "needed": _("Wird von einem Recht benötigt, das nur der Inhaber entziehen kann."),
    "template_scope": _("Diese Vorlage enthält Rechte außerhalb Ihres Bereichs."),
}


def _reason(key, checked, limit, grant, revoke):
    if key not in limit:
        return "role_limit"
    if checked and key not in revoke:
        return "no_revoke"
    if not checked and key not in grant:
        return "no_grant"
    return ""


def _groups(eff, limit, grant, revoke, prefix):
    reasons = {k: _reason(k, k in eff, limit, grant, revoke) for k in P.PERMS}
    # Запертое отмеченное право держит свои requires: снять их — уронить запертое
    # замыканием, а это сервер отклонит ("scope"). Поэтому их тоже не даём снять.
    locked = {k for k in eff if reasons[k]}
    for key in G.with_requires(locked) - locked:
        if key in eff and not reasons[key]:
            reasons[key] = "needed"
    out = []
    for group in P.GROUPS:
        items = []
        for perm in (p for p in P.PERMS.values() if p.group == group):
            reason = reasons[perm.key]
            items.append(
                {
                    "key": perm.key,
                    "label": LABELS[perm.key],
                    "checked": perm.key in eff,
                    "disabled": bool(reason),
                    "reason": REASONS.get(reason, ""),
                    "sensitive": perm.sensitive,
                    "requires": ",".join(perm.requires),
                    "dom_id": f"{prefix}-{perm.key.replace('.', '-')}",
                }
            )
        out.append({"key": group, "label": GROUP_LABELS[group], "items": items})
    return out


def perm_form(actor_m, target_m) -> dict | None:
    """Форма прав участника для актора или None (только чтение: владелец, сам себе,
    нет права править команду, цель вне области)."""
    if actor_m is None or target_m is None or actor_m.pk == target_m.pk:
        return None
    try:
        grant, revoke = G.scopes_for(actor_m, target_m)
    except G.PermsDenied:
        return None
    eff = P.effective_from(target_m.role, target_m.permissions)
    raw = target_m.permissions if isinstance(target_m.permissions, dict) else {}
    stored = raw.get("template", "") if isinstance(raw.get("template", ""), str) else ""
    return {
        "groups": _groups(eff, P.ROLE_LIMIT[target_m.role], grant, revoke, f"p{target_m.pk.hex}"),
        "state": G.state_token(eff),
        "count": len(eff),
        "templates": _templates(actor_m, target_m, stored),
        "template_label": _template_label(stored, target_m.role, eff),
    }


def _templates(actor_m, target_m, stored) -> list[dict]:
    """Карточки шаблонов роли цели: применимые актором — активные, прочие — с причиной."""
    from django.db import connection

    out = []
    for t in RT.templates_for(getattr(connection, "tenant", None), target_m.role):
        try:
            G.preview(actor_m, target_m, t.keys)
            reason = ""
        except G.PermsDenied:
            reason = REASONS["template_scope"]
        out.append(
            {
                "key": t.key,
                "label": t.label,
                "hint": t.hint,
                "disabled": bool(reason),
                "reason": reason,
                "active": t.key == stored,
            }
        )
    return out


def _template_label(stored, role, eff) -> str:
    t = RT.TEMPLATES.get(stored)
    if t is None or t.role != role:
        return ""
    if RT.matches(stored, role, eff):
        return str(t.label)
    return f"{t.label} · {_('angepasst')}"


def invite_forms(actor_m) -> list:
    """Блоки прав инвайта по ролям, доступным актору (по умолчанию — пресет роли
    в пределах его области выдачи; ровно то, что вложит инвайт без правок)."""
    out = []
    for role, label in Membership.ROLES:
        if role not in (G.ADMIN, G.STAFF) or actor_m is None:
            continue
        try:
            default = G.invite_defaults(actor_m, role)
            grant, _revoke = G.scopes_for(actor_m, Membership(role=role))
        except G.PermsDenied:
            continue
        out.append(
            {
                "role": role,
                "label": label,
                "groups": _groups(default, P.ROLE_LIMIT[role], grant, grant, f"inv-{role}"),
            }
        )
    return out
