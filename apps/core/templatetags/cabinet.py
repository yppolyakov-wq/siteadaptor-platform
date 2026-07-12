"""Шаблонные теги кабинета (AB1 язык задач + анти-Битрикс v2 хаб-табы)."""

from django import template
from django.utils.translation import gettext_lazy as _

from apps.core import modules

register = template.Library()


@register.simple_tag(takes_context=True)
def status_label(context, obj, kind="order"):
    """FB-4a: имя статуса в кабинете — своё имя владельца (site_config["status_labels"])
    или дефолт. FB-3 Вариант B Phase 6: для КАСТОМ-статуса дефолт = его label (иначе
    get_status_display вернул бы код). FSM/письма/витрину не трогает."""
    from apps.core import status_registry

    tenant_obj = getattr(context.get("request"), "tenant", None)
    d = status_registry.resolve(kind, obj.status, tenant_obj)
    if d is not None and not d.builtin and d.label:
        default = d.label
    elif hasattr(obj, "get_status_display"):
        default = obj.get_status_display()
    else:
        default = str(obj.status)
    cfg = getattr(tenant_obj, "site_config", None)
    if not isinstance(cfg, dict):
        return default
    labels = cfg.get("status_labels")
    if not isinstance(labels, dict):
        return default
    node = labels.get(kind)
    if not isinstance(node, dict):
        return default
    return node.get(obj.status) or default


@register.simple_tag
def nav_task_label(nav_key):
    """AB1: подпись пункта сайдбара в языке задач (nav_key → DE-метка) или "" —
    тогда шаблон берёт фолбэк NavItem.label. Реестр — modules.NAV_TASK_LABELS."""
    return modules.nav_task_label(nav_key or "")


# S1/S2/S3 (упрощение кабинета): под-страницы хаба = tab-bar над контентом. Один пункт
# сайдбара → страница-хаб с табами. Кортеж (url_name, метка, nav_key, module_key, advanced):
# активный таб по context["nav"]; module_key (или None) — таб виден только при
# is_module_active(tenant, module_key), None = всегда (под-страница ядра); advanced=True —
# таб уходит в свёрнутый ящик «Erweitert» (реже нужные настройки). Расширяется по мере
# сведения хабов (Marketing/Kunden — след. инкременты).
HUB_TABS = {
    # Sortiment: под-страницы каталога (модуль core → всегда, module_key=None).
    "catalog": (
        ("catalog:product-list", _("Produkte"), "catalog", None, False),
        ("catalog:category-list", _("Kategorien"), "categories", None, False),
        ("stock", _("Lager"), "stock", None, False),
        ("catalog:combo-list", _("Kombi"), "combos", None, False),
        ("imports:start", _("Import"), "imports", None, False),
    ),
    # Verkäufe: доска (kanban, core) + продажные списки/календари. Табы продаж
    # гейтятся по своему модулю — Friseur без Übernachtung/Tickets их не покажет.
    "board": (
        ("board", _("Board"), "board", "board", False),
        ("orders:order-list", _("Bestellungen"), "orders", "orders", False),
        ("booking:calendar", _("Termine"), "booking", "booking", False),
        ("stays:calendar", _("Übernachtungen"), "stays", "stays", False),
        ("events:list", _("Tickets"), "events", "events", False),
        ("jobs:list", _("Aufträge"), "jobs", "jobs", False),
    ),
    # Marketing (S4a): акции/отзывы/лояльность/публикация. Якорь-пункт «Marketing»
    # на модуле promotions; каждая вкладка гейтится по своему модулю (Friseur без
    # publishing не покажет Kanäle/Beiträge). Часто нужные — прямые, редкие — в Erweitert.
    "marketing": (
        ("promotions:promotion-list", _("Aktionen"), "promotions", "promotions", False),
        ("reviews:list", _("Bewertungen"), "reviews", "reviews", False),
        ("promotions:coupon-campaigns", _("Kampagnen"), "campaigns", "crm", False),
        ("promotions:voucher-list", _("Gutscheine"), "vouchers", "loyalty", False),
        ("promotions:reservation-list", _("Reservierungen"), "reservations", "promotions", True),
        ("promotions:redeem", _("Einlösen"), "redeem", "promotions", True),
        ("promotions:loyalty-list", _("Treuepunkte"), "loyalty", "loyalty", True),
        ("channels", _("Kanäle"), "channels", "publishing", True),
        ("publishing-posts", _("Beiträge"), "posts", "publishing", True),
    ),
    # Kunden (S4b): контакты + общение. Якорь-пункт «Kunden» на модуле crm; вкладки
    # Nachrichten/Telegram гейтятся по своему модулю.
    "kunden": (
        ("crm:customer-list", _("Kontakte"), "crm", "crm", False),
        ("inbox:list", _("Nachrichten"), "inbox", "inbox", False),
        ("telegram-settings", _("Telegram"), "telegram", "telegram", False),
    ),
    # Einstellungen: часто нужные настройки — прямые табы; реже нужные — в «Erweitert».
    # Модуль settings core → всё всегда видно (module_key=None). «Website» (визуальный
    # билдер) остаётся ОТДЕЛЬНЫМ пунктом сайдбара, в хаб не входит.
    "settings": (
        ("settings", _("Einstellungen"), "settings", None, False),
        # W4-3: единый экран оплаты/доставки (свод billing-Zahlarten + orders-Versand).
        ("payment-settings", _("Zahlung & Versand"), "payments", None, False),
        ("notifications-settings", _("Benachrichtigungen"), "notifications", None, False),
        ("legal-docs", _("Rechtstexte"), "legal-docs", None, False),
        ("extras", _("Zusatzleistungen"), "extras", None, False),
        # Sprachen — прямой таб (не в «Erweitert»): владелец включает доп. языки витрины
        # и переключатель. Прежде был спрятан в ящике → «не видно настроек языка».
        ("languages", _("Sprachen"), "languages", None, False),
        ("media-library", _("Medien"), "media", None, True),
        ("domains", _("Domains"), "domains", None, True),
        ("modules", _("Funktionen"), "modules", None, True),
        ("support:help", _("Hilfe"), "support", None, True),
    ),
}


@register.inclusion_tag("tenant/_hub_tabs.html", takes_context=True)
def hub_tabs(context, hub):
    """Отрисовать tab-bar хаба `hub` (реестр HUB_TABS), подсветив активный по `nav`.

    Табы с module_key прячутся, если модуль не активен у тенанта (fail-open, если
    request/tenant в контексте нет — простой тест-рендер без запроса). advanced-табы
    уходят в свёрнутый ящик «Erweitert» (открыт, если активна одна из его вкладок)."""
    cur = context.get("nav")
    request = context.get("request")
    tenant = getattr(request, "tenant", None) if request is not None else None
    tabs, more = [], []
    for u, lbl, k, mod, advanced in HUB_TABS.get(hub, ()):
        if mod is not None and tenant is not None and not modules.is_module_active(tenant, mod):
            continue
        entry = {"url_name": u, "label": lbl, "nav_key": k, "active": k == cur}
        (more if advanced else tabs).append(entry)
    return {"tabs": tabs, "more_tabs": more, "more_active": any(t["active"] for t in more)}
