"""URL routes портальных хостов (P2.1b).

Подставляется в request.urlconf middleware-резолвером
(apps.aggregator.middleware.AggregatorPortalMiddleware), когда host сопоставлен
с активным AggregatorPortal. Корень — листинги фильтра портала, /<facet>/ —
уточнение по свободной оси (см. apps.aggregator.portal_views).
"""

from django.conf import settings
from django.urls import path
from django.views.static import serve

from apps.aggregator import portal_views

urlpatterns = [
    path("", portal_views.portal_home, name="portal-home"),
    path("<str:facet>/", portal_views.portal_home, name="portal-facet"),
]

# Картинки листингов — относительные /media/... (single-сервер без S3),
# поэтому портальному хосту нужен тот же фолбэк, что и urls_public.
if getattr(settings, "SERVE_MEDIA", False):
    urlpatterns = [
        path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
    ] + urlpatterns
