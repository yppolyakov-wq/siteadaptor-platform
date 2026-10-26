"""KA-12 E6.7b: какое право нужно каждому экрану кабинета.

Один реестр по имени маршрута (``namespace:name``): право на чтение (GET/HEAD/OPTIONS)
и на запись (POST и прочее). Проверяет ``CabinetOwnerAccessMiddleware.process_view`` —
поэтому покрыты и пути с uuid посередине. Новый экран кабинета ОБЯЗАН попасть сюда
(замок ``test_view_perms``); незарегистрированный экран на проде — 403 (fail-closed).

``FLOOR`` — Inhaber-Vorbehalt (Abo, Recht/Impressum, импорт с чужого сайта): только
владелец, никому не выдаётся. ``OPEN`` — экран для всех членов команды (главная,
поиск, язык, помощь, редиректы-лендинги).

E6.7b: правила повторяют сегодняшний доступ (паритет держат замки); точечные проверки
внутри экранов (тарифы, возвраты, Gutschrift…) остаются в самих вьюхах.
"""

import logging
from dataclasses import dataclass
from functools import wraps

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from . import permissions

logger = logging.getLogger(__name__)

FLOOR = "floor"
OPEN = "open"
_MARKERS = (FLOOR, OPEN)

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


@dataclass(frozen=True)
class Rule:
    read: str
    write: str


def _r(read, write=None):
    return Rule(read, write or read)


V, E = "verkaeufe.view", "verkaeufe.edit"
S, SE = "sortiment.view", "sortiment.edit"
M, ME = "marketing.view", "marketing.edit"
W, WE = "website.view", "website.edit"
CFG, CFGE = "einstellungen.view", "einstellungen.edit"
A, AE = "ablaeufe.view", "ablaeufe.edit"
L, LE = "lager.view", "lager.edit"
K, KE = "kunden.view", "kunden.edit"
N, NE = "nachrichten.view", "nachrichten.edit"
FJ, FE = "finanzen.journal", "finanzen.edit"

RULES: dict[str, Rule] = {
    # --- для всех ---------------------------------------------------------------
    "dashboard": _r(OPEN),
    "einstellungen-home": _r(OPEN),
    "integrations-home": _r(OPEN),  # 302 на первый доступный экран
    "marketing-home": _r(OPEN),  # 302 на первый доступный экран
    "palette-search": _r(OPEN),  # результаты маскируются по праву kunden.kontakte
    "set-cabinet-lang": _r(OPEN),
    "support:help": _r(OPEN),
    "support:thread": _r(OPEN),
    # --- Inhaber-Vorbehalt --------------------------------------------------------
    "billing": _r(FLOOR),
    "billing-checkout": _r(FLOOR),
    "billing-payments": _r(FLOOR),
    "billing-payments-callback": _r(FLOOR),
    "billing-payments-connect": _r(FLOOR),
    "billing-payments-methods": _r(FLOOR),
    "billing-portal": _r(FLOOR),
    "legal-docs": _r(FLOOR),
    "lite-business": _r(FLOOR),
    "imports:website": _r(FLOOR),
    "imports:website-run": _r(FLOOR),
    # --- Verkäufe -----------------------------------------------------------------
    "verkaeufe": _r(V, E),
    "verkaeufe-bulk": _r(V, E),
    "verkaeufe-view": _r(V, E),  # пишет общий для всех вид списка
    "verkaeufe-zusatz": _r(V, E),
    "verkaeufe-export": _r("kunden.export"),
    "board": _r(V, E),
    "board-action": _r(V, E),
    "board-settings": _r(A, AE),
    "payments-page": _r(V, E),
    "lite-requests": _r(V, E),
    "community:event-space": _r(V, E),
    "deal-billing-edit": _r(V, E),
    "deal-customer-edit": _r(V, E),
    "deal-external-edit": _r(V, E),
    "deal-link": _r(V, E),
    "deal-unlink": _r(V, E),
    "deal-discount-edit": _r(V, "geld.rabatt"),
    "deal-pay-link": _r(V, "geld.zahlungslink"),
    "deal-invoice": _r(V, FE),
    "deal-refund": _r("geld.korrektur"),
    "deal-advance-invoice": _r("finanzen.korrektur"),
    "booking:calendar": _r(V, E),
    "booking:booking-action": _r(V, E),
    "booking:booking-create": _r(V, E),
    "booking:booking-detail": _r(V, E),
    "booking:tischplan": _r(V, E),
    "orders:order-list": _r(V, E),
    "orders:order-detail": _r(V, E),
    "orders:order-edit": _r(V, E),
    "orders:order-action": _r(V, E),
    "orders:order-delivery-note": _r(V),
    "orders:delivery-notes": _r(V),
    "orders:deliveries": _r(V, E),
    "orders:kitchen": _r(V, E),
    "orders:production": _r(V),
    "orders:kitchen-board": _r(V, E),
    "orders:kitchen-action": _r(V, E),
    "orders:table-qr": _r(CFG),
    "jobs:list": _r(V, E),
    "jobs:new": _r(V, E),
    "jobs:detail": _r(V, E),
    "jobs:delete": _r(V, E),
    "jobs:pdf": _r(V),
    "jobs:protocol-pdf": _r(V),
    "jobs:invoice-pdf": _r(V),
    "jobs:anfrage-form-settings": _r(A, AE),
    "stays:calendar": _r(V, E),
    "stays:today": _r(V, E),
    "stays:checkins": _r(V, E),
    "stays:booking-detail": _r(V, E),
    "stays:booking-delete": _r(V, E),
    "stays:stay-action": _r(V, E),
    "stays:stay-create": _r(V, E),
    "stays:stay-new": _r(V, E),
    "stays:room-clean": _r(V, E),
    "stays:reports-export": _r("kunden.export"),
    "stays:meldescheine-export": _r("kunden.export"),
    "stays:meldeschein-pdf": _r("kunden.edit"),
    "events:ticket-action": _r(V, E),
    "events:ticket-add": _r(V, E),
    "events:ticket-detail": _r(V, E),
    "events:checkin": _r(V, E),
    "events:documents": _r(V, E),
    "events:logistics": _r(V, E),
    "events:waitlist-notify": _r(V, E),
    "events:roster-csv": _r("kunden.export"),
    "promotions:reservation-list": _r(V, E),
    "promotions:reservation-action": _r(V, E),
    "promotions:redeem": _r("geld.einloesen"),
    "promotions:redeem-detail": _r("geld.einloesen"),
    "promotions:redeem-action": _r("geld.einloesen"),
    "promotions:voucher-redeem": _r("geld.einloesen"),
    "promotions:loyalty-stamp": _r("geld.einloesen"),
    # --- Abläufe ------------------------------------------------------------------
    "ablaeufe": _r(A, AE),
    "status-labels-save": _r(A, AE),
    "status-manager": _r(A, AE),
    "status-manager-save": _r(A, AE),
    "transitions-save": _r(A, AE),
    # --- Sortiment ----------------------------------------------------------------
    "sellable-manage": _r(S, SE),
    "sellable-sold-out": _r(S, SE),
    "sellable-visibility": _r(S, SE),
    "sortiment-view": _r(S, SE),  # пишет общий для всех вид списка
    "city-freshness-confirm": _r(S, SE),
    "collections:list": _r(S, SE),
    "booking:services": _r(S, SE),
    "booking:service-edit": _r(S, SE),
    "booking:service-inline-edit": _r(S, SE),
    "booking:service-photo-edit": _r(S, SE),
    "booking:passes": _r(S, SE),
    "stays:units": _r(S, SE),
    "stays:unit-edit": _r(S, SE),
    "stays:stay-inline-edit": _r(S, SE),
    "stays:stay-photo-edit": _r(S, SE),
    "stays:price-calendar": _r("preise.view", "preise.edit"),
    "stays:price-calendar-apply": _r("preise.view", "preise.edit"),
    "stays:price-day": _r("preise.view", "preise.edit"),
    "events:list": _r(S, SE),
    "events:create": _r(S, SE),
    "events:detail": _r(S, SE),
    "events:edit": _r(S, SE),
    "events:action": _r(S, SE),  # отмена — точечно veranstaltung.absagen
    "events:series": _r(S, SE),
    "events:event-inline-edit": _r(S, SE),
    "events:event-photo-edit": _r(S, SE),
    "events:teacher-list": _r(S, SE),
    "events:teacher-create": _r(S, SE),
    "events:teacher-edit": _r(S, SE),
    "events:teacher-delete": _r(S, "sortiment.delete"),
    "events:tour-list": _r(S, SE),
    "events:tour-edit": _r(S, SE),
    "stock": _r(L, LE),
    "purchasing": _r(L, LE),
    "purchasing-maengel-pdf": _r(L),
    "imports:start": _r(L, LE),
    "imports:map": _r(L, LE),
    "imports:preview": _r(L, LE),
    "imports:status": _r(L, LE),
    # Каталог: удаление позиции — отдельное действие (фото — правка).
    "catalog:category-create": _r(S, SE),
    "catalog:category-delete": _r(S, "sortiment.delete"),
    "catalog:category-edit": _r(S, SE),
    "catalog:category-image-delete": _r(S, SE),
    "catalog:category-image-primary": _r(S, SE),
    "catalog:category-inline-edit": _r(S, SE),
    "catalog:category-list": _r(S, SE),
    "catalog:combo-create": _r(S, SE),
    "catalog:combo-delete": _r(S, "sortiment.delete"),
    "catalog:combo-edit": _r(S, SE),
    "catalog:combo-group-add": _r(S, SE),
    "catalog:combo-group-delete": _r(S, "sortiment.delete"),
    "catalog:combo-group-update": _r(S, SE),
    "catalog:combo-image-delete": _r(S, SE),
    "catalog:combo-image-primary": _r(S, SE),
    "catalog:combo-list": _r(S, SE),
    "catalog:combo-option-add": _r(S, SE),
    "catalog:combo-option-delete": _r(S, "sortiment.delete"),
    "catalog:combo-option-update": _r(S, SE),
    "catalog:modifier-group-add": _r(S, SE),
    "catalog:modifier-group-delete": _r(S, "sortiment.delete"),
    "catalog:modifier-group-update": _r(S, SE),
    "catalog:modifier-option-add": _r(S, SE),
    "catalog:modifier-option-delete": _r(S, "sortiment.delete"),
    "catalog:modifier-option-update": _r(S, SE),
    "catalog:product-create": _r(S, SE),
    "catalog:product-delete": _r(S, "sortiment.delete"),
    "catalog:product-edit": _r(S, SE),
    "catalog:product-image-delete": _r(S, SE),
    "catalog:product-image-primary": _r(S, SE),
    "catalog:product-inline-edit": _r(S, SE),
    "catalog:product-list": _r(S, SE),
    "catalog:product-photo-edit": _r(S, SE),
    "catalog:products-merge": _r(S, SE),
    "catalog:products-bulk-visibility": _r(S, SE),
    "catalog:products-bulk-price": _r(S, "preise.edit"),
    "catalog:products-export-csv": _r("lager.export"),
    "catalog:variant-add": _r(S, SE),
    "catalog:variant-generate": _r(S, SE),
    "catalog:variant-color-photo": _r(S, SE),
    "catalog:variant-delete": _r(S, "sortiment.delete"),
    "catalog:variant-update": _r(S, SE),
    # --- Kunden & Nachrichten -------------------------------------------------------
    "crm:customer-list": _r(K, KE),
    "crm:customer-create": _r(K, KE),
    "crm:customer-detail": _r(K, KE),
    "crm:note-add": _r(K, KE),
    "crm:company-list": _r(K, KE),
    "crm:company-create": _r(K, KE),
    "crm:company-detail": _r(K, KE),
    "crm:company-delete": _r(K, KE),
    "crm:customer-export": _r("kunden.export"),
    "crm:customer-dsgvo": _r("kunden.dsgvo"),
    "crm:customer-dsgvo-export": _r("kunden.dsgvo"),
    "crm:customer-dsgvo-erase": _r("kunden.dsgvo"),
    "inbox:list": _r(N, NE),
    "inbox:thread": _r(N, NE),
    "inbox:thread-poll": _r(N, NE),
    "inbox:thread-typing": _r(N, NE),
    "inbox:unread-count": _r(N),
    "inbox:deal-thread": _r(N, NE),
    "inbox:offer-compose": _r(N, NE),
    "inbox:reply-draft": _r(N, NE),
    "inbox:reply-draft-result": _r(N, NE),
    # --- Marketing -----------------------------------------------------------------
    "blog-list": _r(M, ME),
    "blog-edit": _r(M, ME),
    "publishing-posts": _r(M, ME),
    "finder-settings": _r(M, ME),
    "lite-share": _r(M, ME),
    "lite-visibility": _r(M, ME),
    "reviews:list": _r(M, ME),
    "reviews:reply": _r(M, ME),
    "reviews:toggle": _r(M, ME),
    "reviews:business-reply": _r(M, ME),
    "booking:no-show-rule": _r(CFG, CFGE),
    "booking:table-rules": _r(CFG, CFGE),
    "portal-stats": _r("stadtportal.view"),
    "channels": _r("kanaele.view", ME),
    "channel-config": _r("kanaele.edit"),
    "channel-oauth-start": _r("kanaele.edit"),
    "channel-toggle": _r("kanaele.edit"),
    "gbp-sync": _r("kanaele.edit"),
    "gbp-location": _r("kanaele.edit"),
    "gbp-hours": _r("kanaele.edit"),
    "gbp-merchant": _r("kanaele.edit"),
    "telegram-settings": _r(CFG, CFGE),
    # E6.7c-4 (ревью A1): токен своего бота подменяет бота клиентов, ссылка общего бота
    # привязывает чат к владельцу — Inhaber-Vorbehalt, никому не выдаётся.
    "telegram-connect": _r(FLOOR),
    "telegram-disconnect": _r(FLOOR),
    "platform-bot-connect": _r(FLOOR),
    "platform-bot-disconnect": _r(FLOOR),
    "integrations-telegram-activate": _r(FLOOR),
    "catalog:combo-feature": _r(M, ME),
    "catalog:combo-feature-checkout": _r(M, ME),
    "events:feature": _r(M, ME),
    "events:feature-checkout": _r(M, ME),
    "stays:unit-feature": _r(M, ME),
    "stays:unit-feature-checkout": _r(M, ME),
    # Акции
    "promotions:coupon-campaigns": _r(M, ME),
    "promotions:loyalty-list": _r(M, ME),
    "promotions:newsletter": _r(M, ME),
    "promotions:promo-type-list": _r(M, ME),
    "promotions:promo-type-save": _r(M, ME),
    "promotions:promotion-create": _r(M, ME),
    "promotions:promotion-edit": _r(M, ME),
    "promotions:promotion-feature": _r(M, ME),
    "promotions:promotion-feature-checkout": _r(M, ME),
    "promotions:promotion-flyer": _r(M, ME),
    "promotions:promotion-image-delete": _r(M, ME),
    "promotions:promotion-image-primary": _r(M, ME),
    "promotions:promotion-inline-edit": _r(M, ME),
    "promotions:promotion-list": _r(M, ME),
    "promotions:promotion-page-mode": _r(M, ME),
    "promotions:promotion-photo-edit": _r(M, ME),
    "promotions:promotion-preview": _r(M, ME),
    "promotions:promotion-quick": _r(M, ME),
    "promotions:promotion-quick-ai": _r(M, ME),
    "promotions:promotion-quick-ai-result": _r(M, ME),
    "promotions:promotion-quick-done": _r(M, ME),
    "promotions:promotion-share": _r(M, ME),
    "promotions:promotion-text-check": _r(M, ME),
    "promotions:promotion-text-check-ai": _r(M, ME),
    "promotions:promotion-text-check-ai-result": _r(M, ME),
    "promotions:promotion-transition": _r(M, ME),
    "promotions:shop-poster": _r(M, ME),
    "promotions:today-dismiss": _r(M, ME),
    "promotions:voucher-list": _r(M, ME),
    # --- Website ------------------------------------------------------------------
    "design": _r(W, WE),
    "media-library": _r(W, WE),
    "site": _r(W, WE),
    "site-home": _r(W, WE),
    "site-menu": _r(W, WE),
    "site-pages": _r(W, WE),
    "site-sections": _r(W, WE),
    "site-seo": _r(W, WE),
    "site-preview": _r(W, WE),
    "site-preview-draft": _r(W, WE),
    "site-share-preview": _r(W, WE),
    "site-inline-edit": _r(W, WE),
    "site-cblock-photo-edit": _r(W, WE),
    "site-scope-save": _r(W, WE),
    "site-scope-state": _r(W, WE),
    "domains": _r("domains.view", "domains.edit"),
    "domain-add": _r("domains.view", "domains.edit"),
    "domain-verify": _r("domains.view", "domains.edit"),
    "domain-remove": _r("domains.view", "domains.edit"),
    # --- Finanzen -----------------------------------------------------------------
    "finance:journal": _r(FJ, FE),
    "finance:invoices": _r(FJ, FE),
    "finance:invoice-detail": _r(FJ, FE),
    "finance:invoice-pdf": _r(FJ),
    "finance:invoice-mahnung": _r(FJ, FE),
    "finance:expenses": _r(FJ, FE),
    "finance:ergebnis": _r("finanzen.berichte"),
    "finance:offene": _r("finanzen.berichte", FE),
    "finance:customer-search": _r(FJ),
    "finance:bank": _r("finanzen.bank"),
    "finance:export-csv": _r("finanzen.export"),
    "finance:export-datev": _r("finanzen.export"),
    "finance:expenses-datev": _r("finanzen.export"),
    "promotions:analytics": _r(M),
    "stays:reports": _r("finanzen.berichte"),
    "stays:kurtaxe": _r("finanzen.berichte"),
    # --- Einstellungen ------------------------------------------------------------
    "settings": _r(CFG, CFGE),
    "setup": _r(CFG, CFGE),
    "languages": _r(CFG, CFGE),
    "notifications-settings": _r(CFG, CFGE),
    "payment-settings": _r(CFG, CFGE),  # IBAN — Vorbehalt внутри экрана
    "google-reviews-settings": _r(CFG, CFGE),
    "extras": _r(CFG, CFGE),
    "set-presence": _r(CFG, CFGE),
    "booking:resources": _r(CFG, CFGE),
    "booking:availability": _r(CFG, CFGE),
    "stays:channels": _r(CFG, CFGE),
    "modules": _r("funktionen.view", "funktionen.edit"),
    "betriebsferien": _r("betriebsferien.ganz"),
    "team": _r("team.view", "team.edit"),
}


def rule_for(view_name: str) -> Rule | None:
    """Правило экрана; None — экран не зарегистрирован (без правил «по умолчанию»:
    новый маршрут обязан быть записан явно — ревью безопасности E6.7b)."""
    return RULES.get(view_name or "")


def _check_registry() -> None:
    for rule in RULES.values():
        for key in (rule.read, rule.write):
            if key not in _MARKERS:
                permissions.check_key(key)


_check_registry()  # опечатка в реестре — падение при импорте, а не тихий 403


def _strict() -> bool:
    return bool(getattr(settings, "PERMS_STRICT", settings.DEBUG))


def allowed(user, view_name: str, method: str) -> bool:
    """Пускает ли экран ``view_name`` этого пользователя (член команды) этим методом."""
    rule = rule_for(view_name)
    if rule is None:
        if _strict():
            raise ImproperlyConfigured(
                f"Экран кабинета {view_name!r} без права — добавьте в apps/core/view_perms.py"
            )
        logger.error("view_perms: экран без права %r — 403", view_name)
        return False
    key = rule.read if (method or "GET").upper() in SAFE_METHODS else rule.write
    return _passes(user, key)


def allowed_quiet(user, view_name: str, method: str = "GET") -> bool:
    """``allowed`` для хрома (меню/палитра/плитки): незарегистрированный экран — False
    с записью в лог, без исключения strict-режима (рендер меню не должен падать)."""
    if rule_for(view_name) is None:
        logger.error("view_perms: ссылка на экран без права %r скрыта", view_name)
        return False
    return allowed(user, view_name, method)


def url_allowed(user, url: str, method: str = "GET") -> bool:
    """Ссылка/кнопка кабинета (готовый URL) — открывается ли этому пользователю. Не
    экран кабинета (витрина, чужой путь) — True: это не зона прав. Без пользователя —
    True (fail-open хрома; доступ держит middleware)."""
    if not url or user is None or not permissions.is_member(user):
        return True
    from urllib.parse import urlsplit

    from django.urls import Resolver404, resolve

    parts = urlsplit(url)
    try:
        name = resolve(parts.path).view_name
    except Resolver404:
        return True
    if rule_for(name) is None:
        return True
    query = f"?{parts.query}" if parts.query else ""
    return allowed_quiet(user, name, method) and query_allowed(user, name, query)


# E6.7e: вкладки-адреса одного экрана со СВОИМ правом (иначе — право экрана). Ту же
# карту проверяет сама страница: скрытие в меню без проверки на экране — косметика.
QUERY_RULES: dict[tuple[str, str], str] = {
    ("verkaeufe", "?tab=kunden"): "kunden.view",
}


def query_allowed(user, view_name: str, query: str) -> bool:
    key = QUERY_RULES.get((view_name, query or ""))
    return True if key is None else _passes(user, key)


def _passes(user, key: str) -> bool:
    if key == OPEN:
        return True
    if key == FLOOR:
        from .roles import is_owner

        return is_owner(user)
    return permissions.has_perm(user, key)


def perm_required(key: str):
    """Право прямо на вьюхе (под ``@login_required``): страхует прямые вызовы и пути,
    которые middleware не видит. Ключ обязан совпадать с правилом маршрута (замок)."""
    if key not in _MARKERS:
        permissions.check_key(key)

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not _passes(request.user, key):
                from django.http import HttpResponseForbidden
                from django.utils.translation import gettext as _

                return HttpResponseForbidden(_("Dafür fehlt Ihnen das Recht."))
            return view(request, *args, **kwargs)

        wrapper._required_perm = key
        return wrapper

    return decorator
