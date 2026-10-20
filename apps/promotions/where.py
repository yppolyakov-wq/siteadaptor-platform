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


def _catalog_line(tenant, promo) -> str:
    from apps.aggregator import follow, portal_scope
    from apps.aggregator.models import AggregatorListing, AggregatorPortal

    if promo.status != "active":
        return _("Stadtkatalog: erst sichtbar, wenn die Aktion aktiv ist.")
    reason = _catalog_reason(tenant)
    if reason:
        return _("Stadtkatalog: %(reason)s") % {"reason": reason}
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
            return _("Stadtkatalog: nach Meldungen ausgeblendet, wird geprüft.")
        return _("Stadtkatalog: wird gerade aufgenommen (wenige Minuten).")
    urls = []
    for portal in AggregatorPortal.objects.filter(is_active=True).order_by("pk").iterator():
        if portal_scope.contains(listing, portal):  # у тематического портала — запрос
            urls.append(follow.absolute(portal, "aggregator-offer", args=[listing.pk]))
            if len(urls) >= PORTAL_LIMIT:
                break
    if not urls:
        urls = [follow.absolute(None, "aggregator-offer", args=[listing.pk])]
    return _("Stadtkatalog: %(url)s") % {"url": " · ".join(urls)}


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
