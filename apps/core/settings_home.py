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

# Группы обзора (артборд Einstellungen.dc + VarianteB канваса): url_name → группа.
_GROUPS = (
    ("geschaeft", _("Geschäft"), ("settings", "team", "languages")),
    (
        "verkauf",
        _("Verkauf"),
        ("payment-settings", "legal-docs", "notifications-settings", "ablaeufe"),
    ),
    ("system", _("System"), ("integrations-home", "modules", "billing")),
)
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
    """Записи settings-хаба под теми же гейтами, что подменю сайдбара."""
    from apps.core import modules, roles
    from apps.core.models import Membership

    owner_hidden = frozenset()
    if user is not None:
        try:
            role = roles.role_of(user)
            if role and role != Membership.ROLE_OWNER:
                owner_hidden = nav_registry.owner_only_url_names()
        except Exception:  # noqa: BLE001 — fail-open, как в sidebar_nav
            owner_hidden = frozenset()
    out = []
    for url_name, label, _nav, module_key, _adv in nav_registry.legacy_hub_tabs()["settings"]:
        if module_key and not modules.is_module_active(tenant, module_key):
            continue
        if url_name in owner_hidden:
            continue
        if not nav_registry.allowed_for_business(url_name, tenant):
            continue
        try:
            url = reverse(url_name)
        except NoReverseMatch:
            continue
        out.append({"url_name": url_name, "label": label, "url": url})
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
    used = set()
    for key, label, names in _GROUPS:
        rows = [by_name[n] for n in names if n in by_name]
        used.update(names)
        if rows:
            groups.append({"key": key, "label": label, "rows": rows})
    tail = [e for e in entries if e["url_name"] not in used]
    if tail:
        groups.append({"key": _TAIL[0], "label": _TAIL[1], "rows": tail})
    return render(
        request,
        "tenant/einstellungen_home.html",
        {"nav": "settings", "groups": groups},
    )
