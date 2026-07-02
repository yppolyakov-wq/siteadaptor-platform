"""URL routes для SHARED schema (агрегатор, public-сайт, admin).

Эти урлы доступны на основном домене siteadaptor.de.
Django admin живёт ТОЛЬКО здесь (платформенный суперадмин), не на субдоменах.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.static import serve

from apps.aggregator import reviews_views as aggregator_reviews_views
from apps.aggregator import views as aggregator_views
from apps.billing.webhooks import stripe_webhook
from apps.core import health
from apps.publishing import views as publishing_views
from apps.tenants.views import BusinessSignupView, signup_waiting

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("health/", health.liveness, name="health"),
    path("health/ready/", health.readiness, name="health-ready"),
    # Stripe-вебхук (один URL на всю платформу, public-схема).
    path("stripe/webhook/", stripe_webhook, name="stripe-webhook"),
    # In-app OAuth каналов (OAuth-A): единый callback на основном домене.
    path(
        "oauth/<str:provider>/callback/",
        publishing_views.oauth_callback,
        name="channel-oauth-callback",
    ),
    # Phase 2: авторизация custom-доменов для Caddy on-demand TLS.
    path("internal/verify-domain", health.verify_domain, name="verify-domain"),
    # Локальный агрегатор (Sprint 4): городские страницы на основном домене.
    path("entdecken/", aggregator_views.discover_index, name="aggregator-index"),
    path("entdecken/<str:city>/", aggregator_views.city_listing, name="aggregator-city"),
    path(
        "entdecken/<str:city>/<str:business_type>/",
        aggregator_views.city_listing,
        name="aggregator-city-type",
    ),
    # A8/E-2: страница бизнеса (отзывы read-only) и на главном домене — тот же
    # name, что на портальных хостах, чтобы {% url 'portal-business' %} работал везде.
    path(
        "entdecken/unternehmen/<slug:slug>/",
        aggregator_reviews_views.business_page,
        name="portal-business",
    ),
    # Local SEO (Track B5): sitemap + robots основного домена.
    path("sitemap.xml", aggregator_views.sitemap_xml, name="aggregator-sitemap"),
    path("robots.txt", aggregator_views.robots_txt, name="aggregator-robots"),
    # Онбординг: регистрация бизнеса → создаёт Tenant + Domain + владельца.
    path("", BusinessSignupView.as_view(), name="business-signup"),
    # Ожидание фонового провижининга: «Ihre Website wird eingerichtet…».
    path("anmeldung/<slug:slug>/", signup_waiting, name="signup-waiting"),
]

# Раздача загруженных медиа Django, когда нет S3 (single-сервер).
if getattr(settings, "SERVE_MEDIA", False):
    urlpatterns += [
        path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
