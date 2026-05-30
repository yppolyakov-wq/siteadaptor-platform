"""URL routes для SHARED schema (агрегатор, public-сайт, admin).

Эти урлы доступны на основном домене siteadaptor.de.
Django admin живёт ТОЛЬКО здесь (платформенный суперадмин), не на субдоменах.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.static import serve

from apps.core import health
from apps.tenants.views import BusinessSignupView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("health/", health.liveness, name="health"),
    path("health/ready/", health.readiness, name="health-ready"),
    # Phase 2: авторизация custom-доменов для Caddy on-demand TLS.
    path("internal/verify-domain", health.verify_domain, name="verify-domain"),
    # Онбординг: регистрация бизнеса → создаёт Tenant + Domain + владельца.
    path("", BusinessSignupView.as_view(), name="business-signup"),
]

# Раздача загруженных медиа Django, когда нет S3 (single-сервер).
if getattr(settings, "SERVE_MEDIA", False):
    urlpatterns += [
        path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
