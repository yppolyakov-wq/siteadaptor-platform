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

urlpatterns = [
    path("accounts/", include("allauth.urls")),
    path("health/", health.liveness, name="health"),
    path("health/ready/", health.readiness, name="health-ready"),
    # Каталог в кабинете владельца.
    path("catalog/", include("apps.catalog.urls")),
    # Кабинет владельца на субдомене бизнеса.
    path("", dashboard, name="dashboard"),
]

# Раздача загруженных медиа Django, когда нет S3 (single-сервер).
if getattr(settings, "SERVE_MEDIA", False):
    urlpatterns += [
        path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
