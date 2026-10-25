"""SR-5 (вариант Б, реанимация плана r5c-einstellungen-overview §1-3): страница-
обзор `/dashboard/einstellungen/` — группированный список экранов настроек с
живыми подписями (тот же слой `settings_hints`, что подменю варианта А).

Состав — из единого реестра (legacy_hub_tabs("settings"), W8) с теми же
гейтами, что подменю: module_key активен · owner-only скрыто сотруднику ·
allowed_for_business. Формы НЕ сводятся — строка ведёт на родной экран."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

from apps.core import nav_registry, settings_hints

# KA-12 E8.4: группы обзора = группы подменю (nav_registry.SUBMENU_GROUPS["settings"]);
# пункты без группы — блоком «Weitere» в конце.
_TAIL = ("weitere", _("Weitere"))

# Статичные подписи-описания (когда живой нет): url_name → msgid.
_STATIC = {
    "settings": _("Adresse, Öffnungszeiten, Kontakt"),
    "legal-docs": _("Impressum, AGB, USt-Sätze"),
    "ablaeufe": _("Status-Namen, Übergänge, Spalten"),
    "extras": _("Extras & Optionen zu Verkäufen"),
    "support:help": _("Anleitungen & Kontakt"),
    "modules": _("Module an- und abschalten"),
}


def _visible_entries(tenant, user):
    """Подпункты Einstellungen под ТЕМИ ЖЕ гейтами и в том же порядке, что подменю
    сайдбара (nav_registry.visible_children): модуль · направление · тип бизнеса ·
    права пользователя (E6.7e) · пункты скрытого «Finanzen» группой «Zahlen & Finanzen»."""
    from apps.core.modules import owner_hidden_for

    owner_hidden = owner_hidden_for(user)
    anchor = next(a for a in nav_registry.ANCHORS if a.nav_key == "settings")
    out = []
    for e, group in nav_registry.visible_children(anchor, tenant, owner_hidden):
        try:
            url = reverse(e.url_name) + (e.query or "")
        except NoReverseMatch:
            continue
        out.append({"url_name": e.url_name, "label": e.label, "url": url, "group": group})
    return out


@login_required
def einstellungen_home(request):
    tenant = request.tenant
    entries = _visible_entries(tenant, getattr(request, "user", None))
    hints = settings_hints.hints_for(tenant)
    by_name = {}
    for e in entries:
        e["hint"] = hints.get(e["url_name"], "")
        e["static"] = _STATIC.get(e["url_name"], "")
        by_name[e["url_name"]] = e
    groups = []
    for e in entries:
        key = e["group"] or _TAIL[0]
        if not groups or groups[-1]["key"] != key:
            label = nav_registry.group_label("settings", e["group"]) if e["group"] else _TAIL[1]
            groups.append({"key": key, "label": label, "rows": []})
        groups[-1]["rows"].append(e)
    return render(
        request,
        "tenant/einstellungen_home.html",
        {"nav": "settings", "groups": groups},
    )
