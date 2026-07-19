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
    board,
    board_settings,
    dashboard,
    domain_add,
    domain_remove,
    domain_verify,
    domains_view,
    extras_view,
    finder_settings,
    home_builder_view,
    kanban_action,
    languages_view,
    legal_docs_view,
    media_library,
    menu_builder_view,
    modules_view,
    notifications_settings,
    pages_view,
    payment_settings,
    sections_view,
    sellable_manage,
    sellable_visibility,
    seo_settings_view,
    set_cabinet_lang_view,
    set_classic_ui_view,
    set_ui_mode_view,
    settings_view,
    setup_view,
    share_preview_issue,
    site_cblock_photo_edit,
    site_inline_edit,
    site_preview,
    site_preview_draft,
    site_view,
    status_labels_save,
    status_manager,
    status_manager_save,
    transitions_save,
)
from apps.events import public_views as events_public
from apps.events import views as events_views
from apps.inbox import public_views as inbox_public
from apps.inventory.views import stock as stock_view
from apps.inventory.views_purchasing import purchasing_view
from apps.jobs import public_views as jobs_public
from apps.loyalty import public_views as loyalty_public
from apps.orders import public_views as orders_public
from apps.promotions import public_views
from apps.publishing import views as publishing_views
from apps.stays import public_views as stays_public
from apps.telegram import public_views as telegram_public
from apps.telegram import views as telegram_views
from apps.tenants.demo_images import demo_image_view

urlpatterns = [
    path("accounts/", include("allauth.urls")),
    # PR-IMG: локальные демо-фото (тематические SVG) — самодостаточно, без внешних
    # сервисов (GDPR-чисто). Демо-киты ссылаются сюда вместо loremflickr.
    path("medien/demo.svg", demo_image_view, name="demo-image"),
    path("health/", health.liveness, name="health"),
    path("health/ready/", health.readiness, name="health-ready"),
    # --- Кабинет владельца (под логином) ---
    path("dashboard/", dashboard, name="dashboard"),
    # Onboarding-Wizard (Track D / D0c; B.4 линейный ≤10): пошаговая настройка после
    # регистрации. `/willkommen/` — дружелюбный алиас на тот же мастер (анти-Битрикс).
    path("dashboard/setup/", setup_view, name="setup"),
    path("willkommen/", setup_view, name="willkommen"),
    path("dashboard/settings/", settings_view, name="settings"),
    # UD4-2: кабинет «Benachrichtigungen» — каналы email/Telegram per-событие.
    path(
        "dashboard/settings/notifications/",
        notifications_settings,
        name="notifications-settings",
    ),
    # L2 (Волна L): кабинет «Sprachen» — включение языков витрины + дефолт.
    path("dashboard/settings/languages/", languages_view, name="languages"),
    # FD-3-lite: тумблер+превью Finder (вкладка Marketing-хаба «Erweitert»).
    path("dashboard/finder/", finder_settings, name="finder-settings"),
    # W4-3: единый экран «Zahlung & Versand» (свод оплаты/доставки).
    path("dashboard/settings/payments/", payment_settings, name="payment-settings"),
    # L5/E-2: кабинет «Recht» — правовые тексты per-locale (LegalDoc) + AGB.
    path("dashboard/recht/", legal_docs_view, name="legal-docs"),
    path("dashboard/extras/", extras_view, name="extras"),
    # Конструктор витрины v1 (Track C2).
    path("dashboard/site/", site_view, name="site"),
    path("dashboard/site/home/", home_builder_view, name="site-home"),
    path("dashboard/site/menu/", menu_builder_view, name="site-menu"),
    path("dashboard/site/seo/", seo_settings_view, name="site-seo"),
    path("dashboard/site/sections/", sections_view, name="site-sections"),
    path("dashboard/site/pages/", pages_view, name="site-pages"),
    path("dashboard/site/preview/", site_preview, name="site-preview"),
    path("dashboard/site/preview/draft/", site_preview_draft, name="site-preview-draft"),
    # A4: выпуск share-ссылки на снапшот черновика (read-only превью).
    path("dashboard/site/share-preview/", share_preview_issue, name="site-share-preview"),
    path("dashboard/site/preview/edit/", site_inline_edit, name="site-inline-edit"),
    # UC6-4: замена фото C-блока прямо на канве превью (multipart).
    path("dashboard/site/cblock-photo/", site_cblock_photo_edit, name="site-cblock-photo-edit"),
    # Модули кабинета (Track D / D0b): тумблеры опциональных блоков.
    path("dashboard/modules/", modules_view, name="modules"),
    # W3-fix: переключатель Einfach/Experte из шапки (работает с любой страницы).
    path("dashboard/ui-mode/", set_ui_mode_view, name="set-ui-mode"),
    # Страховка редизайна (трек ST): тумблер «Klassische Ansicht» (на «Funktionen»).
    path("dashboard/classic-ui/", set_classic_ui_view, name="set-classic-ui"),
    path("dashboard/cabinet-lang/", set_cabinet_lang_view, name="set-cabinet-lang"),
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
    # E7-3: способы оплаты Stripe Checkout (payment_method_types).
    path(
        "dashboard/billing/payments/methods/",
        billing_views.payments_methods,
        name="billing-payments-methods",
    ),
    # U-D3: кабинет склада (приёмки/корректировки/инвентаризация/реконсиляция).
    path("dashboard/stock/", stock_view, name="stock"),
    # Склад-2 E3: закупки (Lieferanten/Bestellungen/Wareneingang).
    path("dashboard/purchasing/", purchasing_view, name="purchasing"),
    # U-D2: единая Kanban-доска транзакций (заказы/брони/…) + generic FSM-action.
    path("dashboard/board/", board, name="board"),
    # W5: настройки колонок доски (переименование/порядок/скрытие).
    path("dashboard/board/settings/", board_settings, name="board-settings"),
    path(
        "dashboard/board/<str:kind>/<uuid:pk>/action/",
        kanban_action,
        name="board-action",
    ),
    # FB-4a/b: свои имена статусов (order/booking/stay) — кабинет-отображение.
    path(
        "dashboard/status-labels/<str:kind>/",
        status_labels_save,
        name="status-labels-save",
    ),
    # FB-3: правила переходов статусов (скрыть не-danger переходы) — кабинет.
    path(
        "dashboard/status-transitions/<str:kind>/",
        transitions_save,
        name="transitions-save",
    ),
    # FB-3 Вариант B: редактор своих статусов + переходов (order/booking/stay).
    path("dashboard/status-manager/<str:kind>/", status_manager, name="status-manager"),
    path(
        "dashboard/status-manager/<str:kind>/save/",
        status_manager_save,
        name="status-manager-save",
    ),
    # FB-8: единый обзор продаваемых сущностей + тумблер видимости.
    path("dashboard/angebote/", sellable_manage, name="sellable-manage"),
    path(
        "dashboard/angebote/<str:kind>/<uuid:pk>/sichtbar/",
        sellable_visibility,
        name="sellable-visibility",
    ),
    # Кабинет заказов Click & Collect (Track D / D2b).
    path("dashboard/orders/", include("apps.orders.urls")),
    # Кабинет записи по времени (Track D / D3c).
    path("dashboard/booking/", include("apps.booking.urls")),
    # Кабинет date-range-броней / Übernachtung (Track E / E2).
    path("dashboard/stays/", include("apps.stays.urls")),
    # Подборки (коллекции) услуг/номеров — чипы-фасет витрины (UB3-2).
    path("dashboard/collections/", include("apps.collections.urls")),
    # Кабинет событий/билетов (A6).
    path("dashboard/events/", include("apps.events.urls")),
    # CM-1: блог — свой модуль (не events): кабинет на /dashboard/blog/,
    # вьюхи организационно остаются в apps/events (модель самостоятельна).
    path("dashboard/blog/", events_views.blog_list, name="blog-list"),
    path("dashboard/blog/<uuid:pk>/", events_views.blog_edit, name="blog-edit"),
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
    # CM-2: контент-календарь (посты в каналы; отложенная отправка — beat).
    path("dashboard/posts/", publishing_views.posts, name="publishing-posts"),
    # CM-4: медиа-библиотека тенанта (реестр MediaAsset поверх FileRef-копий).
    path("dashboard/medien/", media_library, name="media-library"),
    # CM-6: кабинет «Bewertungen» — модерация/ответы на отзывы.
    path("dashboard/reviews/", include("apps.reviews.urls")),
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
    # ЛК клиента на витрине (CA1): magic-link вход (гейтинг модуля во вьюхах).
    path("konto/", include("apps.account.urls")),
    # --- Публичная витрина (без логина), на корне субдомена ---
    path("", public_views.storefront_home, name="storefront-home"),
    path("aktionen/", public_views.promotion_list, name="storefront-aktionen"),
    path("treue/", public_views.loyalty_page, name="storefront-loyalty"),
    path("ueber-uns/", public_views.about_page, name="storefront-about"),
    # FD-1: Finder «вопросы → 3 предложения» (опция; 404 пока не включён).
    path("finder/", public_views.finder_page, name="storefront-finder"),
    path("lang/", public_views.set_language, name="storefront-set-language"),
    # Каталог товаров на витрине (Track C1).
    path("sortiment/", public_views.product_list, name="storefront-products"),
    path("sortiment/<uuid:pk>/", public_views.product_detail, name="storefront-product"),
    # A1/A2: отзыв о товаре (только верифицированный покупатель).
    path(
        "sortiment/<uuid:pk>/bewerten/",
        public_views.product_review_submit,
        name="storefront-product-review",
    ),
    # Click & Collect (Track D / D2a): корзина-сессия + оформление самовывоза.
    path("warenkorb/", orders_public.cart_view, name="storefront-cart"),
    path("warenkorb/add/", orders_public.cart_add, name="storefront-cart-add"),
    path("warenkorb/quick/<uuid:pk>/", orders_public.quick_add_form, name="storefront-quick-add"),
    path("warenkorb/remove/", orders_public.cart_remove, name="storefront-cart-remove"),
    path("warenkorb/combo-remove/", orders_public.combo_remove, name="storefront-combo-remove"),
    path("warenkorb/nochmal/<str:code>/", orders_public.reorder, name="storefront-reorder"),
    path("warenkorb/code/", orders_public.cart_apply_code, name="storefront-cart-code"),
    path(
        "warenkorb/code-remove/", orders_public.cart_remove_code, name="storefront-cart-code-remove"
    ),
    # Комбо-наборы (A4): витрина + конфигуратор → корзина.
    path("kombi/", orders_public.combo_list_public, name="storefront-combos"),
    path("kombi/add/", orders_public.combo_add, name="storefront-combo-add"),
    path("kombi/<uuid:pk>/", orders_public.combo_detail_public, name="storefront-combo"),
    path("warenkorb/bestellen/", orders_public.checkout, name="storefront-checkout"),
    path("bestellung/<str:code>/", orders_public.order_confirmation, name="storefront-order"),
    # B2.1: повторная Stripe-оплата неоплаченного заказа (Checkout на лету).
    path("bestellung/<str:code>/bezahlen/", orders_public.order_pay, name="storefront-order-pay"),
    # LS-3: персональное предложение из чата (Sofort-Angebot) — короткий
    # префикс /o/ (хаус-стиль /r/ /t/ /s/; /angebot/ занят сметой jobs).
    path("o/<uuid:token>/", orders_public.offer_page, name="storefront-offer"),
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
    # UA1-1 (E-1): SEO/деталь услуги (описание) → CTA ведёт на слот-пикер выше.
    path("leistung/<uuid:pk>/", booking_public.service_detail, name="storefront-service-detail"),
    # UA4-4b: приём отзыва об услуге (verified customer).
    path(
        "leistung/<uuid:pk>/bewerten/",
        booking_public.service_review_submit,
        name="storefront-service-review",
    ),
    path("t/<str:code>/", booking_public.termin_confirmation, name="storefront-termin-ok"),
    # B2.2: повторная оплата депозита (Checkout на лету).
    path("t/<str:code>/bezahlen/", booking_public.termin_pay, name="storefront-termin-pay"),
    # A3: онлайн-продажа Mehrfachkarte.
    path("karten/", booking_public.karten, name="storefront-karten"),
    path("karten/<uuid:pk>/kaufen/", booking_public.karte_kaufen, name="storefront-karte-kaufen"),
    # Übernachtung / date-range-бронь (Track E / E3): юнит → даты → форма.
    path("unterkunft/", stays_public.unterkunft_index, name="storefront-unterkunft"),
    path("unterkunft/<uuid:pk>/", stays_public.unterkunft_unit, name="storefront-unterkunft-unit"),
    # UA4-4b: приём отзыва о номере (verified guest).
    path(
        "unterkunft/<uuid:pk>/bewerten/",
        stays_public.stay_review_submit,
        name="storefront-stay-review",
    ),
    path(
        "unterkunft/<uuid:pk>/kalender/",
        stays_public.unterkunft_unit_calendar,
        name="storefront-unterkunft-calendar",
    ),
    path(
        "unterkunft/<uuid:pk>/buchen/",
        stays_public.unterkunft_book,
        name="storefront-unterkunft-book",
    ),
    path("s/<str:code>/", stays_public.unterkunft_confirmation, name="storefront-stay-ok"),
    # B2.3: повторная оплата предоплаты (Checkout на лету).
    path("s/<str:code>/bezahlen/", stays_public.stay_pay, name="storefront-stay-pay"),
    # H4b: самостоятельная отмена брони гостем по подписанной ссылке.
    path("stornieren/<str:token>/", stays_public.unterkunft_cancel, name="storefront-stay-cancel"),
    # G6: Online-Checkin / цифровой Meldeschein по подписанной ссылке.
    path("checkin/<str:token>/", stays_public.unterkunft_checkin, name="storefront-stay-checkin"),
    # H6: Hausordnung / правила проживания.
    path("hausordnung/", stays_public.hausordnung, name="storefront-hausordnung"),
    # G1→B1.1: Geschenkgutscheine — нейтральные вьюхи (все архетипы, модуль gift).
    path("gutschein/", loyalty_public.gutschein_index, name="storefront-gutschein"),
    path("gutschein/kaufen/", loyalty_public.gutschein_buy, name="storefront-gutschein-buy"),
    path("gutschein/danke/", loyalty_public.gutschein_confirmation, name="storefront-gutschein-ok"),
    # iCal-фид занятости юнита (A5b): Booking.com/Airbnb/Google подписываются.
    path("stays/ical/<str:token>.ics", stays_public.unterkunft_ical, name="storefront-stay-ical"),
    # G8: фид цен/наличия для метапоиска (Google Hotel Center / channel).
    path("stays/feed.json", stays_public.stays_feed, name="storefront-stay-feed"),
    # События/билеты (A6c): список → событие → покупка → подтверждение.
    path("veranstaltung/", events_public.veranstaltung_index, name="storefront-events"),
    # R3b: календарь ретритов + iCal-фид (до <uuid:pk>, чтобы не перехватывались).
    path(
        "veranstaltung/kalender/",
        events_public.veranstaltung_calendar,
        name="storefront-events-calendar",
    ),
    path(
        "veranstaltung/feed.ics",
        events_public.veranstaltung_ical_feed,
        name="storefront-events-ical-feed",
    ),
    path("veranstaltung/<uuid:pk>/", events_public.veranstaltung_detail, name="storefront-event"),
    # UA4-4b: приём отзыва о событии (verified attendee).
    path(
        "veranstaltung/<uuid:pk>/bewerten/",
        events_public.event_review_submit,
        name="storefront-event-review",
    ),
    path(
        "veranstaltung/<uuid:pk>/ical",
        events_public.veranstaltung_ical,
        name="storefront-event-ical",
    ),
    path(
        "veranstaltung/<uuid:pk>/buchen/",
        events_public.veranstaltung_book,
        name="storefront-event-book",
    ),
    path(
        "veranstaltung/<uuid:pk>/warteliste/",
        events_public.veranstaltung_waitlist,
        name="storefront-event-waitlist",
    ),
    path("e/<str:code>/", events_public.veranstaltung_confirmation, name="storefront-ticket-ok"),
    # B2.3: повторная оплата билета (Checkout на лету).
    path("e/<str:code>/bezahlen/", events_public.ticket_pay, name="storefront-ticket-pay"),
    path("e/<str:code>/qr.svg", events_public.ticket_qr, name="storefront-ticket-qr"),  # RT1
    # RT4: публичный блог/новости.
    path("blog/", events_public.blog_index, name="storefront-blog"),
    path("blog/<slug:slug>/", events_public.blog_detail, name="storefront-blog-post"),
    path("e/<str:code>/memo.pdf", events_public.veranstaltung_memo, name="storefront-ticket-memo"),
    # R12: самостоятельная отмена билета гостем по подписанной ссылке.
    path(
        "e/storno/<str:token>/",
        events_public.veranstaltung_cancel,
        name="storefront-ticket-cancel",
    ),
    # R3: преподаватели/ведущие — список + страница учителя.
    path("lehrer/", events_public.lehrer_index, name="storefront-teachers"),
    path("lehrer/<uuid:pk>/", events_public.lehrer_detail, name="storefront-teacher"),
    # Handwerker: заявка + публичное Angebot (G6 / F3).
    path("anfrage/", jobs_public.anfrage, name="storefront-anfrage"),
    path("rueckruf/", jobs_public.rueckruf, name="storefront-rueckruf"),
    path("auftrag/<uuid:token>/", jobs_public.auftrag_status, name="storefront-auftrag"),
    path("angebot/<uuid:token>/", jobs_public.angebot, name="storefront-angebot"),
    # Чат/вопрос клиента (M22b): форма «Frage stellen» + публичный тред по токену.
    path("nachricht/", inbox_public.contact, name="storefront-message"),
    path("nachricht/<uuid:token>/", inbox_public.thread, name="storefront-message-thread"),
    path(
        "nachricht/<uuid:token>/poll/",
        inbox_public.thread_poll,
        name="storefront-message-thread-poll",
    ),
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
    # E-2/L5: AGB — страница есть только при заданном тексте (LegalDoc).
    path("agb/", public_views.agb, name="storefront-agb"),
    # A4: анонимное read-only превью черновика по share-токену.
    path("vorschau/<str:token>/", public_views.shared_preview, name="shared-preview"),
    # C.1: онлайн-форма Widerruf (заявление уходит продавцу).
    path("widerruf-formular/", public_views.withdrawal_form, name="storefront-withdrawal-form"),
    path("u/<uuid:token>/", public_views.unsubscribe, name="storefront-unsubscribe"),
    # G3: подписка на рассылку (Double-Opt-In) + подтверждение по ссылке.
    path("newsletter/", public_views.newsletter_signup, name="storefront-newsletter"),
    path(
        "newsletter/bestaetigen/<str:token>/",
        public_views.newsletter_confirm,
        name="storefront-newsletter-confirm",
    ),
    # Local SEO (Track B5): sitemap + robots на корне витрины.
    path("sitemap.xml", public_views.sitemap_xml, name="storefront-sitemap"),
    path("robots.txt", public_views.robots_txt, name="storefront-robots"),
    # SEO-3c (AI-SEO/GEO): llms.txt — краткое описание бизнеса для AI-ассистентов.
    path("llms.txt", public_views.llms_txt, name="storefront-llms"),
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
