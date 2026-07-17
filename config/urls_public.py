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
from apps.partners import views as partners_views
from apps.publishing import views as publishing_views
from apps.tenants.views import (
    BusinessSignupView,
    about_page,
    industries_index,
    industry_page,
    platform_legal,
    set_public_language,
    signup_confirm,
    signup_resend,
    signup_waiting,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    # T1-c (FB-12): rosetta — веб-редактор переводов .po (public-схема, superuser-only
    # через ROSETTA_ACCESS_CONTROL_FUNCTION). Инструмент платформы, не тенанта.
    path("rosetta/", include("rosetta.urls")),
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
    # D3: кабинет партнёра-реселлера (public-учётка, read-only список клиентов).
    path("partner/", partners_views.dashboard, name="partner-dashboard"),
    path("entdecken/", aggregator_views.discover_index, name="aggregator-index"),
    # D2.3: клик-счётчик featured (имя дублируется в urls_portal — {% url %} везде).
    path(
        "entdecken/klick/<int:pk>/",
        aggregator_views.featured_click,
        name="aggregator-featured-click",
    ),
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
    # Переключатель языка публичных страниц (регистрация и пр.) — 5 языков хрома.
    path("sprache/", set_public_language, name="public-set-language"),
    # Branchen-Landingpages: обзор + страница на каждый архетип (возможности/функционал).
    path("branchen/", industries_index, name="industries-index"),
    path("branchen/<slug:slug>/", industry_page, name="industry-page"),
    # «Über uns» + правовые страницы ПЛАТФОРМЫ (не тенантов).
    path("ueber-uns/", about_page, name="about-page"),
    path("impressum/", platform_legal, {"kind": "impressum"}, name="platform-impressum"),
    path("datenschutz/", platform_legal, {"kind": "datenschutz"}, name="platform-datenschutz"),
    path("agb/", platform_legal, {"kind": "agb"}, name="platform-agb"),
    # Онбординг: регистрация бизнеса → /registrieren/ (создаёт Tenant + Domain +
    # владельца). Корень (2026-07-13, решение владельца) — обзор Branchen; корень
    # продолжает ловить партнёрский ?ref (исторические ссылки).
    path("registrieren/", BusinessSignupView.as_view(), name="business-signup"),
    # AB5.1: double-opt-in — тенант создаётся только после клика по ссылке из письма.
    path("registrieren/bestaetigen/<str:token>/", signup_confirm, name="business-signup-confirm"),
    path("registrieren/erneut-senden/", signup_resend, name="business-signup-resend"),
    path("", industries_index, name="home"),
    # Ожидание фонового провижининга: «Ihre Website wird eingerichtet…».
    path("anmeldung/<slug:slug>/", signup_waiting, name="signup-waiting"),
]

# Раздача загруженных медиа Django, когда нет S3 (single-сервер).
if getattr(settings, "SERVE_MEDIA", False):
    urlpatterns += [
        path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
