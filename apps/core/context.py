"""Context processor: активные модули для навигации кабинета (Track D / D0a).

Подключён в TEMPLATES (config/settings/base.py). На public-схеме (агрегатор,
порталы, онбординг) навигации кабинета нет → пустой контекст.
"""

from . import modules


def _storefront_actions(tenant):
    """Действия для липкой мобильной панели (P1): звонок + главное действие
    по активному модулю + маршрут. Высокий ROI для локального бизнеса
    (click-to-call, бронь/заказ в один тап). Иконки — emoji, без ассетов."""
    from django.urls import NoReverseMatch, reverse
    from django.utils.translation import gettext as _

    actions = []
    phone = (getattr(tenant, "public_phone", "") or "").strip()
    if phone:
        actions.append({"kind": "call", "label": _("Call"), "url": f"tel:{phone}", "icon": "📞"})

    # Одно главное действие по самому релевантному активному модулю.
    primary = None
    if modules.is_module_active(tenant, "booking"):
        primary = ("storefront-termin", _("Book"), "📅")
    elif modules.is_module_active(tenant, "orders"):
        primary = ("storefront-products", _("Order"), "🛒")
    elif modules.is_module_active(tenant, "stays"):
        primary = ("storefront-unterkunft", _("Stay"), "🛏")
    elif modules.is_module_active(tenant, "events"):
        primary = ("storefront-events", _("Events"), "🎫")
    if primary:
        try:
            actions.append(
                {
                    "kind": "primary",
                    "label": primary[1],
                    "url": reverse(primary[0]),
                    "icon": primary[2],
                }
            )
        except NoReverseMatch:
            pass

    map_url = (getattr(tenant, "map_url", "") or "").strip()
    if map_url:
        actions.append({"kind": "route", "label": _("Directions"), "url": map_url, "icon": "🗺"})
    return actions


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
    from apps.tenants import siteconfig

    cfg = siteconfig.normalize(tenant.site_config)
    font_body, font_head = siteconfig.font_stacks(cfg["font"])
    # P5: hero-фото — LCP-кандидат. Браузер находит background-image поздно
    # (после CSS+layout), поэтому отдаём URL для <link rel=preload> в <head>.
    # Только если секция hero включена (иначе зря тянем картинку).
    hero_enabled = any(s["key"] == "hero" and s["enabled"] for s in cfg["sections"])
    hero_preload = cfg["hero_image"] if hero_enabled else ""
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
        # P1: липкая мобильная панель действий (звонок/бронь/маршрут).
        "storefront_actions": _storefront_actions(tenant),
        # P2a: системные шрифт-стеки витрины (тело/заголовки).
        "storefront_font_body": font_body,
        "storefront_font_head": font_head,
        # P5: preload hero-фото (LCP) — пусто, если секция выключена/без фото.
        "storefront_hero_preload": hero_preload,
    }
