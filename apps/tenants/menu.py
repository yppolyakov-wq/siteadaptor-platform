"""S7: резолв многоуровневого меню витрины из site_config['menus'].

Узел (siteconfig._clean_menu_node) → готовый пункт {label, url, icon, children}
для шапки/нижнего меню. Тип определяет построение ссылки и гейтинг по активному
модулю. Узлы без ссылки и без детей отбрасываются; «group»-родитель остаётся,
если есть хоть один резолвимый ребёнок. url НЕ резолвится в шаблоне — здесь, и
недоступный маршрут (NoReverseMatch) гасит узел.
"""

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

from apps.core import modules

from . import siteconfig

#: MEN-15: сколько категорий максимум уезжает в подменю (панель шапки не резиновая).
_MAX_MENU_CATEGORIES = 12

_PAGE_URL_NAMES = {
    "home": "storefront-home",
    "offers": "storefront-home",
    "about": "storefront-about",
    # ST-8: отдельные страницы. Ссылка ставится ТОЛЬКО при наличии контента —
    # см. _page_has_content: пустая страница отдаёт 404, поэтому и пункт меню
    # на неё вести не должен.
    "gallery": "storefront-gallery",
    "team": "storefront-team",
    "reviews": "storefront-reviews",
    # 2026-08-06 (аудит демо): существующие страницы витрины, до которых не было
    # НИ ОДНОГО пути из меню — посетитель мог попасть только по прямой ссылке.
    "loyalty": "storefront-loyalty",  # /treue/ — бонусная программа
    "gift": "storefront-gutschein",  # /gutschein/ — подарочные сертификаты
    "combos": "storefront-combos",  # /kombi/ — наборы
    "finder": "storefront-finder",  # /finder/ — подбор «3 вопроса»
    "wishlist": "storefront-wishlist",  # /merkzettel/ — избранное
    "account": "account-home",  # /konto/ — личный кабинет клиента
    # Кит TOURS ссылался на страницу "contact" — цели с таким именем не было,
    # и пункт молча выпадал из меню (узел без ссылки отбрасывается).
    "contact": "storefront-message",  # /nachricht/ — форма связи
}

# Подписи целей для редактора меню в кабинете. Список страниц там был захардкожен
# как {home, about} — селект строится из него, поэтому узел с ЛЮБОЙ другой целью
# терял выбор и после Save превращался в «Startseite» (аудит 2026-08-07). Реестр
# один, чтобы новая страница появлялась в редакторе сама.
PAGE_TARGET_LABELS = {
    "home": _("Startseite"),
    "about": _("Über uns"),
    "gallery": _("Galerie"),
    "team": _("Unser Team"),
    "reviews": _("Bewertungen"),
    "loyalty": _("Treue"),
    "gift": _("Geschenkgutschein"),
    "combos": _("Kombi-Angebote"),
    "finder": _("Finder"),
    "wishlist": _("Merkzettel"),
    "account": _("Mein Konto"),
    "contact": _("Kontakt"),
}


def page_target_choices() -> list[dict]:
    """[{value, label}] всех страниц-целей меню — для селекта в редакторе.
    `offers` не показываем: это легаси-алиас главной."""
    return [
        {"value": key, "label": str(PAGE_TARGET_LABELS[key])}
        for key in _PAGE_URL_NAMES
        if key in PAGE_TARGET_LABELS
    ]


# Гейт по МОДУЛЮ для страниц, у которых он есть (пункт гаснет при выключенном
# модуле — как у archetype-узлов). Ключ = target страницы.
_PAGE_MODULE_GATES = {
    "loyalty": "loyalty",
    "gift": "gift",
    # MEN-3: у "combos" модульного гейта больше НЕТ — страница видна по каталогу
    # (core-модуль, всегда активен), browse-only кейтеринг показывает наборы как
    # Speisekarte; пункт меню держит контент-гейт (наборы существуют) ниже.
    # finder — ОПЦИЯ, а не модуль реестра: у него свой гейт finder.enabled ниже
    # (is_module_active("finder") всегда False и гасил бы пункт).
    "wishlist": "orders",
    "account": "customer_account",
    "contact": "inbox",
}

# ST-8: чем «наполнена» страница (ключ site_config или запрос) — гейт пункта меню.
_PAGE_CONTENT_GATES = ("gallery", "team", "reviews", "combos")


def _content_probe(tenant, target: str) -> bool:
    """Проверка наполненности. Запросы — fail-closed: сбой чтения прячет ПУНКТ
    МЕНЮ, но не роняет страницу (то же правило, что у `storefront_reviews`)."""
    if target != "combos":
        cfg = siteconfig.normalize(tenant.site_config)
        if target == "gallery":
            return bool(cfg.get("gallery") or cfg.get("gallery_video"))
        if target == "team":
            return bool(cfg.get("team"))
        # reviews: кураторские `testimonials` отвечают без запроса.
        if cfg.get("testimonials"):
            return True
    try:
        if target == "combos":
            # Модуль orders активен почти у всех, но наборы есть у единиц — без
            # гейта пункт «Kombi-Angebote» встал бы в шапку каждого тенанта и вёл
            # на пустую страницу.
            from apps.catalog.models import Combo

            return Combo.objects.filter(is_active=True).exists()
        # reviews: портальные BusinessReview — SHARED-модель, читаем по schema_name.
        from django.db import connection

        from apps.aggregator.models import BusinessReview

        return BusinessReview.objects.filter(
            tenant_schema=connection.schema_name, status=BusinessReview.STATUS_PUBLISHED
        ).exists()
    except Exception:  # noqa: BLE001 — гейт пункта меню не должен ронять страницу
        return False


def _page_has_content(tenant, target: str) -> bool:
    """Есть ли что показать на странице ST-8 (иначе пункт меню гасим).

    Результат мемоизируется на объекте тенанта: `resolve_menu` вызывается на
    КАЖДЫЙ рендер (шапка + нижнее меню витрины, контекст-процессор кабинета), а
    гейты `reviews`/`combos` ходят в БД — без мемо это лишние запросы на каждой
    странице. Живёт ровно столько, сколько живёт tenant-объект запроса.
    """
    if target not in _PAGE_CONTENT_GATES:
        return True
    memo = getattr(tenant, "_menu_content_memo", None)
    if memo is None:
        memo = {}
        try:
            tenant._menu_content_memo = memo
        except AttributeError:  # объект без __dict__ — просто считаем каждый раз
            return _content_probe(tenant, target)
    if target not in memo:
        memo[target] = _content_probe(tenant, target)
    return memo[target]


def _gift_reachable(tenant) -> bool:
    """`/gutschein/` живёт не только на модуле gift: без настроенной онлайн-оплаты
    страница отдаёт 404 (`gift_purchase_active`). Тот же гейт, что у ссылки в
    футере (`seo.gift_link_active`) и у плитки первого экрана."""
    try:
        from apps.loyalty.public_views import gift_purchase_active

        return gift_purchase_active(tenant)
    except Exception:  # noqa: BLE001
        return False


def _reverse(name: str):
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


def _reverse_args(name: str, *args):
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        return None


def _archetype_url(tenant, key: str):
    spec = modules.get_module(key)
    if spec is None or not spec.storefront_landing:
        return None
    if not modules.is_module_active(tenant, key):
        return None
    return _reverse(spec.storefront_landing)


def _category_url(tenant, slug: str):
    # KAT-1: категория = страница /sortiment/<slug>/ (фильтр ?kategorie= умер
    # из внутренних ссылок; правка одной функции чинит меню всех демо-китов).
    if not slug or not modules.is_module_active(tenant, "catalog"):
        return None
    from apps.catalog.models import Category

    if not Category.objects.filter(slug=slug, is_active=True).exists():
        return None
    return _reverse_args("storefront-category", slug)


def _category_children(tenant, parent_slug: str):
    """MEN-15: дети узла «Kategorien» — живые категории каталога, ОДНИМ запросом.

    Запрос владельца (2026-08-13): «настройка выводить категории во 2-й уровень
    меню с картинками». Список не ведётся руками: добавил категорию — она в
    меню. `parent_slug` пуст → корневые категории; иначе подкатегории названной.

    Ссылка обязана совпадать с плиткой категории (`_category_tile.html`):
    KAT-1 — всегда страница категории /sortiment/<slug>/.

    Мемо на объекте тенанта — как `_page_has_content`: меню резолвится на каждый
    рендер (шапка, нижнее меню, контекст-процессор), а это запрос в БД.
    """
    # catalog — core-модуль (всегда активен): проверка защищает лишь от будущей
    # смены спеки, реальным гейтом служит пустой список категорий.
    if not modules.is_module_active(tenant, "catalog"):
        return []
    memo = getattr(tenant, "_menu_categories_memo", None)
    if memo is None:
        memo = {}
        try:
            tenant._menu_categories_memo = memo
        except AttributeError:
            memo = None
    if memo is not None and parent_slug in memo:
        return memo[parent_slug]

    try:
        from apps.catalog.models import Category

        qs = Category.objects.filter(is_active=True)
        if parent_slug:
            # Ревью MEN-15: JOIN по родителю не наследует ни is_active, ни
            # soft-delete менеджера — без явных условий в подменю попадали дети
            # выключенной и даже удалённой ветки (slug переиспользуем).
            qs = qs.filter(
                parent__slug=parent_slug,
                parent__is_active=True,
                parent__deleted_at__isnull=True,
            )
        else:
            qs = qs.filter(parent__isnull=True)
        rows = list(qs.order_by("sort_order", "slug")[:_MAX_MENU_CATEGORIES])
    except Exception:  # noqa: BLE001 — узел меню не должен ронять страницу
        rows = []

    out = []
    for cat in rows:
        # KAT-1: одна цель — страница категории (ветвление лендинг/фильтр умерло).
        url = _reverse_args("storefront-category", cat.slug)
        if not url:
            continue
        out.append(
            {
                "label": cat.get_i18n("name"),
                "url": url,
                "icon": cat.icon or "",
                "image": cat.image_url,
                # MEN-20 (фидбэк «субменю разнообразить, добавить описания»):
                # короткое описание категории под названием плитки. Обрезает
                # шаблон (truncatechars) — здесь данные без вёрстки.
                "desc": cat.get_i18n("description"),
                "children": [],
            }
        )
    if memo is not None:
        memo[parent_slug] = out
    return out


def _combo_children(tenant, category_slug: str):
    """Плитки НАБОРОВ меню для подменю (фидбэк владельца 2026-08-26).

    «Оставить меню картинками по наборам и категориям» — рядом с плитками
    категорий встают сами наборы, чтобы гость видел их прямо из шапки, не
    проваливаясь на отдельную страницу «Menüs & Pakete».

    Берём наборы указанной категории (пусто = все активные). Как и у категорий,
    сюда едут только данные: обрезку описания и вёрстку делает шаблон.
    """
    if not modules.is_module_active(tenant, "catalog"):
        return []
    try:
        from apps.catalog.models import Combo

        qs = Combo.objects.filter(is_active=True, deleted_at__isnull=True)
        if category_slug:
            qs = qs.filter(category__slug=category_slug)
        rows = list(qs.order_by("sort_order", "name")[:_MAX_MENU_CATEGORIES])
    except Exception:  # noqa: BLE001 — узел меню не должен ронять страницу
        rows = []

    out = []
    for combo in rows:
        url = _reverse_args("storefront-combo", combo.pk)
        if not url:
            continue
        images = combo.images or []
        first = images[0] if images else None
        image = first.get("url") if isinstance(first, dict) else (first or "")
        out.append(
            {
                # У набора имя — плоское поле + оверлей переводов (не JSON-поле,
                # как у категории), поэтому `*_localized`, а не `get_i18n`:
                # иначе плитка приходит без подписи (поймано замком).
                "label": combo.name_localized(),
                "url": url,
                "icon": "",
                "image": image or "",
                "desc": combo.description_localized(),
                "children": [],
            }
        )
    return out


def _promo_group_url(tenant, group: str):
    if not group or not modules.is_module_active(tenant, "promotions"):
        return None
    from apps.promotions.models import Promotion

    if not Promotion.objects.filter(status="active", group=group).exists():
        return None
    base = _reverse("storefront-aktionen")
    if not base:
        return None
    from urllib.parse import quote

    return f"{base}?gruppe={quote(group)}"


def _node_url(tenant, node: dict):
    ntype, target = node["type"], node["target"]
    if ntype == "archetype":
        return _archetype_url(tenant, target)
    if ntype == "category":
        return _category_url(tenant, target)
    if ntype == "categories":
        # MEN-15: сам пункт кликабелен, подменю — категории. При заданном
        # target узел означает КОНКРЕТНУЮ ветку, поэтому и ведёт в неё (ревью:
        # раньше «Essen» с подменю своих подкатегорий открывал весь каталог).
        if not modules.is_module_active(tenant, "catalog"):
            return None
        return _category_url(tenant, target) or _reverse("storefront-products")
    if ntype == "promo_group":
        return _promo_group_url(tenant, target)
    if ntype == "page":
        name = _PAGE_URL_NAMES.get(target)
        if not name or not _page_has_content(tenant, target):
            return None
        gate = _PAGE_MODULE_GATES.get(target)
        if gate and not modules.is_module_active(tenant, gate):
            return None
        if target == "finder":
            from apps.core import finder as _finder

            if not _finder.enabled(tenant):
                return None
        if target == "gift" and not _gift_reachable(tenant):
            return None
        return _reverse(name)
    if ntype == "url":
        return target or None
    if ntype == "anchor":
        if not target:
            return None
        return target if target.startswith(("#", "/")) else f"/#{target}"
    # group: своей ссылки нет — родитель выпадающего подменю, держится на детях.
    # Фидбэк 2026-07-30 («кнопка Акция не кликабельная»): если ВСЕ дети —
    # promo_group, у группы есть осмысленная цель — страница всех акций;
    # клик по пункту ведёт туда, hover по-прежнему раскрывает подменю.
    if ntype == "group":
        kids = node.get("children") or []
        if kids and all(k.get("type") == "promo_group" for k in kids):
            return (
                _reverse("storefront-aktionen") if tenant.is_module_active("promotions") else None
            )
    return None


# Якоря перевода: стандартные подписи меню приходят из ДАННЫХ (site_config/демо-
# киты), а не из gettext-литералов, поэтому makemessages их не извлечёт. Перечисляем
# их здесь gettext_lazy, чтобы msgid'ы жили в каталогах и переводились на язык
# витрины через фолбэк _node_label. (Кастомные подписи владельца — не msgid'ы,
# gettext вернёт их без изменений.)
_MENU_LABEL_ANCHORS = (
    _("Start"),
    _("Galerie"),
    _("Zimmer & Preise"),
    _("Bewertungen"),
    _("Hausordnung"),
    _("FAQ"),
    _("Über uns"),
    _("Kontakt"),
    _("Jetzt buchen"),
    _("Buchen"),
    _("Zimmer"),
    _("Speisekarte"),
    _("Angebote"),
    _("Termine"),
    _("Leistungen"),
    _("Anfahrt"),
    # ST-8: подписи новых страниц (галерея/отзывы/команда) в демо-меню.
    _("Unser Team"),
    _("Meister"),
    _("Referenzen"),
    # 2026-08-06 (аудит демо): 23 подписи демо-меню не были объявлены здесь и
    # потому оставались немецкими на всех языках витрины.
    _("Damen"),
    _("Herren"),
    _("Accessoires"),
    _("Shop"),
    _("Catering"),
    _("Retreats"),
    _("Touren"),
    _("Events & Ausflüge"),
    _("Wellness & Extras"),
    _("Treue & Aktionen"),
    _("Einzelsitzung"),
    _("Sitzung"),
    _("Lehrer"),
    _("Teile"),
    _("Partyservice"),
    _("Party"),
    _("Korb"),
    _("Vorbestellung"),
    _("Wochenangebote"),
    _("Hausmacher-Wochen"),
    _("Dauertiefpreis"),
    _("Anti-Food-Waste"),
    _("Räumung"),
    # Аудит 2026-08-06: размещение ретрита в меню (номера/места в общей комнате).
    _("Unterkunft"),
    # MEN-20: наборы меню — ручной ребёнок подменю «Speisekarte» кита catering.
    _("Menüs & Pakete"),
    # Catering-Welle 2026-08-25: подменю «Catering» у pranasy (Speisekarte /
    # Menüs & Pakete / Anfrage) — якорь держит msgid при makemessages.
    _("Anfrage"),
    # Фидбэк 2026-08-26: «наша работа» — галерея работ в подменю кейтеринга.
    _("Unsere Arbeit"),
)


def _node_label(node: dict) -> str:
    """Подпись узла на текущей локали (i18n): явный `label_i18n[locale]` →
    иначе gettext базовой подписи. Стандартные пункты («Kontakt», «Galerie»,
    «Jetzt buchen» …) — msgid'ы хрома и переводятся на язык витрины; кастомные
    подписи владельца не являются msgid'ами → gettext вернёт их без изменений."""
    from django.utils.translation import get_language, gettext

    li18n = node.get("label_i18n") or {}
    explicit = li18n.get(get_language() or "de")
    return explicit or gettext(node["label"])


def _resolve(tenant, node: dict):
    if not node.get("enabled", True):
        return None
    children = [c for c in (_resolve(tenant, k) for k in node.get("children", [])) if c]
    if node["type"] == "categories":
        # MEN-15: дети собираются из живых категорий (владелец список не ведёт).
        # Ручные дети, если их положили, остаются впереди авто-списка.
        children = children + _category_children(tenant, node["target"])
        # Фидбэк 2026-08-26: у гастро в то же подменю едут наборы меню —
        # «картинками по наборам и категориям».
        if node.get("with_combos"):
            children = children + _combo_children(tenant, node["target"])
    url = _node_url(tenant, node)
    if url is None and not children:
        return None
    return {
        "label": _node_label(node),
        "url": url,
        "icon": node.get("icon", ""),
        "children": children,
        # MEN-15: подсказка рендеру — рисовать подменю плитками с фото. Считаем
        # здесь, а не в шаблоне: у категории без фото плитка выродится в серый
        # прямоугольник, поэтому сетку включаем только если фото ЕСТЬ.
        "has_images": any(c.get("image") for c in children),
    }


def resolve_menu(tenant, side: str) -> list[dict]:
    """Готовое дерево пунктов для стороны меню ('top' | 'bottom')."""
    cfg = siteconfig.normalize(tenant.site_config)["menus"].get(side, {})
    return [r for r in (_resolve(tenant, n) for n in cfg.get("items", [])) if r]


def top_meta(tenant) -> tuple[str, bool]:
    """(style, sticky) верхнего меню."""
    top = siteconfig.normalize(tenant.site_config)["menus"]["top"]
    return top["style"], top["sticky"]


def bottom_enabled(tenant) -> bool:
    return siteconfig.normalize(tenant.site_config)["menus"]["bottom"]["enabled"]
