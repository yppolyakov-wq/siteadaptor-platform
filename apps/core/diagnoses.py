"""AIS-A A-0: реестр диагнозов помощника — «почему не работает» без ИИ.

Каждый диагноз — симптом → проверки → находки со ссылками. **Проверки вызывают настоящие
гейты витрины/каталога**, а не повторяют их условия (правка архитектора, план §12): гейты
зовутся через атрибут модуля (`storefront_state.hidden_reasons(t)`), чтобы замок мог
подменить гейт и увидеть, что вывод меняется. Список вызываемых гейтов — в `gates`.

Сбой проверки — находка «unknown» («Konnte nicht geprüft werden»), а не «всё хорошо»:
«alles in Ordnung» печатается только при нуле находок-проблем И нуле unknown.
Только чтение: ни одна проверка ничего не пишет и не выбирает данные клиентов."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

logger = logging.getLogger(__name__)

PROBLEM, INFO, UNKNOWN, OK = "problem", "info", "unknown", "ok"
CHEAP, HEAVY = "cheap", "heavy"
MAX_SERVICES = 5
MAX_PROMOS = 5
SLOT_DAYS = 14
ROOM_DAYS = 60


@dataclass(frozen=True)
class Finding:
    level: str
    text: str
    url_name: str = ""
    args: tuple = ()
    query: str = ""
    owner_only: bool = False
    method: str = "GET"


@dataclass(frozen=True)
class Diagnosis:
    key: str
    symptom: object  # lazy-строка
    cost: str
    applies: Callable
    run: Callable
    #: Вызываемые гейты — «модуль:атрибут» (замок подменяет их и ждёт другой вывод).
    gates: tuple[str, ...] = field(default=())


# --- проверки ----------------------------------------------------------------------------


def _website_hidden(t) -> list[Finding]:
    from apps.core import storefront_state
    from apps.tenants import onboarding

    reasons = storefront_state.hidden_reasons(t)
    out = []
    if "email_pending" in reasons:
        out.append(
            Finding(
                PROBLEM,
                _(
                    "Ihre E-Mail-Adresse ist noch nicht bestätigt — bis dahin sehen Kunden „Bald online“."
                ),
                "owner-confirm-resend",
                method="POST",
            )
        )
    if "unpublished" in reasons:
        out.append(
            Finding(
                PROBLEM,
                _("Die Website ist noch nicht veröffentlicht."),
                "setup",
                query="step=recht",
            )
        )
        for row in onboarding.publish_blockers(t, fresh=False):
            out.append(
                Finding(INFO, _("Es fehlt: %(item)s") % {"item": row["label"]}, row["url_name"])
            )
    return out or [Finding(OK, _("Ihre Website ist für Kunden sichtbar."))]


def _not_in_city(t) -> list[Finding]:
    from apps.aggregator import visibility
    from apps.aggregator.models import AggregatorListing

    if getattr(t, "is_demo", False):
        return [Finding(INFO, _("Demo-Geschäft — erscheint nicht im echten Stadtkatalog."))]
    reasons = visibility.withheld_reasons(t)
    texts = {
        "email_pending": (_("Erst nach Bestätigung Ihrer E-Mail-Adresse."), "owner-confirm-resend"),
        "unpublished": (_("Erst nach „Website veröffentlichen“."), "setup"),
        "operator_off": (_("Im Stadtkatalog vom Betreiber ausgeschaltet."), ""),
        "suspended": (_("Konto pausiert — bitte unter „Abo“ prüfen."), "billing"),
        "inactive": (_("Ihr Konto ist derzeit nicht aktiv."), ""),
        "internal": (_("Testkonto — erscheint nicht im Stadtkatalog."), ""),
    }
    out = []
    for code in reasons:
        text, url = texts.get(code, (_("Derzeit nicht sichtbar."), ""))
        out.append(
            Finding(
                PROBLEM,
                text,
                url,
                query="step=recht" if code == "unpublished" else "",
                owner_only=code in ("suspended", "inactive", "operator_off"),
                method="POST" if url == "owner-confirm-resend" else "GET",
            )
        )
    if out:
        return out
    with transaction.atomic():  # savepoint: сбой чтения public не ломает запрос кабинета
        listed = AggregatorListing.objects.public().filter(tenant_schema=t.schema_name).exists()
    if not listed:
        return [
            Finding(
                PROBLEM,
                _(
                    "Noch keine sichtbaren Einträge — aktive Aktionen und Angebote mit Foto und "
                    "Preis erscheinen im Stadtkatalog."
                ),
                "promotions:promotion-list",
            )
        ]
    return [Finding(OK, _("Ihr Geschäft ist im Stadtkatalog sichtbar."))]


def _module_finding(t, key: str, label) -> Finding | None:
    from apps.core import modules

    reason = modules.inactive_reason(t, key)
    if not reason:
        return None
    if reason == "unknown":
        return Finding(UNKNOWN, _("Konnte nicht geprüft werden — bitte später erneut versuchen."))
    if reason == "package":
        return Finding(PROBLEM, _("%(f)s ist in Ihrem Paket nicht enthalten.") % {"f": label})
    if reason == "tariff":
        return Finding(
            PROBLEM, _("%(f)s ist in Ihrem Tarif nicht enthalten.") % {"f": label}, owner_only=True
        )
    if reason.startswith("needs:"):
        return Finding(
            PROBLEM,
            _("%(f)s braucht eine weitere Funktion, die ausgeschaltet ist.") % {"f": label},
            "modules",
        )
    return Finding(PROBLEM, _("%(f)s ist ausgeschaltet.") % {"f": label}, "modules")


def _cart_closed(t) -> list[Finding]:
    from apps.core import closures, readiness, storefront_profile
    from apps.orders import payments

    out = []
    module = _module_finding(t, "orders", _("Online-Bestellung"))
    if module:
        return [module]
    if storefront_profile.is_aktionen(t):
        out.append(
            Finding(PROBLEM, _("Ihre Website zeigt nur Aktionen — der Warenkorb ist ausgeblendet."))
        )
    message = closures.closed_now_message(t)
    if message:
        out.append(Finding(PROBLEM, str(message), "betriebsferien"))
    if not payments.available_methods(t):
        out.append(
            Finding(
                PROBLEM, _("Keine Zahlungsart eingerichtet."), "payment-settings", owner_only=True
            )
        )
    product = readiness.is_done(t, "waren.product", unknown_on_error=True)
    if product is False:
        out.append(
            Finding(PROBLEM, _("Noch kein Produkt mit Preis angelegt."), "catalog:product-create")
        )
    elif product is None:
        out.append(Finding(UNKNOWN, _("Produkte konnten nicht geprüft werden.")))
    return out or [Finding(OK, _("Kunden können online bestellen."))]


def _promo_invisible(t) -> list[Finding]:
    from apps.promotions import limits, where
    from apps.promotions.models import Promotion

    promos = list(Promotion.objects.exclude(status="archived").order_by("-updated_at")[:MAX_PROMOS])
    if not promos:
        return [Finding(INFO, _("Noch keine Aktion angelegt."), "promotions:promotion-create")]
    out = []
    for promo in promos:
        name = promo.title_text() or "—"
        if promo.status != "active" and not limits.can_activate(promo, t):
            limit = limits.active_limit(t)
            out.append(Finding(PROBLEM, limits.limit_message(limit)))
            continue
        for row in where.rows(t, promo, portal_urls=False):
            if row["key"] in ("website", "stadtportal") and row["ok"] is False:
                out.append(
                    Finding(
                        PROBLEM,
                        _("„%(name)s“ — %(where)s: %(why)s")
                        % {"name": name, "where": row["label"], "why": row["detail"]},
                        "promotions:promotion-edit",
                        args=(promo.pk,),
                    )
                )
    return out or [Finding(OK, _("Ihre Aktionen sind sichtbar."))]


def _looks_closed(t) -> list[Finding]:
    from django.utils import formats, timezone

    from apps.core import closures

    today = timezone.localdate()
    # Строгое чтение: сбой ≠ «открыто» (closures по умолчанию молча считает «не закрыто»).
    closures.closed_days(today, today, t, strict=True)
    status = t.open_status()
    if status is None:
        return [
            Finding(
                INFO,
                _("Keine Öffnungszeiten hinterlegt — die Website zeigt keinen Status."),
                "settings",
            )
        ]
    if status.get("holiday"):
        until = status.get("holiday_until")
        return [
            Finding(
                PROBLEM,
                _("Betriebsferien bis %(day)s — die Website zeigt „geschlossen“.")
                % {"day": formats.date_format(until, "SHORT_DATE_FORMAT") if until else ""},
                "betriebsferien",
            )
        ]
    if not status.get("open"):
        return [
            Finding(
                INFO,
                _("Gerade geschlossen laut Öffnungszeiten — die Website zeigt das so an."),
                "settings",
            )
        ]
    return [Finding(OK, _("Laut Öffnungszeiten gerade geöffnet."))]


def _no_slots(t) -> list[Finding]:
    from apps.booking import availability
    from apps.booking.models import Service
    from apps.core import storefront_state

    if not storefront_state.booking_active(t):
        return [_module_finding(t, "booking", _("Online-Termine")) or Finding(UNKNOWN, "—")]
    services = list(Service.objects.filter(is_active=True).order_by("name")[:MAX_SERVICES])
    if not services:
        return [Finding(PROBLEM, _("Noch keine aktive Leistung."), "booking:services")]
    out = []
    for svc in services:
        if not availability.service_pool(svc):
            out.append(
                Finding(
                    PROBLEM,
                    _("„%(name)s“: niemand im Team bietet diese Leistung an.") % {"name": svc.name},
                    "booking:resources",
                )
            )
        elif availability.next_free_slot(svc, max_days=SLOT_DAYS) is None:
            out.append(
                Finding(
                    PROBLEM,
                    _(
                        "„%(name)s“: in den nächsten %(days)s Tagen keine freien Termine — "
                        "Öffnungszeiten der Mitarbeiter, Betriebsferien oder Buchungsfenster prüfen."
                    )
                    % {"name": svc.name, "days": SLOT_DAYS},
                    "booking:resources",
                )
            )
    return out or [Finding(OK, _("Für Ihre Leistungen gibt es freie Termine."))]


def _rooms_not_bookable(t) -> list[Finding]:
    from apps.core import readiness, storefront_state
    from apps.stays import availability

    if not storefront_state.stays_active(t):
        return [_module_finding(t, "stays", _("Zimmerbuchung")) or Finding(UNKNOWN, "—")]
    room = readiness.is_done(t, "zimmer.room", unknown_on_error=True)
    if room is False:
        return [
            Finding(
                PROBLEM,
                _("Kein Zimmer mit Preis, Gästezahl und Foto — Gäste können nicht online buchen."),
                "stays:units",
            )
        ]
    if room is None:
        return [Finding(UNKNOWN, _("Zimmer konnten nicht geprüft werden."))]
    if availability.next_free_range(1, guests=1, max_days=ROOM_DAYS) is None:
        return [
            Finding(
                PROBLEM,
                _("In den nächsten %(days)s Tagen keine freie Nacht — Belegung und Preise prüfen.")
                % {"days": ROOM_DAYS},
                "stays:units",
            )
        ]
    return [Finding(OK, _("Gäste können Zimmer online buchen."))]


def _google_feed(t) -> list[Finding]:
    from apps.catalog import google
    from apps.publishing import merchant
    from apps.publishing.models import Channel

    # НЕ merchant.channel(): тот делает get_or_create — GET помощника ничего не пишет.
    obj = Channel.objects.filter(type=Channel.GOOGLE_BUSINESS).first()
    if obj is None or not merchant.feed_state(obj)["enabled"]:
        return [Finding(INFO, _("Der Google-Produktfeed ist nicht eingeschaltet."), "gbp-merchant")]
    data = google.summary()
    excluded = sum(data["excluded"].values())
    if excluded:
        return [
            Finding(
                PROBLEM,
                _("%(n)s Produkte fehlen im Google-Feed (z. B. ohne Foto oder Preis).")
                % {"n": excluded},
                "gbp-merchant",
            )
        ]
    return [Finding(OK, _("Alle Produkte sind im Google-Feed."))]


# --- применимость -------------------------------------------------------------------------


def _always(t) -> bool:
    return True


def _direction(key):
    def check(t) -> bool:
        from apps.core import directions

        return directions.is_active(t, key)

    return check


def _promotions_on(t) -> bool:
    from apps.core import modules

    return modules.is_module_active(t, "promotions")


def _real_business(t) -> bool:
    from apps.core import readiness

    return not readiness.is_service_tenant(t) or getattr(t, "is_demo", False)


def _has_google_channel(t) -> bool:
    from apps.publishing.models import Channel

    return _direction("waren")(t) and Channel.objects.filter(type=Channel.GOOGLE_BUSINESS).exists()


REGISTRY: tuple[Diagnosis, ...] = (
    Diagnosis(
        "website_hidden",
        gettext_lazy("Kunden sehen „Bald online“"),
        CHEAP,
        _always,
        _website_hidden,
        ("apps.core.storefront_state:hidden_reasons",),
    ),
    Diagnosis(
        "not_in_city",
        gettext_lazy("Nicht im Stadtkatalog"),
        CHEAP,
        _real_business,
        _not_in_city,
        ("apps.aggregator.visibility:withheld_reasons",),
    ),
    Diagnosis(
        "cart_closed",
        gettext_lazy("Kunden können nicht online bestellen"),
        CHEAP,
        _direction("waren"),
        _cart_closed,
        (
            "apps.core.modules:inactive_reason",
            "apps.core.storefront_profile:is_aktionen",
            "apps.core.closures:closed_now_message",
            "apps.orders.payments:available_methods",
        ),
    ),
    Diagnosis(
        "promo_invisible",
        gettext_lazy("Meine Aktion ist nicht zu sehen"),
        CHEAP,
        _promotions_on,
        _promo_invisible,
        ("apps.promotions.where:rows",),
    ),
    Diagnosis(
        "looks_closed",
        gettext_lazy("Die Website zeigt „geschlossen“"),
        CHEAP,
        _always,
        _looks_closed,
        ("apps.tenants.models:Tenant.open_status",),
    ),
    Diagnosis(
        "no_slots",
        gettext_lazy("Keine freien Termine auf der Website"),
        HEAVY,
        _direction("termine"),
        _no_slots,
        ("apps.booking.availability:service_pool", "apps.booking.availability:next_free_slot"),
    ),
    Diagnosis(
        "rooms_not_bookable",
        gettext_lazy("Zimmer nicht buchbar"),
        HEAVY,
        _direction("zimmer"),
        _rooms_not_bookable,
        ("apps.stays.availability:next_free_range",),
    ),
    Diagnosis(
        "google_feed",
        gettext_lazy("Produkte fehlen bei Google"),
        HEAVY,
        _has_google_channel,
        _google_feed,
        ("apps.catalog.google:summary",),
    ),
)
BY_KEY = {d.key: d for d in REGISTRY}


def _safe(fn, t, default):
    try:
        return fn(t)
    except Exception:  # noqa: BLE001 — сбой проверки виден как «unknown», кабинет не падает
        logger.warning("assistant: check %s failed", getattr(fn, "__name__", fn), exc_info=True)
        return default


_APPLIES_FAILED = object()


def applicable_status(tenant) -> list[tuple[Diagnosis, bool]]:
    """[(диагноз, понятно_ли_применим)]: сбой `applies` не прячет карточку молча —
    она остаётся с пометкой «nicht geprüft» (не знаю ≠ «не относится»)."""
    out = []
    for d in REGISTRY:
        got = _safe(d.applies, tenant, _APPLIES_FAILED)
        if got is _APPLIES_FAILED:
            out.append((d, False))
        elif got:
            out.append((d, True))
    return out


def applicable(tenant) -> list[Diagnosis]:
    return [d for d, known in applicable_status(tenant) if known]


def run(tenant, key: str) -> list[Finding]:
    """Прогнать один диагноз. Сбой — одна находка «unknown», не «всё хорошо»."""
    diagnosis = BY_KEY[key]
    unknown = [Finding(UNKNOWN, _("Konnte nicht geprüft werden — bitte später erneut versuchen."))]
    return _safe(diagnosis.run, tenant, unknown)
