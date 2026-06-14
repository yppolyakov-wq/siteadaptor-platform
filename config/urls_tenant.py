"""URL routes для TENANT schema ({slug}.siteadaptor.de и custom-домены).

Эти урлы видны на субдоменах конкретного бизнеса. Django admin сюда НЕ
включён — он только на public (см. urls_public). Дашборд владельца — это
отдельный HTMX-UI (Sprint 2), а не Django admin.
"""

from django.conf import settings
from django.urls import include, path
from django.views.static import serve

from apps.billing import views as billing_views
from apps.booking import public_views as booking_public
from apps.core import health
from apps.core.views import (
    dashboard,
    domain_add,
    domain_remove,
    domain_verify,
    domains_view,
    modules_view,
    settings_view,
    setup_view,
    site_view,
)
from apps.inbox import public_views as inbox_public
from apps.jobs import public_views as jobs_public
from apps.orders import public_views as orders_public
from apps.promotions import public_views
from apps.publishing import views as publishing_views
from apps.stays import public_views as stays_public
from apps.telegram import public_views as telegram_public
from apps.telegram import views as telegram_views

urlpatterns = [
    path("accounts/", include("allauth.urls")),
    path("health/", health.liveness, name="health"),
    path("health/ready/", health.readiness, name="health-ready"),
    # --- Кабинет владельца (под логином) ---
    path("dashboard/", dashboard, name="dashboard"),
    # Onboarding-Wizard (Track D / D0c): пошаговая настройка после регистрации.
    path("dashboard/setup/", setup_view, name="setup"),
    path("dashboard/settings/", settings_view, name="settings"),
    # Конструктор витрины v1 (Track C2).
    path("dashboard/site/", site_view, name="site"),
    # Модули кабинета (Track D / D0b): тумблеры опциональных блоков.
    path("dashboard/modules/", modules_view, name="modules"),
    # Self-service custom-домены бизнеса (P2): заявка + DNS-подтверждение.
    path("dashboard/domains/", domains_view, name="domains"),
    path("dashboard/domains/add/", domain_add, name="domain-add"),
    path("dashboard/domains/<int:pk>/verify/", domain_verify, name="domain-verify"),
    path("dashboard/domains/<int:pk>/remove/", domain_remove, name="domain-remove"),
    # Биллинг/подписка (Sprint 5).
    path("dashboard/billing/", billing_views.billing, name="billing"),
    path("dashboard/billing/checkout/", billing_views.checkout, name="billing-checkout"),
    path("dashboard/billing/portal/", billing_views.portal, name="billing-portal"),
    # Приём оплаты от клиентов через Stripe Connect (P2.5a).
    path("dashboard/billing/payments/", billing_views.payments, name="billing-payments"),
    path(
        "dashboard/billing/payments/connect/",
        billing_views.payments_connect,
        name="billing-payments-connect",
    ),
    path(
        "dashboard/billing/payments/callback/",
        billing_views.payments_callback,
        name="billing-payments-callback",
    ),
    # Кабинет заказов Click & Collect (Track D / D2b).
    path("dashboard/orders/", include("apps.orders.urls")),
    # Кабинет записи по времени (Track D / D3c).
    path("dashboard/booking/", include("apps.booking.urls")),
    # Кабинет date-range-броней / Übernachtung (Track E / E2).
    path("dashboard/stays/", include("apps.stays.urls")),
    # Кабинет Aufträge/Angebote / смета Handwerker (G6 / F2).
    path("dashboard/auftraege/", include("apps.jobs.urls")),
    # Журнал выручки Light-Finance (Track D / D4a).
    path("dashboard/finance/", include("apps.finance.urls")),
    # Inbox: чат/поддержка/тикеты клиент↔бизнес (M22a).
    path("dashboard/inbox/", include("apps.inbox.urls")),
    # Hilfe: платформенная техподдержка тенант↔SiteAdaptor (M22c).
    path("dashboard/help/", include("apps.support.urls")),
    # Каналы публикации (Sprint 4).
    path("dashboard/channels/", publishing_views.channels, name="channels"),
    path("dashboard/channels/toggle/", publishing_views.channel_toggle, name="channel-toggle"),
    path("dashboard/channels/config/", publishing_views.channel_config, name="channel-config"),
    # In-app OAuth (OAuth-A): старт из кабинета → провайдер → callback на public.
    path(
        "dashboard/channels/connect/<str:provider>/",
        publishing_views.oauth_start,
        name="channel-oauth-start",
    ),
    # Каталог в кабинете владельца.
    path("catalog/", include("apps.catalog.urls")),
    # CSV-импорт товаров.
    path("imports/", include("apps.imports.urls")),
    # Акции и брони в кабинете владельца.
    path("promotions/", include("apps.promotions.urls")),
    # CRM-минимум «Клиенты» (Track C3).
    path("crm/", include("apps.crm.urls")),
    # --- Публичная витрина (без логина), на корне субдомена ---
    path("", public_views.storefront_home, name="storefront-home"),
    path("lang/", public_views.set_language, name="storefront-set-language"),
    # Каталог товаров на витрине (Track C1).
    path("sortiment/", public_views.product_list, name="storefront-products"),
    path("sortiment/<uuid:pk>/", public_views.product_detail, name="storefront-product"),
    # Click & Collect (Track D / D2a): корзина-сессия + оформление самовывоза.
    path("warenkorb/", orders_public.cart_view, name="storefront-cart"),
    path("warenkorb/add/", orders_public.cart_add, name="storefront-cart-add"),
    path("warenkorb/remove/", orders_public.cart_remove, name="storefront-cart-remove"),
    path("warenkorb/bestellen/", orders_public.checkout, name="storefront-checkout"),
    path("bestellung/<str:code>/", orders_public.order_confirmation, name="storefront-order"),
    # Запись по времени (Track D / D3b): ресурс → день → слот → форма.
    path("termin/", booking_public.termin_index, name="storefront-termin"),
    path("termin/<uuid:pk>/", booking_public.termin_slots, name="storefront-termin-slots"),
    path("termin/<uuid:pk>/buchen/", booking_public.termin_book, name="storefront-termin-book"),
    # Запись на услугу (G10): услуга → слот (по всем ресурсам) → форма.
    path(
        "termin/leistung/<uuid:pk>/", booking_public.service_slots, name="storefront-service-slots"
    ),
    path(
        "termin/leistung/<uuid:pk>/buchen/",
        booking_public.service_book,
        name="storefront-service-book",
    ),
    path("t/<str:code>/", booking_public.termin_confirmation, name="storefront-termin-ok"),
    # Übernachtung / date-range-бронь (Track E / E3): юнит → даты → форма.
    path("unterkunft/", stays_public.unterkunft_index, name="storefront-unterkunft"),
    path("unterkunft/<uuid:pk>/", stays_public.unterkunft_unit, name="storefront-unterkunft-unit"),
    path(
        "unterkunft/<uuid:pk>/buchen/",
        stays_public.unterkunft_book,
        name="storefront-unterkunft-book",
    ),
    path("s/<str:code>/", stays_public.unterkunft_confirmation, name="storefront-stay-ok"),
    # Handwerker: заявка + публичное Angebot (G6 / F3).
    path("anfrage/", jobs_public.anfrage, name="storefront-anfrage"),
    path("angebot/<uuid:token>/", jobs_public.angebot, name="storefront-angebot"),
    # Чат/вопрос клиента (M22b): форма «Frage stellen» + публичный тред по токену.
    path("nachricht/", inbox_public.contact, name="storefront-message"),
    path("nachricht/<uuid:token>/", inbox_public.thread, name="storefront-message-thread"),
    path("p/<uuid:pk>/", public_views.promotion_detail, name="storefront-promotion"),
    path("p/<uuid:pk>/reserve/", public_views.reservation_create, name="storefront-reserve"),
    path("p/<uuid:pk>/waitlist/", public_views.waitlist_join, name="storefront-waitlist"),
    path("p/<uuid:pk>/qr.svg", public_views.promotion_qr, name="storefront-promotion-qr"),
    path("r/<str:code>/", public_views.reservation_confirmation, name="storefront-confirmation"),
    path("r/<str:code>/qr.svg", public_views.reservation_qr, name="storefront-reservation-qr"),
    path("v/<str:code>/qr.svg", public_views.voucher_qr, name="storefront-voucher-qr"),
    path("c/<uuid:token>/qr.svg", public_views.loyalty_card_qr, name="storefront-loyalty-qr"),
    path("impressum/", public_views.impressum, name="storefront-impressum"),
    path("datenschutz/", public_views.privacy, name="storefront-privacy"),
    path("widerruf/", public_views.withdrawal, name="storefront-withdrawal"),
    path("u/<uuid:token>/", public_views.unsubscribe, name="storefront-unsubscribe"),
    # Local SEO (Track B5): sitemap + robots на корне витрины.
    path("sitemap.xml", public_views.sitemap_xml, name="storefront-sitemap"),
    path("robots.txt", public_views.robots_txt, name="storefront-robots"),
    # Каталог-фид (M23b): Google Merchant / Meta Commerce — загрузка по URL.
    path("feed/google.xml", public_views.product_feed_xml, name="storefront-product-feed"),
    # Telegram-бот (M23/TG1): кабинет + публичный webhook на домене арендатора.
    path("dashboard/telegram/", telegram_views.settings_view, name="telegram-settings"),
    path("dashboard/telegram/connect/", telegram_views.connect, name="telegram-connect"),
    path("dashboard/telegram/disconnect/", telegram_views.disconnect, name="telegram-disconnect"),
    path("tg/<str:secret>/", telegram_public.webhook, name="telegram-webhook"),
]

# Раздача загруженных медиа Django, когда нет S3 (single-сервер).
if getattr(settings, "SERVE_MEDIA", False):
    urlpatterns += [
        path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
