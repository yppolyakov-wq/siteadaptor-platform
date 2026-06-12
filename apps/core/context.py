"""Context processor: активные модули для навигации кабинета (Track D / D0a).

Подключён в TEMPLATES (config/settings/base.py). На public-схеме (агрегатор,
порталы, онбординг) навигации кабинета нет → пустой контекст.
"""

from . import modules


def modules_nav(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or getattr(tenant, "schema_name", "public") == "public":
        return {}
    return {
        "nav_modules": modules.active_modules(tenant),
        # Флаг для шапки публичной витрины (ссылка «Termin», D3b).
        "storefront_booking_enabled": modules.is_module_active(tenant, "booking"),
    }
