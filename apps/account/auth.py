"""Magic-link вход клиента на витрине бизнеса (per-tenant ЛК, CA1).

Зеркало apps.aggregator.auth, но личность — `promotions.Customer` в схеме
бизнеса (НЕ PortalUser агрегатора и НЕ auth.User владельца). Без пароля: email →
одноразовая ссылка (Redis-токен SHA-256, TTL 15 мин, расход до использования) →
переход = вход. Сессия лёгкая (account_customer_id). Анти-энумерация и
rate-limit — в issue/вьюхах.
"""

import hashlib
import secrets

from django.core.cache import cache

from apps.core import ratelimit
from apps.promotions.models import Customer

TOKEN_TTL = 15 * 60  # сек; ссылка — bearer-секрет, узкое окно
EMAIL_RL_LIMIT = 3  # ссылок на email в час (анти-спам/энумерация)
EMAIL_RL_WINDOW = 3600
SESSION_KEY = "account_customer_id"
SESSION_AGE = 60 * 60 * 24 * 30  # 30 дней


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_magic_link(email: str) -> str | None:
    """Одноразовый токен (или None при превышении лимита на email)."""
    email = email.strip().lower()
    if ratelimit.hit("acct_ml", email, limit=EMAIL_RL_LIMIT, window=EMAIL_RL_WINDOW):
        return None
    token = secrets.token_urlsafe(32)
    cache.set(f"acct_ml_token:{_hash(token)}", {"email": email}, TOKEN_TTL)
    return token


def consume_magic_link(token: str) -> dict | None:
    """Payload токена; ключ удаляется ДО использования (одноразовость)."""
    key = f"acct_ml_token:{_hash(token)}"
    payload = cache.get(key)
    if payload is None:
        return None
    cache.delete(key)
    return payload


def login(request, email: str) -> Customer:
    """Найти/создать Customer в схеме бизнеса и положить в сессию.

    Переход по ссылке = подтверждение email, поэтому get_or_create безопасно
    (created_source=manual — без новой choice/миграции)."""
    email = email.strip().lower()
    customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
    if customer is None:
        customer = Customer.objects.create(
            name="", email=email, created_source=Customer.SOURCE_MANUAL
        )
    request.session[SESSION_KEY] = str(customer.pk)
    request.session.set_expiry(SESSION_AGE)
    return customer


def logout(request) -> None:
    request.session.pop(SESSION_KEY, None)


def current_customer(request):
    """Customer из сессии (или None). Кэшируется на объекте запроса."""
    if hasattr(request, "_account_customer"):
        return request._account_customer
    customer = None
    pk = request.session.get(SESSION_KEY) if hasattr(request, "session") else None
    if pk:
        customer = Customer.objects.filter(pk=pk).first()
    request._account_customer = customer
    return customer
