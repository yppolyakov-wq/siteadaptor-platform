"""URL routes для TENANT schema ({slug}.siteadaptor.de и custom-домены).

Эти урлы видны на субдоменах конкретного бизнеса. Django admin сюда НЕ
включён — он только на public (см. urls_public). Дашборд владельца — это
отдельный HTMX-UI (Sprint 2), а не Django admin.
"""

from django.conf import settings
from django.urls import include, path
from django.views.static import serve

from apps.core import health
from apps.core.views import dashboard, settings_view
from apps.promotions import public_views

urlpatterns = [
    path("accounts/", include("allauth.urls")),
    path("health/", health.liveness, name="health"),
    path("health/ready/", health.readiness, name="health-ready"),
    # --- Кабинет владельца (под логином) ---
    path("dashboard/", dashboard, name="dashboard"),
    path("dashboard/settings/", settings_view, name="settings"),
    # Каталог в кабинете владельца.
    path("catalog/", include("apps.catalog.urls")),
    # CSV-импорт товаров.
    path("imports/", include("apps.imports.urls")),
    # Акции и брони в кабинете владельца.
    path("promotions/", include("apps.promotions.urls")),
    # --- Публичная витрина (без логина), на корне субдомена ---
    path("", public_views.storefront_home, name="storefront-home"),
    path("lang/", public_views.set_language, name="storefront-set-language"),
    path("p/<uuid:pk>/", public_views.promotion_detail, name="storefront-promotion"),
    path("p/<uuid:pk>/reserve/", public_views.reservation_create, name="storefront-reserve"),
    path("p/<uuid:pk>/waitlist/", public_views.waitlist_join, name="storefront-waitlist"),
    path("p/<uuid:pk>/qr.svg", public_views.promotion_qr, name="storefront-promotion-qr"),
    path("r/<str:code>/", public_views.reservation_confirmation, name="storefront-confirmation"),
    path("r/<str:code>/qr.svg", public_views.reservation_qr, name="storefront-reservation-qr"),
    path("v/<str:code>/qr.svg", public_views.voucher_qr, name="storefront-voucher-qr"),
    path("impressum/", public_views.impressum, name="storefront-impressum"),
    path("datenschutz/", public_views.privacy, name="storefront-privacy"),
    path("widerruf/", public_views.withdrawal, name="storefront-withdrawal"),
    path("u/<uuid:token>/", public_views.unsubscribe, name="storefront-unsubscribe"),
]

# Раздача загруженных медиа Django, когда нет S3 (single-сервер).
if getattr(settings, "SERVE_MEDIA", False):
    urlpatterns += [
        path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
