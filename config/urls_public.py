"""URL routes для SHARED schema (агрегатор, public-сайт, admin).

Эти урлы доступны на основном домене siteadaptor.de.
Django admin живёт ТОЛЬКО здесь (платформенный суперадмин), не на субдоменах.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.aggregator import follow_views as aggregator_follow_views
from apps.aggregator import reports as aggregator_reports
from apps.aggregator import reviews_views as aggregator_reviews_views
from apps.aggregator import views as aggregator_views
from apps.billing import views as billing_views
from apps.billing.webhooks import stripe_webhook
from apps.core import health
from apps.core.media_views import serve_media
from apps.partners import views as partners_views
from apps.publishing import views as publishing_views
from apps.tenants import quickstart_views
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
    # R5: платформенная BI-панель (MRR/churn/LTV) — только суперадмин (staff).
    path("plattform/bi/", billing_views.platform_bi, name="platform-bi"),
    path("entdecken/", aggregator_views.discover_index, name="aggregator-index"),
    # FD-4: платформенный Finder — ВЫШЕ catch-all города (иначе «finder» = city).
    path("entdecken/finder/", aggregator_views.platform_finder, name="aggregator-finder"),
    # MEN-12: отложенные предложения и их сравнение (сессия, без аккаунта) —
    # ВЫШЕ catch-all города, иначе «merkliste» распознаётся как город.
    path(
        "entdecken/merkliste/",
        aggregator_views.shortlist_compare,
        name="aggregator-shortlist",
    ),
    path(
        "entdecken/merkliste/toggle/",
        aggregator_views.shortlist_toggle,
        name="aggregator-shortlist-toggle",
    ),
    # D2.3: клик-счётчик featured (имя дублируется в urls_portal — {% url %} везде).
    path(
        "entdecken/klick/<int:pk>/",
        aggregator_views.featured_click,
        name="aggregator-featured-click",
    ),
    # В5 V5-2: переход «к продавцу» через счётчик — ВЫШЕ catch-all <city>.
    path(
        "entdecken/weiter/<int:pk>/",
        aggregator_views.outbound_click,
        name="aggregator-outbound",
    ),
    # T-8.6 «Melden» (имя дублируется в urls_portal — {% url %} везде).
    # T-8.24: страница предложения (до catch-all <city>).
    path("entdecken/angebot/<int:pk>/", aggregator_views.offer_page, name="aggregator-offer"),
    # T-8.8: открытый фид основного домена (`?city=`) — до catch-all <city>.
    path("entdecken/feed.json", aggregator_views.discover_feed_json, name="aggregator-feed-json"),
    path("entdecken/feed.xml", aggregator_views.discover_feed_atom, name="aggregator-feed-atom"),
    path("entdecken/melden/<int:pk>/", aggregator_reports.report_listing, name="aggregator-report"),
    # A8/E-2 (T-8.7: перенесено ВЫШЕ catch-all <city>/<business_type> — иначе
    # «unternehmen» резолвился как город): страница бизнеса (отзывы read-only) и на главном домене — тот же
    # name, что на портальных хостах, чтобы {% url 'portal-business' %} работал везде.
    path(
        "entdecken/unternehmen/<slug:slug>/",
        aggregator_reviews_views.business_page,
        name="portal-business",
    ),
    # T-8.7 «Folgen» на основном домене (имена общие с urls_portal).
    path("entdecken/folgen/", aggregator_follow_views.follow_page, name="aggregator-follow"),
    path(
        "entdecken/folgen/bestaetigen/<str:token>/",
        aggregator_follow_views.follow_confirm,
        name="aggregator-follow-confirm",
    ),
    path(
        "entdecken/folgen/verwalten/<str:token>/",
        aggregator_follow_views.follow_manage,
        name="aggregator-follow-manage",
    ),
    path(
        "entdecken/folgen/abmelden/<str:token>/",
        aggregator_follow_views.follow_unsubscribe,
        name="aggregator-follow-unsubscribe",
    ),
    path("entdecken/<str:city>/", aggregator_views.city_listing, name="aggregator-city"),
    path(
        "entdecken/<str:city>/<str:business_type>/",
        aggregator_views.city_listing,
        name="aggregator-city-type",
    ),
    # Local SEO (Track B5): sitemap + robots основного домена.
    path("sitemap.xml", aggregator_views.sitemap_xml, name="aggregator-sitemap"),
    path("robots.txt", aggregator_views.robots_txt, name="aggregator-robots"),
    # T-8.8: llms.txt платформы (порталы, /entdecken/, фид).
    path("llms.txt", aggregator_views.llms_txt, name="aggregator-llms"),
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
    # T-8.5 «Aktion in 3 Klicks»: регистрация + первая акция одной страницей.
    path("aktion-starten/", quickstart_views.quick_start, name="quick-start"),
    path("aktion-starten/adresse/", quickstart_views.slug_check, name="quick-start-slug"),
    path("aktion-starten/<slug:slug>/", quickstart_views.quick_waiting, name="quick-start-waiting"),
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
        path("media/<path:path>", serve_media),  # корень читает гейт при запросе
    ]
