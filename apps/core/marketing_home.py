"""ST-6a: Marketing-центр — данные лендинга /dashboard/marketing/.

Карточки-входы в ROI-порядке ТЗ (напоминания → лояльность → отзывы →
«во все каналы» → кампании) + read-only обзор напоминаний (поверх
prefs.customer_matrix + win-back-кампании UD4-2/B4) + панель результатов из
готовых источников (views активных акций, ★-показы/клики агрегатора по
tenant_schema, погашения кампаний, отзывы). Новых моделей/ключей НЕТ; каждый
блок отказоустойчив (_safe — модуль/таблица может быть недоступна).
"""

from django.urls import reverse
from django.utils.translation import gettext as _


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def cards(tenant):
    """Карточки-входы в ROI-порядке ТЗ; показываются только доступные по модулям."""
    items = [
        {
            "icon": "⏰",
            "label": _("Erinnerungen & Care-Zyklus"),
            "hint": _("Zahlungs-/Termin-Erinnerungen, «Wie war's?»-Mails"),
            "url_name": "notifications-settings",
            "show": True,
        },
        {
            "icon": "🎟️",
            "label": _("Treue & Gutscheine"),
            "hint": _("Gutscheine, Treuepunkte, Geschenkgutscheine"),
            "url_name": "promotions:voucher-list",
            "show": tenant.is_module_active("loyalty"),
        },
        {
            "icon": "⭐",
            "label": _("Bewertungen"),
            "hint": _("Antworten, verwalten, um Bewertungen bitten"),
            "url_name": "reviews:list",
            "show": tenant.is_module_active("reviews"),
        },
        {
            "icon": "📣",
            "label": _("Aktion überall teilen"),
            "hint": _("Kanäle, ★ Anzeige und E-Mail — von der Aktion aus"),
            "url_name": "promotions:promotion-list",
            "show": tenant.is_module_active("promotions"),
        },
        {
            "icon": "✉️",
            "label": _("Kampagnen"),
            "hint": _("Coupon-Kampagnen nach Kundensegmenten"),
            "url_name": "promotions:coupon-campaigns",
            "show": tenant.is_module_active("crm"),
        },
        {
            "icon": "📡",
            "label": _("Kanäle & Beiträge"),
            "hint": _("Google/Facebook/Instagram/Telegram verbinden"),
            "url_name": "channels",
            "show": tenant.is_module_active("publishing"),
        },
    ]
    return [c for c in items if c["show"]]


# События матрицы UD4-2, являющиеся «напоминаниями»/автокасаниями (ROI №1).
_REMINDER_EVENTS = {
    "payment_reminder",
    "reminder",
    "service_reminder",
    "post_purchase",
    "post_visit",
    "post_stay",
    "post_event",
}


def reminder_overview(tenant):
    """Read-only свод «какие авто-касания активны»: строки reminder-событий из
    матрицы UD4-2 (per-домен гейт модулей уже внутри customer_matrix) + строка
    Win-back (B4-кампания kind=auto_winback). Настройка — по ссылкам."""
    from apps.notifications import prefs

    rows = []
    for group in _safe(lambda: prefs.customer_matrix(tenant), []):
        for row in group["rows"]:
            if row["event"] not in _REMINDER_EVENTS:
                continue
            rows.append(
                {
                    "label": f"{group['label']}: {row['label']}",
                    "email": row["email"],
                    "telegram": row["telegram"],
                    "url": reverse("notifications-settings"),
                }
            )

    def _winback():
        from apps.promotions.models import CouponCampaign

        camp = (
            CouponCampaign.objects.filter(kind=CouponCampaign.KIND_AUTO_WINBACK)
            .order_by("-created_at")
            .first()
        )
        if camp is None:
            return None
        return {
            "label": _("Win-back (inaktive Kunden)"),
            "active": camp.status == CouponCampaign.STATUS_ACTIVE,
            "url": reverse("promotions:coupon-campaigns"),
        }

    return {"rows": rows, "winback": _safe(_winback, None)}


def results_panel(tenant):
    """Сводная панель результатов — 4 готовых источника, только чтение."""
    metrics = []

    def _views():
        from django.db.models import Sum

        from apps.promotions.models import Promotion

        n = Promotion.objects.filter(status="active").aggregate(s=Sum("views"))["s"]
        return {
            "label": _("Aufrufe aktiver Aktionen"),
            "value": n or 0,
            "url": reverse("promotions:analytics"),
        }

    def _featured():
        from django.db import connection
        from django.db.models import Sum

        from apps.aggregator.models import AggregatorListing

        agg = AggregatorListing.objects.filter(tenant_schema=connection.schema_name).aggregate(
            imp=Sum("featured_impressions"), clk=Sum("featured_clicks")
        )
        if not (agg["imp"] or agg["clk"]):
            return None
        return {
            "label": _("★ Anzeige: Aufrufe · Klicks"),
            "value": f"{agg['imp'] or 0} · {agg['clk'] or 0}",
            "url": reverse("promotions:promotion-list"),
        }

    def _campaigns():
        from django.db.models import Count, Sum

        from apps.promotions.models import CouponCampaign

        agg = CouponCampaign.objects.aggregate(
            issued=Count("vouchers"), redeemed=Sum("vouchers__used_count")
        )
        if not agg["issued"]:
            return None
        return {
            "label": _("Kampagnen: ausgegeben · eingelöst"),
            "value": f"{agg['issued']} · {agg['redeemed'] or 0}",
            "url": reverse("promotions:coupon-campaigns"),
        }

    def _reviews():
        from apps.reviews import services as review_services

        overview = review_services.owner_overview()
        if not overview.get("count"):
            return None
        avg = overview.get("avg") or 0
        return {
            "label": _("Bewertungen: ⌀ · Anzahl"),
            "value": f"{avg:.1f} · {overview['count']}",
            "url": reverse("reviews:list"),
        }

    if tenant.is_module_active("promotions"):
        metrics.append(_safe(_views, None))
        metrics.append(_safe(_featured, None))
    if tenant.is_module_active("crm"):
        metrics.append(_safe(_campaigns, None))
    if tenant.is_module_active("reviews"):
        metrics.append(_safe(_reviews, None))
    return [m for m in metrics if m]
