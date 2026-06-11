"""URL routes портальных хостов (P2.1b).

Подставляется в request.urlconf middleware-резолвером
(apps.aggregator.middleware.AggregatorPortalMiddleware), когда host сопоставлен
с активным AggregatorPortal. Корень — листинги фильтра портала, /<facet>/ —
уточнение по свободной оси (см. apps.aggregator.portal_views).
"""

from django.conf import settings
from django.urls import path
from django.views.static import serve

from apps.aggregator import account_views, portal_views
from apps.core import health

urlpatterns = [
    path("", portal_views.portal_home, name="portal-home"),
    # Health-пробы должны отвечать и на хосте портала (мониторинг/Caddy).
    # Стоят до <facet>, иначе сегмент ушёл бы в уточнение и дал 404.
    path("health/", health.liveness, name="health"),
    path("health/ready/", health.readiness, name="health-ready"),
    # SEO портала (P2.1c): sitemap/robots по хосту портала.
    path("sitemap.xml", portal_views.portal_sitemap_xml, name="portal-sitemap"),
    path("robots.txt", portal_views.portal_robots_txt, name="portal-robots"),
    # Клиентский аккаунт (P2.3a): magic-link вход. Тоже до <facet>.
    path("konto/", account_views.account, name="portal-account"),
    path("konto/login/", account_views.login_view, name="portal-login"),
    path("konto/login/verify/", account_views.login_verify, name="portal-login-verify"),
    path("konto/logout/", account_views.logout_view, name="portal-logout"),
    path("<str:facet>/", portal_views.portal_home, name="portal-facet"),
]

# Картинки листингов — относительные /media/... (single-сервер без S3),
# поэтому портальному хосту нужен тот же фолбэк, что и urls_public.
if getattr(settings, "SERVE_MEDIA", False):
    urlpatterns = [
        path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
    ] + urlpatterns
