"""URL routes для SHARED schema (агрегатор, public-сайт, admin).

Эти урлы доступны на основном домене siteadaptor.de.
Django admin живёт ТОЛЬКО здесь (платформенный суперадмин), не на субдоменах.
"""

from django.contrib import admin
from django.urls import include, path

from apps.core import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("health/", health.liveness, name="health"),
    path("health/ready/", health.readiness, name="health-ready"),
    # Phase 2: авторизация custom-доменов для Caddy on-demand TLS.
    path("internal/verify-domain", health.verify_domain, name="verify-domain"),
]
