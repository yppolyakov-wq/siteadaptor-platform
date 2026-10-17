"""URL routes портальных хостов (P2.1b).

Подставляется в request.urlconf middleware-резолвером
(apps.aggregator.middleware.AggregatorPortalMiddleware), когда host сопоставлен
с активным AggregatorPortal. Корень — листинги фильтра портала, /<facet>/ —
уточнение по свободной оси (см. apps.aggregator.portal_views).
"""

from django.conf import settings
from django.urls import path

from apps.aggregator import account_views, follow_views, portal_views, reviews_views
from apps.aggregator import reports as aggregator_reports
from apps.aggregator import telegram_bot as portal_telegram
from apps.aggregator import views as aggregator_views
from apps.core import health
from apps.core.media_views import serve_media
from apps.tenants.views import set_public_language

urlpatterns = [
    path("", portal_views.portal_home, name="portal-home"),
    # Health-пробы должны отвечать и на хосте портала (мониторинг/Caddy).
    # Стоят до <facet>, иначе сегмент ушёл бы в уточнение и дал 404.
    path("health/", health.liveness, name="health"),
    path("health/ready/", health.readiness, name="health-ready"),
    # SEO портала (P2.1c): sitemap/robots по хосту портала.
    path("sitemap.xml", portal_views.portal_sitemap_xml, name="portal-sitemap"),
    path("robots.txt", portal_views.portal_robots_txt, name="portal-robots"),
    # T-8.8: машиночитаемость — открытый фид (JSON Feed/Atom) + llms.txt портала.
    path("feed.json", portal_views.portal_feed_json, name="portal-feed-json"),
    path("feed.xml", portal_views.portal_feed_atom, name="portal-feed-atom"),
    path("llms.txt", portal_views.portal_llms_txt, name="portal-llms"),
    # Клиентский аккаунт (P2.3a): magic-link вход. Тоже до <facet>.
    path("konto/", account_views.account, name="portal-account"),
    path("konto/login/", account_views.login_view, name="portal-login"),
    path("konto/login/verify/", account_views.login_verify, name="portal-login-verify"),
    path("konto/logout/", account_views.logout_view, name="portal-logout"),
    # Избранное (P2.3b).
    path("konto/favoriten/", account_views.favorite_toggle, name="portal-favorite-toggle"),
    # Настройки уведомлений (P2.3d).
    path(
        "konto/benachrichtigungen/",
        account_views.notifications_toggle,
        name="portal-notifications-toggle",
    ),
    # T-8.7 «Folgen»: подписки жителя (имена общие с urls_public — {% url %} везде).
    path("folgen/", follow_views.follow_page, name="aggregator-follow"),
    path(
        "folgen/bestaetigen/<str:token>/",
        follow_views.follow_confirm,
        name="aggregator-follow-confirm",
    ),
    path(
        "folgen/verwalten/<str:token>/", follow_views.follow_manage, name="aggregator-follow-manage"
    ),
    path(
        "folgen/abmelden/<str:token>/",
        follow_views.follow_unsubscribe,
        name="aggregator-follow-unsubscribe",
    ),
    path("konto/folgen/", follow_views.follow_toggle, name="aggregator-follow-toggle"),
    # Страница бизнеса + отзывы (G8a). До <facet>: 2-сегментный путь, не коллизит.
    path("unternehmen/<slug:slug>/", reviews_views.business_page, name="portal-business"),
    path(
        "unternehmen/<slug:slug>/bewerten/",
        reviews_views.submit_review,
        name="portal-business-review",
    ),
    # Telegram-бот портала (TG4): публичный webhook на хосте портала.
    path("tg/<str:secret>/", portal_telegram.webhook, name="portal-telegram-webhook"),
    # D2.3: клик-счётчик featured (то же имя, что в urls_public) — до catch-all.
    path("klick/<int:pk>/", aggregator_views.featured_click, name="aggregator-featured-click"),
    # В5 V5-2: переход «к продавцу» через счётчик (то же имя, что в urls_public).
    path("weiter/<int:pk>/", aggregator_views.outbound_click, name="aggregator-outbound"),
    # T-8.6 «Melden» (то же имя, что в urls_public) — до catch-all.
    path("melden/<int:pk>/", aggregator_reports.report_listing, name="aggregator-report"),
    # T-8.24: страница предложения внутри портала (то же имя, что в urls_public).
    path("angebot/<int:pk>/", aggregator_views.offer_page, name="aggregator-offer"),
    # T-8.17: страницы районов города (до catch-all <facet>).
    path("stadtteil/<slug:district>/", portal_views.portal_home, name="portal-district"),
    path(
        "stadtteil/<slug:district>/<str:facet>/",
        portal_views.portal_home,
        name="portal-district-facet",
    ),
    # Переключатель языка (тот же, что на публичном хосте) — до catch-all <facet>.
    path("sprache/", set_public_language, name="portal-set-language"),
    # Блок А3: «Für Unternehmen» — до catch-all <facet>.
    path("fuer-unternehmen/", portal_views.for_business, name="portal-for-business"),
    path("<str:facet>/", portal_views.portal_home, name="portal-facet"),
]

# Картинки листингов — относительные /media/... (single-сервер без S3),
# поэтому портальному хосту нужен тот же фолбэк, что и urls_public.
if getattr(settings, "SERVE_MEDIA", False):
    urlpatterns = [
        path("media/<path:path>", serve_media),  # корень читает гейт при запросе
    ] + urlpatterns
