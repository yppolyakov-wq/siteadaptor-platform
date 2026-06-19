"""Context processor: активные модули для навигации кабинета (Track D / D0a).

Подключён в TEMPLATES (config/settings/base.py). На public-схеме (агрегатор,
порталы, онбординг) навигации кабинета нет → пустой контекст.
"""

from . import modules


def _storefront_bottom_nav(request, tenant):
    """Мобильный нижний таб-бар витрины (T2b, развивает P1 action-bar).

    Адаптивный набор по активным модулям (иконка+подпись, emoji — без ассетов):
    Speisekarte · Aktionen · главное действие (Корзина с бейджем / Termin / …) ·
    Anruf. Корзина — акцент (kind=primary). Полная настройка владельцем —
    отдельная итерация (ТЗ «нижнее меню в кабинете», roadmap §Отложено); пока
    дефолт по доступности. Cap 5 (узкий мобайл).
    """
    from django.urls import NoReverseMatch, reverse
    from django.utils.translation import gettext as _

    items = []

    def add(name_or_url, label, icon, *, kind="default", badge=0, is_url=False):
        url = name_or_url
        if not is_url:
            try:
                url = reverse(name_or_url)
            except NoReverseMatch:
                return
        items.append({"url": url, "label": label, "icon": icon, "kind": kind, "badge": badge})

    add("storefront-products", _("Menu"), "🍽")
    if modules.is_module_active(tenant, "promotions"):
        add("/#aktionen", _("Deals"), "🔥", is_url=True)

    # Главное действие по самому релевантному активному модулю.
    if modules.is_module_active(tenant, "orders"):
        cart = request.session.get("cart") if hasattr(request, "session") else None
        count = sum(v for v in cart.values() if isinstance(v, int)) if isinstance(cart, dict) else 0
        add("storefront-cart", _("Cart"), "🛒", kind="primary", badge=count)
    elif modules.is_module_active(tenant, "booking"):
        add("storefront-termin", _("Book"), "📅", kind="primary")
    elif modules.is_module_active(tenant, "stays"):
        add("storefront-unterkunft", _("Stay"), "🛏", kind="primary")
    elif modules.is_module_active(tenant, "events"):
        add("storefront-events", _("Events"), "🎫", kind="primary")

    if modules.is_module_active(tenant, "customer_account"):
        add("account-home", _("Account"), "👤")
    phone = (getattr(tenant, "public_phone", "") or "").strip()
    if phone:
        add(f"tel:{phone}", _("Call"), "📞", is_url=True)
    return items[:5]


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
    # CA4: вошедший клиент (для автозаполнения форм заказа/брони именем/почтой).
    account_customer = None
    if modules.is_module_active(tenant, "customer_account"):
        from apps.account.auth import current_customer

        account_customer = current_customer(request)
    # T2a QR-Bestellung am Tisch: ?tisch=N запоминаем в сессии, чтобы донести
    # номер стола до оформления заказа (как ?ch= для атрибуции).
    storefront_table = ""
    if hasattr(request, "session"):
        table = (request.GET.get("tisch") or "").strip()[:20]
        if table:
            request.session["table"] = table
        storefront_table = request.session.get("table", "")
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
        "storefront_orders_enabled": modules.is_module_active(tenant, "orders"),  # T2c quick-add
        # CA1: ЛК клиента (ссылка «Mein Konto» в шапке/таб-баре при активном модуле).
        "storefront_account_enabled": modules.is_module_active(tenant, "customer_account"),
        # CA4: вошедший клиент (автозаполнение форм; None если не вошёл/модуль выкл).
        "account_customer": account_customer,
        # T2c: «+»/модалка на карточках = orders активен И не отключён владельцем.
        "storefront_quick_add": modules.is_module_active(tenant, "orders") and cfg["quick_add"],
        # M20 ④: готовая навигация витрины (стиль/sticky/пункты).
        "storefront_nav": nav_items,
        "storefront_nav_style": nav_style,
        "storefront_nav_sticky": nav_sticky,
        # P1→T2b: липкий мобильный таб-бар (Menu/Deals/Cart/Call, адаптивно).
        "storefront_bottom_nav": _storefront_bottom_nav(request, tenant),
        # P2a: системные шрифт-стеки витрины (тело/заголовки).
        "storefront_font_body": font_body,
        "storefront_font_head": font_head,
        # P5: preload hero-фото (LCP) — пусто, если секция выключена/без фото.
        "storefront_hero_preload": hero_preload,
        # T2a: текущий стол (из ?tisch=, в сессии) — для баннера витрины/checkout.
        "storefront_table": storefront_table,
    }
