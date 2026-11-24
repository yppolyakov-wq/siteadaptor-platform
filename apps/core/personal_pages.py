"""FB-33 D8: личные страницы витрины — вне индекса и без утечки адреса в Referer.

Личная страница открывается по коду или токену из письма (подтверждение заказа, записи,
номера, билета, резерва; смета и предложение; участники; QR, PDF и iCal по коду; отписка и
настройки рассылки). Поисковику она не нужна, а адрес с токеном — ключ к данным клиента.

Один реестр имён маршрутов (`PERSONAL_ROUTES`); читают его middleware
(`PersonalPageHeadersMiddleware`: `X-Robots-Tag` и `Referrer-Policy`, в том числе у SVG,
PDF и ICS) и процессор контекста витрины (`storefront_personal_noindex`: мета `robots`
и без LocalBusiness в `_base.html`). robots.txt не трогаем: `Disallow` спрятал бы `noindex`.

Замок покрытия (`apps/core/tests/test_fb33_d8_personal_pages.py`): каждый маршрут
`config/urls_tenant.py`, `urls_public.py` и `urls_portal.py` с `<code>`, `<token>`,
`<signed>` или `<secret>` в пути и каждый маршрут ЛК `konto/…` — здесь или в `NOT_PERSONAL`
с причиной. Имена маршрутов у трёх urlconf общие по смыслу (`aggregator-follow-*` — и на
платформе, и на портале).
"""

from __future__ import annotations

#: значения заголовков личной страницы
ROBOTS = "noindex, nofollow"
REFERRER_POLICY = "same-origin"

PERSONAL_ROUTES = frozenset(
    {
        # заказ (Click & Collect, доставка)
        "storefront-order",
        "storefront-order-pay",
        "storefront-reorder",
        # предложение (оферта) и смета ремесла, заявка
        "storefront-offer",
        "storefront-angebot",
        "storefront-auftrag",
        # запись по времени
        "storefront-termin-ok",
        "storefront-termin-pay",
        "storefront-termin-manage",
        # номер (по датам)
        "storefront-stay-ok",
        "storefront-stay-pay",
        "storefront-stay-cancel",
        "storefront-stay-checkin",
        "storefront-stay-ical",
        # билеты событий
        "storefront-ticket-ok",
        "storefront-ticket-pay",
        "storefront-ticket-qr",
        "storefront-ticket-memo",
        "storefront-ticket-cancel",
        "storefront-ticket-participants",
        # резерв акции, купон, ваучер, карта лояльности
        "storefront-confirmation",
        "storefront-reservation-qr",
        "storefront-coupon",
        "storefront-coupon-qr",
        "storefront-voucher-qr",
        "storefront-loyalty-qr",
        # переписка и подтверждение действий ассистента
        "storefront-message-thread",
        "storefront-message-thread-poll",
        "storefront-message-thread-typing",
        "storefront-assistant-confirm",
        "storefront-assistant-decline",
        # рассылка
        "storefront-unsubscribe",
        "storefront-newsletter-preferences",
        "storefront-newsletter-confirm",
        # лента поездки: посты и имена участников группы
        "community-space",
        "community-space-post",
        "community-space-poll",
        "community-space-comment",
        "community-space-join",
        # приглашения и разовые входы по токену или подписи
        "team-join",
        "tg-start",
        "owner-start",
        "owner-confirm-email",
        "shared-preview",
        # ЛК клиента витрины `/konto/` (вход по ссылке — токен в query `?t=`)
        "account-home",
        "account-verify",
        "account-telegram-login",
        "account-logout",
        "account-profile",
        "account-export",
        "account-delete",
        "account-cancel-booking",
        "account-documents",
        "account-document-download",
        "account-document-delete",
        # ЛК городского портала `/konto/` (`config/urls_portal.py`)
        "portal-account",
        "portal-login-verify",
        "portal-logout",
        "portal-favorite-toggle",
        "portal-notifications-toggle",
        "aggregator-follow-toggle",
        # подписка на бизнесы портала (`urls_public.py` и `urls_portal.py`) и подтверждение
        # регистрации бизнеса (`urls_public.py`) — middleware глобальный, действует и там
        "aggregator-follow-confirm",
        "aggregator-follow-manage",
        "aggregator-follow-unsubscribe",
        "business-signup-confirm",
    }
)

#: маршруты с кодом или токеном в пути, которые НЕ личные страницы витрины — с причиной
NOT_PERSONAL = {
    "checkin": "кабинет под логином (сканер билетов), не витрина",
    "redeem-detail": "кабинет под логином (погашение кода на кассе), не витрина",
    "redeem-action": "кабинет под логином (погашение кода на кассе), не витрина",
    "storefront-merchant-feed": "машинный фид Merchant Center: вывод для Google прежний",
    "storefront-merchant-local-feed": "машинный фид Merchant Center: вывод для Google прежний",
    "telegram-webhook": "машинный вызов Telegram (секрет в пути), не страница",
    "portal-telegram-webhook": "машинный вызов Telegram портала (секрет в пути), не страница",
    "account-login": "форма входа ЛК без данных клиента",
    "portal-login": "форма входа ЛК портала без данных клиента",
}


def is_personal(request) -> bool:
    """Ответ на маршрут личной страницы (по `resolver_match`; без разбора — нет)."""
    match = getattr(request, "resolver_match", None)
    return getattr(match, "url_name", None) in PERSONAL_ROUTES
