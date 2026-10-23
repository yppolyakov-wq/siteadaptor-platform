"""T-8.31a: «Start» лёгкого кабинета (план docs/t8-31-mein-laden-plan-2026-10-20.md §2).

Главная «Mein Laden» по утверждённому макету: имя и дата, «＋ Neue Aktion», карточка
акций (счётчики + ближайшая по окончанию + где видна), плитки «Mein Angebot» и
«Sichtbarkeit», «Nächster Schritt». Только чтение; ссылки — на существующие экраны.
Заголовок живёт в теле страницы (не в шапке кабинета) — для Mini App (T-8.30).
"""

from __future__ import annotations

from django.db.models import Count, F, Q
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def promo_counts() -> dict:
    from apps.promotions.models import Promotion

    return Promotion.objects.aggregate(
        active=Count("pk", filter=Q(status="active")),
        scheduled=Count("pk", filter=Q(status="scheduled")),
    )


def featured_promo():
    """Активная акция, которая кончается раньше всех (без конца — в хвосте), потом по
    просмотрам; со счётчиком «zurückgelegt» тем же условием, что список акций."""
    from apps.promotions.models import Promotion

    return (
        Promotion.objects.filter(status="active")
        .select_related("product")
        .annotate(
            n_held=Count(
                "reservations",
                filter=Q(reservations__status__in=["pending", "confirmed", "fulfilled"]),
            )
        )
        .order_by(F("ends_at").asc(nulls_last=True), "-views", "-created_at")
        .first()
    )


def product_counts() -> dict:
    from apps.catalog.models import Product

    return Product.objects.filter(is_active=True).aggregate(
        total=Count("pk"), no_photo=Count("pk", filter=Q(images=[]))
    )


CHIP_KEYS = ("website", "stadtportal", "telegram")


def visibility_chips(tenant, promo) -> list[dict]:
    """Где акция видна сейчас — по фактам (те же строки, что «Wo erscheint die Aktion?»)."""
    import logging

    from apps.promotions import where

    try:
        rows = where.rows(tenant, promo, portal_urls=False)
    except Exception:  # noqa: BLE001 — главная лёгкого кабинета не падает из-за статуса
        logging.getLogger(__name__).warning("lite_home: visibility chips failed", exc_info=True)
        return []
    return [r for r in rows if r["key"] in CHIP_KEYS]


# Реестр «следующего шага»: первое сработавшее правило. Цели — только существующие
# экраны лёгкого кабинета (замок проверяет, что каждая резолвится).
NEXT_STEPS = (
    {
        "key": "first_promo",
        "url": "promotions:promotion-quick",
        "text": _("Starten Sie Ihre erste Aktion — Foto, Preis, fertig."),
        "cta": _("Aktion anlegen"),
    },
    {
        # KA-12 E7.2: Impressum — предупреждение (не блок), сразу после первой акции.
        "key": "impressum",
        "url": "lite-business",
        "anchor": "#sec-recht",
        "text": _("Ihr Impressum ist noch unvollständig — ergänzen Sie die Pflichtangaben."),
        "cta": _("Impressum ergänzen"),
    },
    {
        "key": "photos",
        "url": "sellable-manage",
        "text": _("Einige Produkte haben noch kein Foto. Mit Foto werden sie öfter angesehen."),
        "cta": _("Fotos ergänzen"),
    },
    {
        "key": "telegram",
        "url": "notifications-settings",
        "text": _("Neue Reservierungen sofort in Telegram erfahren."),
        "cta": _("Telegram verbinden"),
    },
    {
        "key": "share",
        "url": "lite-share",
        "text": _("Teilen Sie Ihre Seite — per QR-Code im Laden oder in WhatsApp."),
        "cta": _("Teilen"),
    },
)


def _step_url(rule) -> str:
    return reverse(rule["url"]) + rule.get("anchor", "")


def _owner_in_telegram(tenant) -> bool:
    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    node = cfg.get("notify") if isinstance(cfg.get("notify"), dict) else {}
    return bool(node.get("owner_chat_id"))


def _impressum_missing(tenant) -> list[str]:
    from apps.core.lite_cabinet import impressum_missing

    return impressum_missing(tenant)


def next_step(tenant, counts, products) -> dict:
    checks = {
        "first_promo": lambda: not counts.get("active") and not counts.get("scheduled"),
        "impressum": lambda: bool(_impressum_missing(tenant)),
        "photos": lambda: bool(products and products.get("no_photo")),
        "telegram": lambda: not _owner_in_telegram(tenant),
        "share": lambda: True,
    }
    for rule in NEXT_STEPS:
        if checks[rule["key"]]():
            return {**rule, "url": _step_url(rule)}
    return {}


def open_reservations() -> int:
    from apps.promotions.models import Reservation
    from apps.promotions.views import open_reservation_statuses

    return Reservation.objects.filter(status__in=open_reservation_statuses()).count()


def render_home(request):
    tenant = request.tenant
    counts = promo_counts()
    featured = featured_promo()
    products = product_counts()
    return render(
        request,
        "tenant/lite_home.html",
        {
            "nav": "dashboard",
            "today": timezone.localdate(),
            "counts": counts,
            "featured": featured,
            "chips": visibility_chips(tenant, featured) if featured else [],
            "products": products,
            "step": next_step(tenant, counts, products),
            # T-8.30e: касса — ждут продавца (pending+confirmed), как на экране акций.
            "open_reservations": open_reservations(),
        },
    )
