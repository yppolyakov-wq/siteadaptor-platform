"""URL routes для TENANT schema ({slug}.siteadaptor.de и custom-домены).

Эти урлы видны на субдоменах конкретного бизнеса. Django admin сюда НЕ
включён — он только на public (см. urls_public). Дашборд владельца — это
отдельный HTMX-UI (Sprint 2), а не Django admin.
"""

from django.conf import settings
from django.urls import include, path
from django.views.static import serve

from apps.billing import views as billing_views
from apps.core import health
from apps.core.views import (
    dashboard,
    domain_add,
    domain_remove,
    domain_verify,
    domains_view,
    settings_view,
)
from apps.promotions import public_views
from apps.publishing import views as publishing_views

urlpatterns = [
    path("accounts/", include("allauth.urls")),
    path("health/", health.liveness, name="health"),
    path("health/ready/", health.readiness, name="health-ready"),
    # --- Кабинет владельца (под логином) ---
    path("dashboard/", dashboard, name="dashboard"),
    path("dashboard/settings/", settings_view, name="settings"),
    # Self-service custom-домены бизнеса (P2): заявка + DNS-подтверждение.
    path("dashboard/domains/", domains_view, name="domains"),
    path("dashboard/domains/add/", domain_add, name="domain-add"),
    path("dashboard/domains/<int:pk>/verify/", domain_verify, name="domain-verify"),
    path("dashboard/domains/<int:pk>/remove/", domain_remove, name="domain-remove"),
    # Биллинг/подписка (Sprint 5).
    path("dashboard/billing/", billing_views.billing, name="billing"),
    path("dashboard/billing/checkout/", billing_views.checkout, name="billing-checkout"),
    path("dashboard/billing/portal/", billing_views.portal, name="billing-portal"),
    # Каналы публикации (Sprint 4).
    path("dashboard/channels/", publishing_views.channels, name="channels"),
    path("dashboard/channels/toggle/", publishing_views.channel_toggle, name="channel-toggle"),
    path("dashboard/channels/config/", publishing_views.channel_config, name="channel-config"),
    # Каталог в кабинете владельца.
    path("catalog/", include("apps.catalog.urls")),
    # CSV-импорт товаров.
    path("imports/", include("apps.imports.urls")),
    # Акции и брони в кабинете владельца.
    path("promotions/", include("apps.promotions.urls")),
    # --- Публичная витрина (без логина), на корне субдомена ---
    path("", public_views.storefront_home, name="storefront-home"),
    path("lang/", public_views.set_language, name="storefront-set-language"),
    # Каталог товаров на витрине (Track C1).
    path("sortiment/", public_views.product_list, name="storefront-products"),
    path("sortiment/<uuid:pk>/", public_views.product_detail, name="storefront-product"),
    path("p/<uuid:pk>/", public_views.promotion_detail, name="storefront-promotion"),
    path("p/<uuid:pk>/reserve/", public_views.reservation_create, name="storefront-reserve"),
    path("p/<uuid:pk>/waitlist/", public_views.waitlist_join, name="storefront-waitlist"),
    path("p/<uuid:pk>/qr.svg", public_views.promotion_qr, name="storefront-promotion-qr"),
    path("r/<str:code>/", public_views.reservation_confirmation, name="storefront-confirmation"),
    path("r/<str:code>/qr.svg", public_views.reservation_qr, name="storefront-reservation-qr"),
    path("v/<str:code>/qr.svg", public_views.voucher_qr, name="storefront-voucher-qr"),
    path("c/<uuid:token>/qr.svg", public_views.loyalty_card_qr, name="storefront-loyalty-qr"),
    path("impressum/", public_views.impressum, name="storefront-impressum"),
    path("datenschutz/", public_views.privacy, name="storefront-privacy"),
    path("widerruf/", public_views.withdrawal, name="storefront-withdrawal"),
    path("u/<uuid:token>/", public_views.unsubscribe, name="storefront-unsubscribe"),
    # Local SEO (Track B5): sitemap + robots на корне витрины.
    path("sitemap.xml", public_views.sitemap_xml, name="storefront-sitemap"),
    path("robots.txt", public_views.robots_txt, name="storefront-robots"),
]

# Раздача загруженных медиа Django, когда нет S3 (single-сервер).
if getattr(settings, "SERVE_MEDIA", False):
    urlpatterns += [
        path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
