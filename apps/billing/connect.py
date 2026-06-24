"""Stripe Connect: оплата конечного клиента бизнесу напрямую (P2.5).

Деньги идут «клиент → бизнес» через connected account бизнеса (в отличие от
подписки «бизнес → платформа», см. services.py). Платформа может удержать
application fee — процент задаётся ПО ТИПУ БИЗНЕСА (решение владельца 2026-06-12:
по умолчанию 0 для всех, но настройка существует и включается позже).

Модель монетизации — ВАРИАНТ B (решение владельца 2026-06-13): комиссию НЕ
удерживаем в платеже (клиент платит бизнесу 100 % через его connected account),
а начисляем как «Nutzungsgebühr» (тот же % по типу бизнеса) строкой в счёте
подписки за систему. Поэтому при платежах application_fee = 0; функции
application_fee_* переиспользуются для расчёта этой usage-комиссии. Сам расчёт
оборота + строка в инвойсе — отдельная будущая подзадача (P2.5-fee), включаем
при ненулевом проценте. Вариант «платформа собирает + payout» (option 3) —
резерв под маркетплейс. Онбординг (OAuth) и платежи — P2.5a/b/c.
"""

from decimal import ROUND_DOWN, Decimal
from urllib.parse import urlencode

import stripe
from django.conf import settings

# Дефолтная комиссия по типу бизнеса — пусто = 0 % для всех. Оверрайд через
# settings.BILLING_APPLICATION_FEE_PERCENT (env), ключ "" — дефолт для всех типов.
_DEFAULT_FEE_PERCENT: dict[str, str] = {}


def _fee_table() -> dict[str, str]:
    return {**_DEFAULT_FEE_PERCENT, **getattr(settings, "BILLING_APPLICATION_FEE_PERCENT", {})}


def application_fee_percent(business_type: str) -> Decimal:
    """Процент application fee для типа бизнеса (Decimal ≥ 0, по умолчанию 0).

    Приоритет: точный тип → ключ "" (общий дефолт) → 0.
    """
    table = _fee_table()
    raw = table.get(business_type)
    if raw is None:
        raw = table.get("", 0)
    pct = Decimal(str(raw or 0))
    return pct if pct > 0 else Decimal(0)


def application_fee_cents(amount_cents: int, business_type: str) -> int:
    """application fee в центах от суммы платежа (округление вниз).

    0 при нулевом проценте — тогда Checkout создаётся вообще без application_fee
    (платформа ничего не удерживает, бизнес получает всё).
    """
    pct = application_fee_percent(business_type)
    if pct <= 0 or amount_cents <= 0:
        return 0
    fee = (Decimal(amount_cents) * pct / Decimal(100)).to_integral_value(rounding=ROUND_DOWN)
    return int(fee)


# --- Connect onboarding (Standard-аккаунты, OAuth) ------------------------


def _secret() -> str:
    return (
        settings.STRIPE_LIVE_SECRET_KEY
        if settings.STRIPE_LIVE_MODE
        else settings.STRIPE_TEST_SECRET_KEY
    )


def _client():
    stripe.api_key = _secret()
    return stripe


def is_connect_configured() -> bool:
    """Готов ли Connect: есть client_id платформы и секретный ключ Stripe."""
    return bool(getattr(settings, "STRIPE_CONNECT_CLIENT_ID", "")) and bool(_secret())


def oauth_authorize_url(*, state: str, redirect_uri: str) -> str:
    """URL Stripe Connect OAuth для подключения Standard-аккаунта бизнеса.

    Standard онбордится через OAuth (не Account Links): редиректим владельца на
    Stripe, он логинится/создаёт аккаунт и возвращается с ?code= на redirect_uri.
    state — анти-CSRF (проверяем в callback).
    """
    params = {
        "response_type": "code",
        "client_id": getattr(settings, "STRIPE_CONNECT_CLIENT_ID", ""),
        "scope": "read_write",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return "https://connect.stripe.com/oauth/authorize?" + urlencode(params)


def complete_oauth(code: str) -> str:
    """Обменять OAuth-код на id connected-аккаунта (stripe_user_id)."""
    resp = _client().OAuth.token(grant_type="authorization_code", code=code)
    return resp["stripe_user_id"]


def set_connect_status(account_id: str, charges_enabled: bool) -> bool:
    """Вебхук account.updated → Tenant.payments_enabled. Public-схема (Tenant SHARED).

    Возвращает True, если арендатор найден по stripe_connect_id и обновлён/совпал.
    """
    from apps.tenants.models import Tenant

    if not account_id:
        return False
    tenant = Tenant.objects.filter(stripe_connect_id=account_id).first()
    if tenant is None:
        return False
    if tenant.payments_enabled != charges_enabled:
        tenant.payments_enabled = charges_enabled
        tenant.save(update_fields=["payments_enabled", "updated_at"])
    return True


# --- Платежи на connected account (P2.5b/c) -------------------------------


def connected_checkout_session(
    *,
    connect_id: str,
    amount_cents: int,
    product_name: str,
    metadata: dict,
    success_url: str,
    cancel_url: str,
    business_type: str = "",
    currency: str = "eur",
) -> str:
    """Checkout (mode=payment) НА connected account бизнеса — деньги идут ему.

    application_fee удерживаем только при ненулевом проценте типа (вариант A);
    при варианте B (процент 0, текущая модель) комиссия не удерживается — бизнес
    получает 100 %. Возвращает URL оплаты.
    """
    intent_data: dict = {"metadata": dict(metadata)}
    fee = application_fee_cents(amount_cents, business_type)
    if fee > 0:
        intent_data["application_fee_amount"] = fee
    session = _client().checkout.Session.create(
        stripe_account=connect_id,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": currency,
                    "unit_amount": amount_cents,
                    "product_data": {"name": product_name[:250]},
                },
                "quantity": 1,
            }
        ],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata,
        payment_intent_data=intent_data,
    )
    return session["url"]


def refund(*, connect_id: str, payment_intent: str) -> None:
    """Полный возврат платежа на connected account (анти-фрод при отмене)."""
    _client().Refund.create(payment_intent=payment_intent, stripe_account=connect_id)


# --- Рассрочка (R10): мандат + off-session списания -----------------------


def installment_checkout_session(
    *,
    connect_id: str,
    amount_cents: int,
    product_name: str,
    metadata: dict,
    success_url: str,
    cancel_url: str,
    business_type: str = "",
    currency: str = "eur",
) -> str:
    """Checkout первой доли рассрочки НА connected account (R10b).

    Как connected_checkout_session, но создаёт Customer (`customer_creation=always`)
    и помечает PaymentIntent `setup_future_usage=off_session` — сохраняет карту как
    мандат для последующих off-session списаний долей (beat, R10c). Возвращает URL.
    """
    intent_data: dict = {"metadata": dict(metadata), "setup_future_usage": "off_session"}
    fee = application_fee_cents(amount_cents, business_type)
    if fee > 0:
        intent_data["application_fee_amount"] = fee
    session = _client().checkout.Session.create(
        stripe_account=connect_id,
        mode="payment",
        customer_creation="always",
        line_items=[
            {
                "price_data": {
                    "currency": currency,
                    "unit_amount": amount_cents,
                    "product_data": {"name": product_name[:250]},
                },
                "quantity": 1,
            }
        ],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata,
        payment_intent_data=intent_data,
    )
    return session["url"]


def mandate_from_payment_intent(*, connect_id: str, payment_intent: str) -> tuple[str, str]:
    """(customer_id, payment_method_id) сохранённого мандата из PaymentIntent (R10b).

    Нужны для off-session списаний последующих долей. Пустые строки, если Stripe
    не вернул (карта без сохранения)."""
    pi = _client().PaymentIntent.retrieve(payment_intent, stripe_account=connect_id)
    return (pi.get("customer") or "", pi.get("payment_method") or "")


def charge_off_session(
    *,
    connect_id: str,
    customer_id: str,
    payment_method_id: str,
    amount_cents: int,
    metadata: dict,
    currency: str = "eur",
    business_type: str = "",
) -> str:
    """Off-session списание доли рассрочки по сохранённому мандату (R10c).

    Создаёт и подтверждает PaymentIntent сразу (`off_session=True, confirm=True`).
    Возвращает id PaymentIntent при успехе. Бросает stripe.error.CardError при
    отказе / необходимости аутентификации (SCA) — обрабатывает вызывающий (ретрай+
    письмо). Деньги идут бизнесу (на connected account)."""
    intent_data: dict = {
        "amount": amount_cents,
        "currency": currency,
        "customer": customer_id,
        "payment_method": payment_method_id,
        "off_session": True,
        "confirm": True,
        "metadata": dict(metadata),
    }
    fee = application_fee_cents(amount_cents, business_type)
    if fee > 0:
        intent_data["application_fee_amount"] = fee
    pi = _client().PaymentIntent.create(stripe_account=connect_id, **intent_data)
    return pi["id"]
