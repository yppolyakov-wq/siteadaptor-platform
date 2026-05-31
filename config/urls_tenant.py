"""URL routes для TENANT schema ({slug}.siteadaptor.de и custom-домены).

Эти урлы видны на субдоменах конкретного бизнеса. Django admin сюда НЕ
включён — он только на public (см. urls_public). Дашборд владельца — это
отдельный HTMX-UI (Sprint 2), а не Django admin.
"""

from django.conf import settings
from django.urls import include, path
from django.views.static import serve

from apps.core import health
from apps.core.views import dashboard
from apps.promotions import public_views

urlpatterns = [
    path("accounts/", include("allauth.urls")),
    path("health/", health.liveness, name="health"),
    path("health/ready/", health.readiness, name="health-ready"),
    # --- Кабинет владельца (под логином) ---
    path("dashboard/", dashboard, name="dashboard"),
    # Каталог в кабинете владельца.
    path("catalog/", include("apps.catalog.urls")),
    # CSV-импорт товаров.
    path("imports/", include("apps.imports.urls")),
    # Акции и брони в кабинете владельца.
    path("promotions/", include("apps.promotions.urls")),
    # --- Публичная витрина (без логина), на корне субдомена ---
    path("", public_views.storefront_home, name="storefront-home"),
    path("p/<uuid:pk>/", public_views.promotion_detail, name="storefront-promotion"),
    path("p/<uuid:pk>/reserve/", public_views.reservation_create, name="storefront-reserve"),
    path("r/<str:code>/", public_views.reservation_confirmation, name="storefront-confirmation"),
]

# Раздача загруженных медиа Django, когда нет S3 (single-сервер).
if getattr(settings, "SERVE_MEDIA", False):
    urlpatterns += [
        path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
