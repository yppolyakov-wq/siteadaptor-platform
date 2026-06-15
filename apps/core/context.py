"""Context processor: активные модули для навигации кабинета (Track D / D0a).

Подключён в TEMPLATES (config/settings/base.py). На public-схеме (агрегатор,
порталы, онбординг) навигации кабинета нет → пустой контекст.
"""

from . import modules


def _storefront_nav(tenant):
    """Готовые пункты шапки витрины (M20 ④): порядок владельца, только
    включённые и с активным модулем. Возвращает (items, style, sticky)."""
    from django.urls import NoReverseMatch, reverse

    from apps.tenants import siteconfig

    nav_cfg = siteconfig.normalize(tenant.site_config)["nav"]
    meta = {key: (label, url, mod) for key, label, url, mod in siteconfig.NAV_ITEMS}
    items = []
    for entry in nav_cfg["items"]:
        if not entry["enabled"]:
            continue
        label, url_name, module = meta[entry["key"]]
        if module and not modules.is_module_active(tenant, module):
            continue
        try:
            items.append({"key": entry["key"], "label": label, "url": reverse(url_name)})
        except NoReverseMatch:  # маршрут недоступен в текущем urlconf — пропустить
            continue
    return items, nav_cfg["style"], nav_cfg["sticky"]


def modules_nav(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or getattr(tenant, "schema_name", "public") == "public":
        return {}
    nav_items, nav_style, nav_sticky = _storefront_nav(tenant)
    return {
        "nav_modules": modules.active_modules(tenant),
        # Флаги для шапки публичной витрины (ссылки «Termin» D3b / «Übernachten» E3).
        "storefront_booking_enabled": modules.is_module_active(tenant, "booking"),
        "storefront_stays_enabled": modules.is_module_active(tenant, "stays"),
        "storefront_jobs_enabled": modules.is_module_active(tenant, "jobs"),
        "storefront_inbox_enabled": modules.is_module_active(tenant, "inbox"),  # M22b
        "storefront_events_enabled": modules.is_module_active(tenant, "events"),  # A6c
        # M20 ④: готовая навигация витрины (стиль/sticky/пункты).
        "storefront_nav": nav_items,
        "storefront_nav_style": nav_style,
        "storefront_nav_sticky": nav_sticky,
    }
