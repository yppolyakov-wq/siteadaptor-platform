"""T-8.10h H-7d: «Wo ist meine Aktion?» — где акция видна прямо сейчас, словами.

План — docs/t8-10h-h7-owner-bot-ux-plan-2026-10-20.md §2. Только чтение: своя страница,
флаер, каталог города (ссылка или ПРИЧИНА, почему нет) и каналы публикации со статусом.
Вызывается в схеме бизнеса (акция и публикации — tenant-таблицы; листинг — public).
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import gettext as _

TENANT_URLCONF = "config.urls_tenant"
PORTAL_LIMIT = 3


def _catalog_reason(tenant) -> str:
    """Почему бизнеса нет в каталоге города ('' — может быть)."""
    from apps.aggregator import visibility

    if getattr(tenant, "is_demo", False):
        return _("Demo-Geschäft — nicht im echten Stadtkatalog.")
    if getattr(tenant, "email_pending", False):
        return _("Erst nach Bestätigung Ihrer E-Mail-Adresse (Link in der E-Mail).")
    if not getattr(tenant, "in_city_catalog", True):
        return _("Im Stadtkatalog ausgeschaltet (Einstellungen → Mein Geschäft).")
    if getattr(tenant, "subscription_status", "") == visibility.SUSPENDED:
        return _("Konto pausiert — bitte im Kabinett unter „Abo“ prüfen.")
    if not visibility.listable(tenant):
        return _("Derzeit nicht sichtbar.")
    return ""


def _catalog_state(tenant, promo, *, with_urls=True) -> dict:
    """Состояние в каталоге города: ``ok`` (видна) + ``detail`` (причина, если нет) +
    ``urls`` (адреса на порталах). Одна точка для отчёта в чат и для кабинета."""
    from apps.aggregator import follow, portal_scope
    from apps.aggregator.models import AggregatorListing, AggregatorPortal

    if promo.status != "active":
        return {"ok": False, "detail": _("erst sichtbar, wenn die Aktion aktiv ist."), "urls": []}
    reason = _catalog_reason(tenant)
    if reason:
        return {"ok": False, "detail": reason, "urls": []}
    key = {
        "tenant_schema": tenant.schema_name,
        "listing_kind": AggregatorListing.KIND_PROMOTION,
        "source_ref": str(promo.pk),
    }
    # Ссылка — только на то, что портал реально покажет (та же точка чтения, что у него).
    listing = AggregatorListing.objects.public().filter(**key).first()
    if listing is None:
        raw = AggregatorListing.objects.filter(**key).first()
        if raw is not None and raw.hidden_at is not None:
            return {
                "ok": False,
                "detail": _("nach Meldungen ausgeblendet, wird geprüft."),
                "urls": [],
            }
        return {"ok": False, "detail": _("wird gerade aufgenommen (wenige Minuten)."), "urls": []}
    if not with_urls:  # «Start»: нужен только факт — без обхода всех порталов
        return {"ok": True, "detail": "", "urls": []}
    urls = []
    for portal in AggregatorPortal.objects.filter(is_active=True).order_by("pk").iterator():
        if portal_scope.contains(listing, portal):  # у тематического портала — запрос
            urls.append(follow.absolute(portal, "aggregator-offer", args=[listing.pk]))
            if len(urls) >= PORTAL_LIMIT:
                break
    if not urls:
        urls = [follow.absolute(None, "aggregator-offer", args=[listing.pk])]
    return {"ok": True, "detail": "", "urls": urls}


def _catalog_line(tenant, promo) -> str:
    state = _catalog_state(tenant, promo)
    if state["ok"]:
        return _("Stadtkatalog: %(url)s") % {"url": " · ".join(state["urls"])}
    return _("Stadtkatalog: %(reason)s") % {"reason": state["detail"]}


def _status_word(status: str) -> str:
    words = {
        "queued": _("in Warteschlange"),
        "published": _("veröffentlicht"),
        "failed": _("Fehler"),
        "removed": _("entfernt"),
    }
    return words.get(status, status)


def _channels_line(promo) -> str:
    from apps.publishing.models import Publication

    pubs = list(
        Publication.objects.filter(promotion=promo).select_related("channel").order_by("pk")
    )
    if not pubs:
        return ""
    parts = [f"{pub.channel.get_type_display()} — {_status_word(pub.status)}" for pub in pubs[:8]]
    return _("Kanäle: %(list)s") % {"list": "; ".join(parts)}


def report(tenant, promo) -> list[str]:
    """Строки отчёта для чата (без HTML: Telegram получает обычный текст)."""
    from apps.core import owner_login

    base = owner_login.tenant_url(tenant)
    lines = [
        "🔗 "
        + _("Eigene Seite: %(url)s")
        % {"url": base + reverse("storefront-promotion", args=[promo.pk], urlconf=TENANT_URLCONF)},
        "📄 "
        + _("Aushang (PDF, nach Anmeldung): %(url)s")
        % {
            "url": base
            + reverse("promotions:promotion-flyer", args=[promo.pk], urlconf=TENANT_URLCONF)
        },
        "🏙 " + _catalog_line(tenant, promo),
    ]
    channels = _channels_line(promo)
    if channels:
        lines.append("📣 " + channels)
    return lines


def _telegram_channel_on() -> bool:
    from apps.publishing.models import Channel

    return Channel.objects.filter(type=Channel.TELEGRAM, is_enabled=True).exists()


def rows(tenant, promo, *, portal_urls=True) -> list[dict]:
    """T-8.31b: «Wo erscheint die Aktion?» для кабинета — ``{key, label, ok, detail, url}``.
    ``ok``: True — видна, False — нет (``detail`` — почему), None — не про видимость."""
    from apps.core import owner_login

    base = owner_login.tenant_url(tenant)
    catalog = _catalog_state(tenant, promo, with_urls=portal_urls)
    page = reverse("storefront-promotion", args=[promo.pk], urlconf=TENANT_URLCONF)
    return [
        {
            "key": "website",
            "label": _("Meine Website"),
            "ok": promo.status == "active",
            "detail": ""
            if promo.status == "active"
            else _("erst sichtbar, wenn die Aktion aktiv ist."),
            "url": base + page,
        },
        {
            "key": "stadtportal",
            "label": _("Stadtportal"),
            "ok": catalog["ok"],
            "detail": catalog["detail"],
            "url": catalog["urls"][0] if catalog["urls"] else "",
        },
        {
            "key": "telegram",
            "label": _("Telegram-Kanal"),
            "ok": _telegram_channel_on(),
            "detail": "",
            "url": "",
        },
        {
            "key": "flyer",
            "label": _("Aushang (QR)"),
            "ok": None,
            "detail": "",
            "url": reverse("promotions:promotion-flyer", args=[promo.pk], urlconf=TENANT_URLCONF),
        },
    ]
