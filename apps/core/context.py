"""Context processor: активные модули для навигации кабинета (Track D / D0a).

Подключён в TEMPLATES (config/settings/base.py). На public-схеме (агрегатор,
порталы, онбординг) навигации кабинета нет → пустой контекст.
"""

from django.conf import settings
from django.utils.translation import get_language, get_language_info

from . import modules
from .i18n_cabinet import cabinet_languages


def _native_language_name(code: str) -> str:
    """Родное имя языка («Deutsch»/«English»/…) для переключателя витрины.

    Django знает имена для всех кодов из `LANGUAGES`; для неизвестного —
    фолбэк на верхний регистр кода (не падаем).
    """
    try:
        return get_language_info(code)["name_local"].capitalize()
    except Exception:  # noqa: BLE001 — генерик, любой сбой → фолбэк на код
        return code.upper()


def _wishlist_enabled(tenant) -> bool:
    """M4-C: показывать ли «Merkzettel» (опция витрины, дефолт по архетипу)."""
    from apps.orders import wishlist

    return wishlist.enabled(tenant) if tenant is not None else False


def _wishlist_count(request) -> int:
    from apps.orders import wishlist

    return wishlist.count(request) if hasattr(request, "session") else 0


def _wishlist_ids(request) -> list:
    """pk отложенного — карточка красит сердечко без запроса на товар."""
    from apps.orders import wishlist

    return wishlist.ids(request) if hasattr(request, "session") else []


def _wishlist_promo_ids(request) -> list:
    """SF-4a: pk отложенных АКЦИЙ — сердечко на промо-карточке."""
    from apps.orders import wishlist

    return wishlist.ids(request, "promotion") if hasattr(request, "session") else []


def _cart_count(request) -> int:
    """Всего позиций в корзине (товары + комбо) — для бейджа иконки корзины."""
    total = 0
    if hasattr(request, "session"):
        for key in ("cart", "combo_cart"):
            d = request.session.get(key)
            if isinstance(d, dict):
                total += sum(v for v in d.values() if isinstance(v, int))
    return total


def _studio_page_ctx(request) -> dict:
    """STU-2: `data-stu-page`/`data-stu-ref` на <body> витрины.

    Studio грузит страницу сайта в кадр и должен понять, ЧТО именно открыто, —
    иначе панель «Эта страница» показывает настройки наугад (сегодня она их и
    показывает: настройки акций живут в области «Тема», то есть видны на любой
    странице, кроме своей). Путь читать нечем: `/sortiment/<uuid>/` — товар, а
    `/sortiment/<slug>/` — категория. Поэтому тип определяет РЕЕСТР по уже
    разобранному `resolver_match`, а витрина просто выносит ответ в разметку.
    """
    from apps.core import studio_pages

    try:
        ctx = studio_pages.resolve_match(
            getattr(request, "resolver_match", None),
            request.GET.dict() if hasattr(request, "GET") else {},
            path=getattr(request, "path", ""),
        )
    except Exception:  # витрина не должна падать из-за подсказки редактору
        return {
            "storefront_page_type": "",
            "storefront_page_ref": "",
            "storefront_edit_target": getattr(request, "path", "") or "/",
        }
    return {
        "storefront_page_type": ctx.code,
        "storefront_page_ref": ctx.object_ref,
        # STU-7: адрес для кнопки «Edit design». Раньше она слала ГОЛЫЙ request.path,
        # поэтому владелец, стоя на странице группы акций, попадал в редактор на общий
        # обзор — санитайзер `?page=` параметр уже принимает, а producer его не давал.
        # Список параметров — тот же реестр, что у санитайзера и у канвы.
        "storefront_edit_target": _edit_target(request),
    }


def _edit_target(request) -> str:
    """Путь + параметры, ЗАДАЮЩИЕ страницу — значение для `?page=` кнопки «Edit design»."""
    from urllib.parse import urlencode

    from apps.core import studio_pages

    path = getattr(request, "path", "") or "/"
    keep = [
        (key, value)
        for key in studio_pages.PAGE_QUERY_KEYS
        for value in [(request.GET.get(key) or "").strip()]
        if value
    ]
    return f"{path}?{urlencode(keep)}" if keep else path


def _demo_design_ctx(request, tenant):
    """DL-8e: данные пилюли «Design testen» на демо-витрине (None вне демо).

    Опции = сборки типа бизнеса (bundles_for); активный ключ — из сессии
    посетителя. Внутри канвы редактора (?preview=1) пилюлю не показываем —
    там владелец работает со своим превью."""
    from apps.core import demo_switch

    if request.GET.get("preview") == "1" or not demo_switch.is_demo_tenant(tenant):
        return None
    from apps.tenants import sitetemplates

    active = request.session.get(demo_switch.SESSION_KEY, "") if hasattr(request, "session") else ""
    return {
        "options": [
            {"key": b["key"], "label": b["label"]}
            for b in sitetemplates.bundles_for(getattr(tenant, "business_type", "") or "retail")
        ],
        "active": active,
    }


def _accent_ink(accent: str) -> str:
    """DL-5: цвет текста ПОВЕРХ акцент-фона по яркости акцента.

    Светлый акцент (лайм neon #c8f542, янтарь warm) с белым текстом нечитаем —
    отдаём тёмные чернила; тёмный/насыщенный акцент — белые (прежний вид).
    Не-hex/битое значение → белый (fail-safe, как было всегда)."""
    accent = (accent or "").strip()
    if len(accent) == 7 and accent.startswith("#"):
        try:
            r, g, b = (int(accent[i : i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            return "#ffffff"
        if (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.62:
            return "#111827"
    return "#ffffff"


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


#: DS-10: листинги, поддерживающие ?q= (движок поиска UB2-2) — куда ведёт 🔍 шапки.
_SEARCH_ROUTES = {
    "catalog": "storefront-products",
    "booking": "storefront-termin",
    "stays": "storefront-unterkunft",
    "events": "storefront-events",
}


def _primary_search_module(tenant) -> str | None:
    """Модуль, чей листинг ищет поиск шапки: главный архетип тенанта, если у
    него есть листинг с ?q=; иначе None (фолбэк на каталог у вызывающего)."""
    try:
        from apps.core import archetypes

        key = archetypes.primary_module(tenant)
    except Exception:  # noqa: BLE001 — шапка не должна падать из-за резолвера
        return None
    return key if key in _SEARCH_ROUTES else None


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
    # ST-1b: stateless-превью Look'а (?preview=1&look=<family>) — оверлей пачки
    # ключей ПОВЕРХ cfg только на этот рендер, НИЧЕГО не пишет (N iframe галереи
    # не делят единственный session-слот черновика). DL-3: += &bundle=<key> —
    # оси сборки (стили/включение секций, catalog_layout, страничные пресеты)
    # тем же read-only оверлеем; без явного &look= кожу даёт Look самой сборки.
    # DL-8e: тот же оверлей питает демо-переключатель шаблона (выбор в СЕССИИ
    # посетителя, только на демо-тенантах; конфиг не пишется никогда).
    from apps.core import demo_switch as _demo_switch

    _ov_bundle_key = _demo_switch.overlay_bundle_key(request)
    _ov_look_key = request.GET.get("look", "") if request.GET.get("preview") == "1" else ""
    if _ov_look_key or _ov_bundle_key:
        from apps.tenants import sitetemplates

        _bundle = sitetemplates.get_bundle(_ov_bundle_key)
        _fam = sitetemplates.get_look_family(_ov_look_key or (_bundle["look"] if _bundle else ""))
        if _fam is not None:
            cfg = dict(cfg)
            cfg["font"] = _fam["font"]
            cfg["typography"] = siteconfig.normalize_typography(_fam["typography"])
            cfg["site_defaults"] = siteconfig.normalize_site_defaults(_fam["site_defaults"])
            _nav = dict(cfg.get("nav") or {})
            _nav["style"] = _fam["nav_style"]
            cfg["nav"] = _nav
            nav_style = _fam["nav_style"]  # top_meta считан выше — переопределяем
            cfg["hero_style"] = _fam["hero_style"]
            if _fam["theme"] == "dark":
                cfg["theme"] = "dark"
            else:
                cfg.pop("theme", None)
            storefront_accent = sitetemplates.look_accent(
                getattr(tenant, "business_type", ""), _fam["key"]
            )
            # DL-8b: превью несёт и фирменные бейджи/цены семейства.
            cfg["design"] = {**(cfg.get("design") or {}), "look": _fam["key"]}
        if _bundle is not None:
            cfg = sitetemplates.apply_preview_bundle(cfg, _bundle["key"])
            nav_style = (cfg.get("nav") or {}).get("style") or nav_style
    font_body, font_head = siteconfig.font_stacks(cfg["font"])
    # ST-1: тёмный Look — дефолт темы сайта ("" | "dark", draft-aware для превью).
    storefront_theme_default = cfg.get("theme", "")
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
            # Фидбэк 2026-07-28: обложка = ОДИН узкий слайдер — hero-фото и галерея
            # сведены в общий список слайдов (hero первым, без дублей).
            slides = [ov.get("hero_image", "")] if ov.get("hero_image") else []
            for img in ov.get("gallery", []):
                if img.get("url") and img["url"] not in slides:
                    slides.append(img["url"])
            archetype_cover = {
                "intro": ov.get("intro", ""),
                "slides": slides,
                "button_label": ov.get("button_label", ""),
                "button_url": ov.get("button_url", ""),
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
    # ST-4b/W-CL: таб-бар = первая четвёрка якорей компакт-сайдбара (безусловно).
    _compact = modules.sidebar_nav(tenant, getattr(request, "user", None))
    # VF-7a (фидбэк 2026-08-24 «выбелены оба»): активный ПОДПУНКТ определяется
    # по URL страницы, не по nav_key — несколько подпунктов раздела законно
    # делят nav_key (booking, marketing) и подсвечивались парами. Фолбэк для
    # под-страниц: nav_key, но только если он у ЕДИНСТВЕННОГО подпункта.
    from django.urls import NoReverseMatch as _NRM
    from django.urls import reverse as _rev

    _full = request.get_full_path()
    _path = request.path
    for _it in _compact:
        _hit = False
        _kids = _it.get("children", [])
        _key_counts = {}
        for _c in _kids:
            _key_counts[_c["nav_key"]] = _key_counts.get(_c["nav_key"], 0) + 1
        for _c in _kids:
            try:
                _u = _rev(_c["url_name"])
            except _NRM:
                _c["active"] = False
                _c["nav_unique"] = False
                continue
            q = _c.get("query") or ""
            _c["active"] = _full.startswith(_u + q) if q else (_path == _u)
            # фолбэк для под-страниц (nav ведом только шаблону): годится лишь
            # подпункт, чей nav_key уникален внутри раздела
            _c["nav_unique"] = _key_counts.get(_c["nav_key"], 0) == 1
            _hit = _hit or _c["active"]
        # VF-10: query-совпадение специфичнее голого пути — на
        # /verkaeufe/?tab=job горит «Aufträge», а не он же вместе с «Verkäufe»
        # (обзорный подпункт без query делит путь со вкладками).
        if any(_c.get("active") and _c.get("query") for _c in _kids):
            for _c in _kids:
                if _c.get("active") and not _c.get("query"):
                    _c["active"] = False
        _it["has_active_child"] = _hit
    nav_primary = [
        {
            "url_name": it["url_name"],
            "nav_key": it["nav_key"],
            "label": it["label"],
            "icon": it["icon"],
            # R7-1: раздел с подменю на мобильном открывает СПИСОК подпунктов
            # (тот же жест, что на десктопе), а не уводит сразу на страницу.
            "has_children": bool(it.get("children")),
        }
        for it in _compact[:4]
    ]
    # DS-3b (Fokus): CTA primary-действия в шапке (nav.cta) — метка/URL из
    # реестра primary_item (как hero-CTA); нерезолвимый лендинг → кнопки нет.
    storefront_nav_cta = None
    if (cfg.get("nav") or {}).get("cta"):
        from django.urls import NoReverseMatch, reverse

        from apps.core import archetypes as _archetypes

        _pi = _archetypes.primary_item(tenant)
        if _pi and _pi.get("landing"):
            try:
                storefront_nav_cta = {"label": _pi["label"], "url": reverse(_pi["landing"])}
            except NoReverseMatch:
                storefront_nav_cta = None
    # DS-6/DS-10: глобальный поиск в шапке. Ведёт в листинг ГЛАВНОГО модуля
    # архетипа (номера у отеля, услуги у салона, события у организатора, иначе
    # каталог) — DS-10 убрал поле поиска из тулбаров листингов, и жёсткая
    # привязка к каталогу оставила бы эти архетипы вовсе без поиска.
    storefront_search_url = ""
    from django.urls import NoReverseMatch as _NRM
    from django.urls import reverse as _rev

    for _mod, _route in (
        (_primary_search_module(tenant), None),
        ("catalog", "storefront-products"),
    ):
        if not _mod:
            continue
        _name = _route or _SEARCH_ROUTES.get(_mod)
        if not _name or not modules.is_module_active(tenant, _mod):
            continue
        try:
            storefront_search_url = _rev(_name)
            break
        except _NRM:
            continue
    if storefront_nav_cta:
        # Мобильно вторая липкая кнопка = перегруз (таб-бар уже есть) — вместо
        # этого акцентируем совпадающий пункт таб-бара (kind=primary, как корзина).
        for item in bottom_nav:
            if item.get("url") == storefront_nav_cta["url"]:
                item["kind"] = "primary"
    # L1 (Волна L): языки переключателя витрины — по `active_locales` тенанта (N
    # локалей, генерик). Метка — короткий код (DE/EN/…) для пилюли + родное имя
    # («Deutsch»/«English») для выпадающего блока. Переключатель скрывается при
    # одной локали (шаблон). Активный язык шаблон берёт из request.LANGUAGE_CODE.
    from apps.core.langs import badge as _lang_badge

    storefront_locales = [
        {"code": code, "label": _lang_badge(code), "native": _native_language_name(code)}
        for code in tenant.active_locales
    ]
    return {
        # ST-4b/W-CL: компактный сайдбар «хабы + Website» — единственный.
        "nav_compact": _compact,
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
        "storefront_gift_enabled": modules.is_module_active(tenant, "gift"),  # M0 mode-плитка
        # CA1: ЛК клиента (ссылка «Mein Konto» в шапке/таб-баре при активном модуле).
        "storefront_account_enabled": modules.is_module_active(tenant, "customer_account"),
        # CA4: вошедший клиент (автозаполнение форм; None если не вошёл/модуль выкл).
        "account_customer": account_customer,
        # R1: всего позиций в корзине — бейдж иконки корзины в шапке.
        "storefront_cart_count": _cart_count(request),
        # M4-C: список отложенного — опция витрины (бутик/ритейл) + счётчик
        # для иконки-сердца в шапке. Сессия, без аккаунта (DSGVO-чисто).
        "storefront_wishlist_enabled": _wishlist_enabled(tenant),
        "storefront_wishlist_count": _wishlist_count(request),
        "storefront_wishlist_ids": _wishlist_ids(request),
        "storefront_wishlist_promo_ids": _wishlist_promo_ids(request),
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
        # DS-3b (Fokus): кнопка primary-действия в шапке (None = как раньше).
        "storefront_nav_cta": storefront_nav_cta,
        # DS-6: поиск в шапке ("" = иконки нет).
        "storefront_search_url": storefront_search_url,
        # DS-7b: активна ли продажа (orders) — при ней цены в меню скрывать
        # нельзя (PAngV), тумблер menu_show_prices игнорируется рендером.
        "storefront_orders_active": modules.is_module_active(tenant, "orders"),
        # P2a: системные шрифт-стеки витрины (тело/заголовки).
        "storefront_font_body": font_body,
        "storefront_font_head": font_head,
        # SE-3b: глобальная типографика (draft-aware). 0/0.0 → шаблон не эмитит
        # переменную → текущий вид (без регрессии).
        "storefront_font_weight_head": cfg["typography"]["weight_head"],
        "storefront_line_height": cfg["typography"]["line_height"],
        # M20: override акцента в live-preview (пусто → tenant.primary_color).
        "storefront_accent": storefront_accent,
        # DL-5 (стенд): «чернила» поверх акцент-фона — светлый акцент (лайм
        # neon, янтарь warm) с жёстким text-white был нечитаем на 36 CTA.
        "storefront_accent_ink": _accent_ink(storefront_accent or "#4f46e5"),
        # ST-1: тёмный Look — дефолт темы сайта (посетительский тумблер сильнее).
        "storefront_theme_default": storefront_theme_default,
        # SE-2d/SE-3d: глобальный стиль карточек («весь сайт»; draft-aware). Пустые
        # (0/false/"") → шаблон не эмитит inline-переменные → витрина без регрессии.
        "storefront_card_radius": cfg["site_defaults"]["card_radius"],
        "storefront_card_shadow": cfg["site_defaults"]["card_shadow"],
        "storefront_card_bg": cfg["site_defaults"]["card_bg"],
        "storefront_card_padding": cfg["site_defaults"]["card_padding"],
        # DS-1: фон страницы Look-семейства (крем/песок; "" = bg-gray-50 как
        # раньше; тёмная тема правило не видит — скоуп html:not(.dark)).
        "storefront_page_bg": cfg["site_defaults"].get("page_bg", ""),
        # ST-7c: глобальная ФОРМА карточки ("" | overlay | compact; draft-aware).
        "storefront_card_style": cfg["site_defaults"].get("card_style", ""),
        # STU-9: ширина текстовой колонки — отсюда, потому что здесь уже учтён
        # черновик ?preview=1; тег, читавший конфиг тенанта сам, живого превью
        # не давал и на правовых страницах (там нет `site`) работал по
        # СОХРАНЁННОМУ конфигу.
        "storefront_text_width": cfg["site_defaults"].get("text_width", ""),
        # DL-2: ХРОМ карточек ("" | hard | hairline | line) — рамка/тень
        # семейства Look'а; body несёт data-sf-chrome, правила в _base.html.
        "storefront_card_chrome": cfg["site_defaults"].get("card_chrome", ""),
        # DL-10a: форма кадра на карточках (round | wide; "" = как в разметке).
        "storefront_media_shape": cfg["site_defaults"].get("media_shape", ""),
        # DL-16.4: форма карточки акции ("" | preis) и листание фото на карточке товара.
        "storefront_promo_card": cfg["site_defaults"].get("promo_card", ""),
        "storefront_card_slider": cfg["site_defaults"].get("card_slider", ""),
        # DL-8b: семейство выбранного Look'а (body data-sf-look — фирменные
        # бейджи/цены варианта CSS-каскадом); в превью — из GET-оверлея (ниже).
        "storefront_look": (cfg.get("design") or {}).get("look", ""),
        # DL-8e: пилюля «Design testen» — только на демо-тенантах.
        "storefront_demo_design": _demo_design_ctx(request, tenant),
        # O-2: дефолтный вид выбора вариантов ("" = выпадающий список). Товар
        # может переопределить своим `variant_style`.
        "storefront_variant_style": cfg["site_defaults"].get("variant_style", ""),
        # HF-2: какие удобства показывать пиктограммами на карточке номера (выбор
        # владельца; пусто = первые несколько удобств самого номера).
        "storefront_card_amenities": cfg.get("stay_card_amenities", []),
        # H1.2: тэглайн подвала (draft-aware) — правится инлайн (data-edit="footer_text").
        "storefront_footer_text": cfg.get("footer_text", ""),
        # STU-2: тип страницы витрины для Studio — редактор читает его с <body>
        # кадра и показывает настройки ИМЕННО этой страницы. Считаем по уже
        # разобранному resolver_match (Django разрешил путь до вьюхи) — второго
        # разбора на каждый рендер витрины не происходит.
        **_studio_page_ctx(request),
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
        # #4 (ясность режима): что Простой режим убирает из меню (человекочит. названия,
        # независимо от текущего режима) — для подсказки у тумблера/на «Funktionen».
        # Число включённых языков витрины — бейдж у ссылки «Sprachen» в шапке.
        "cabinet_locale_count": len(tenant.active_locales),
        # T1 (FB-12): язык КАБИНЕТА (админ-панели) — отдельно от языка витрины.
        # cabinet_langs — доступные переведённые языки для переключателя в шапке;
        # cabinet_lang — текущий активный (для подсветки).
        "cabinet_langs": cabinet_languages(),
        "cabinet_lang": get_language() or settings.LANGUAGE_CODE,
    }
