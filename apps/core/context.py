"""Context processor: активные модули для навигации кабинета (Track D / D0a).

Подключён в TEMPLATES (config/settings/base.py). На public-схеме (агрегатор,
порталы, онбординг) навигации кабинета нет → пустой контекст.
"""

from django.conf import settings
from django.utils.translation import get_language

from . import modules
from .i18n_cabinet import cabinet_languages


def _cart_count(request) -> int:
    """Всего позиций в корзине (товары + комбо) — для бейджа иконки корзины."""
    total = 0
    if hasattr(request, "session"):
        for key in ("cart", "combo_cart"):
            d = request.session.get(key)
            if isinstance(d, dict):
                total += sum(v for v in d.values() if isinstance(v, int))
    return total


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
        add("storefront-cart", _("Cart"), "🛒", kind="primary", badge=_cart_count(request))
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
    from apps.tenants import menu as menu_mod

    nav_items, _legacy_style, _legacy_sticky = _storefront_nav(tenant)
    # S7: многоуровневое меню — top (дерево с подменю) + опц. кастомный bottom.
    storefront_menu = menu_mod.resolve_menu(tenant, "top")
    nav_style, nav_sticky = menu_mod.top_meta(tenant)
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

    # M20 live-preview: под ?preview=1 владелец видит несохранённый черновик из
    # конструктора (тот же источник, что и storefront_home) — значит и дизайн
    # (шрифт/hero/акцент) превьюится вживую. Вне превью — сохранённый конфиг.
    _draft = None
    if request.GET.get("preview") == "1" and hasattr(request, "session"):
        d = request.session.get("site_preview_draft")
        if isinstance(d, dict):
            _draft = d

    # Двуязычная витрина (i18n): обложки разделов/тексты chrome — на текущей локали.
    cfg = siteconfig.localize(
        siteconfig.normalize(_draft if _draft is not None else tenant.site_config),
        get_language(),
    )
    # Акцент — поле Tenant (не в site_config). Отдаём готовое значение: в превью —
    # override из черновика (`_accent`), иначе tenant.primary_color. Шаблон НЕ
    # обращается к request.tenant сам (в фильтре-аргументе это падало бы на
    # запросах без tenant, напр. в юнит-тестах витрины).
    if _draft is not None and isinstance(_draft.get("_accent"), str) and _draft["_accent"]:
        storefront_accent = _draft["_accent"]
    else:
        storefront_accent = tenant.primary_color or ""
    font_body, font_head = siteconfig.font_stacks(cfg["font"])
    # P5: hero-фото — LCP-кандидат. Браузер находит background-image поздно
    # (после CSS+layout), поэтому отдаём URL для <link rel=preload> в <head>.
    # Только если секция hero включена (иначе зря тянем картинку).
    hero_enabled = any(s["key"] == "hero" and s["enabled"] for s in cfg["sections"])
    hero_preload = cfg["hero_image"] if hero_enabled else ""
    # S3: «обложка» раздела — интро/hero над лендингом архетипа (по текущему
    # url_name). Рендерится один раз в _base.html, поверх любого лендинга.
    archetype_cover = {}
    rm = getattr(request, "resolver_match", None)
    if rm is not None:
        ckey = modules.archetype_by_landing(getattr(rm, "url_name", "") or "")
        ov = cfg["archetypes"].get(ckey) if ckey else None
        if ov and (ov.get("intro") or ov.get("hero_image") or ov.get("gallery")):
            archetype_cover = {
                "intro": ov.get("intro", ""),
                "hero_image": ov.get("hero_image", ""),
                "gallery": ov.get("gallery", []),
            }
    # S7: нижнее меню — кастомное (из menus.bottom) либо авто таб-бар (T2b).
    if menu_mod.bottom_enabled(tenant):
        # Доводка bottom-nav ТЗ (решение владельца 2026-07-03: доводим S7, а не
        # отдельный bottom_nav-ключ): узел-корзина в кастомном меню сохраняет
        # семантику авто-таб-бара — акцент (kind=primary) + бейдж позиций.
        from django.urls import NoReverseMatch, reverse

        try:
            _cart_url = reverse("storefront-cart")
        except NoReverseMatch:
            _cart_url = None
        _n_cart = _cart_count(request)
        bottom_nav = [
            {
                "url": i["url"],
                "label": i["label"],
                "icon": i["icon"] or "•",
                "kind": "primary" if _cart_url and i["url"] == _cart_url else "default",
                "badge": _n_cart if _cart_url and i["url"] == _cart_url else 0,
            }
            for i in menu_mod.resolve_menu(tenant, "bottom")
            if i["url"]
        ][:5]
    else:
        bottom_nav = _storefront_bottom_nav(request, tenant)
    # Кабинет: плоский список первых пунктов для мобильного таб-бара (нативно).
    _active = modules.active_modules(tenant)
    nav_primary = [
        {"url_name": it.url_name, "nav_key": it.nav_key, "label": it.label, "icon": m.icon}
        for m in _active
        for it in m.nav_items
    ][:4]
    # L1 (Волна L): языки переключателя витрины — по `active_locales` тенанта (N
    # локалей, генерик). Метка — короткий код (DE/EN/…); переключатель скрывается
    # при одной локали (шаблон). Активный язык шаблон берёт из request.LANGUAGE_CODE.
    storefront_locales = [{"code": code, "label": code.upper()} for code in tenant.active_locales]
    return {
        "nav_modules": _active,
        "nav_groups": modules.grouped_active_modules(tenant),  # AB1: сайдбар по задачам
        "nav_primary": nav_primary,  # мобильный таб-бар кабинета
        # S1: витринные «лица» активных архетипов — для тизеров главной (S2) и
        # конструктора меню (S7). Источник правды — реестр модулей.
        "storefront_archetypes": modules.storefront_archetypes(tenant),
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
        # R1: всего позиций в корзине — бейдж иконки корзины в шапке.
        "storefront_cart_count": _cart_count(request),
        # T2c: «+»/модалка на карточках = orders активен И не отключён владельцем.
        "storefront_quick_add": modules.is_module_active(tenant, "orders") and cfg["quick_add"],
        # M20 ④: легаси-навигация (плоская) — на случай старых шаблонов.
        "storefront_nav": nav_items,
        # S7: многоуровневое меню витрины (дерево с подменю) + стиль/sticky.
        "storefront_menu": storefront_menu,
        "storefront_nav_style": nav_style,
        "storefront_nav_sticky": nav_sticky,
        # P1→T2b: липкий мобильный таб-бар — кастомный (menus.bottom) или авто.
        "storefront_bottom_nav": bottom_nav,
        # P2a: системные шрифт-стеки витрины (тело/заголовки).
        "storefront_font_body": font_body,
        "storefront_font_head": font_head,
        # SE-3b: глобальная типографика (draft-aware). 0/0.0 → шаблон не эмитит
        # переменную → текущий вид (без регрессии).
        "storefront_font_weight_head": cfg["typography"]["weight_head"],
        "storefront_line_height": cfg["typography"]["line_height"],
        # M20: override акцента в live-preview (пусто → tenant.primary_color).
        "storefront_accent": storefront_accent,
        # SE-2d/SE-3d: глобальный стиль карточек («весь сайт»; draft-aware). Пустые
        # (0/false/"") → шаблон не эмитит inline-переменные → витрина без регрессии.
        "storefront_card_radius": cfg["site_defaults"]["card_radius"],
        "storefront_card_shadow": cfg["site_defaults"]["card_shadow"],
        "storefront_card_bg": cfg["site_defaults"]["card_bg"],
        "storefront_card_padding": cfg["site_defaults"]["card_padding"],
        # H1.2: тэглайн подвала (draft-aware) — правится инлайн (data-edit="footer_text").
        "storefront_footer_text": cfg.get("footer_text", ""),
        # Режим редактора (?preview=1): витрина показывает превью-аффордансы (пустые
        # C-блоки → плейсхолдер, пустые интро/тексты → редактируемые) на ВСЕХ страницах.
        # На публичной (без preview) пусто/чисто. Раньше задавался только в product_list.
        "is_preview": request.GET.get("preview") == "1" if hasattr(request, "GET") else False,
        # P5: preload hero-фото (LCP) — пусто, если секция выключена/без фото.
        "storefront_hero_preload": hero_preload,
        # S3: обложка раздела (интро/hero) — пусто вне лендинга архетипа.
        "archetype_cover": archetype_cover,
        # T2a: текущий стол (из ?tisch=, в сессии) — для баннера витрины/checkout.
        "storefront_table": storefront_table,
        # L1: языки переключателя витрины (по active_locales тенанта, N локалей).
        "storefront_locales": storefront_locales,
        # W3-fix (видимость): режим кабинета (Einfach/Experte) — тумблер в шапке
        # (_base_dashboard), чтобы был всегда виден (раньше только на «Funktionen»).
        "ui_simple": modules.is_simple(tenant),
        # #4 (ясность режима): что Простой режим убирает из меню (человекочит. названия,
        # независимо от текущего режима) — для подсказки у тумблера/на «Funktionen».
        "ui_simple_hidden": modules.simple_hidden_labels(tenant),
        # Число включённых языков витрины — бейдж у ссылки «Sprachen» в шапке.
        "cabinet_locale_count": len(tenant.active_locales),
        # T1 (FB-12): язык КАБИНЕТА (админ-панели) — отдельно от языка витрины.
        # cabinet_langs — доступные переведённые языки для переключателя в шапке;
        # cabinet_lang — текущий активный (для подсветки).
        "cabinet_langs": cabinet_languages(),
        "cabinet_lang": get_language() or settings.LANGUAGE_CODE,
    }
