"""Magic-link вход клиента на порталах (P2.3a).

По docs/references/patterns/magic-link-auth.md: покупателю не нужен пароль —
email → одноразовая ссылка → переход = вход (и подтверждение email). Токен
живёт в Redis (храним SHA-256-хэш, TTL 15 мин, расход до использования —
одноразовость). Сессия лёгкая (portal_user_id), отдельно от auth.User
(владельцы бизнесов). Анти-энумерация и rate-limit — в вьюхах/issue.
"""

import hashlib
import secrets

from django.core.cache import cache
from django.utils import timezone

from apps.core import ratelimit

from .models import PortalUser

TOKEN_TTL = 15 * 60  # сек; узкое окно — ссылка является bearer-секретом
EMAIL_RL_LIMIT = 3  # ссылок на email
EMAIL_RL_WINDOW = 3600
SESSION_KEY = "portal_user_id"
SESSION_AGE = 60 * 60 * 24 * 30  # 30 дней


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_magic_link(email: str) -> str | None:
    """Выпустить одноразовый токен (или None при превышении лимита на email)."""
    email = email.strip().lower()
    if ratelimit.hit("magiclink", email, limit=EMAIL_RL_LIMIT, window=EMAIL_RL_WINDOW):
        return None
    token = secrets.token_urlsafe(32)
    cache.set(f"ml_token:{_hash(token)}", {"email": email}, TOKEN_TTL)
    return token


def consume_magic_link(token: str) -> dict | None:
    """Payload токена; ключ удаляется ДО использования (одноразовость)."""
    key = f"ml_token:{_hash(token)}"
    payload = cache.get(key)
    if payload is None:
        return None
    cache.delete(key)
    return payload


def login(request, email: str) -> PortalUser:
    """Создать/найти PortalUser и положить в сессию (после consume токена)."""
    user, _created = PortalUser.objects.get_or_create(email=email.strip().lower())
    user.last_login_at = timezone.now()
    user.save(update_fields=["last_login_at", "updated_at"])
    request.session[SESSION_KEY] = user.pk
    request.session.set_expiry(SESSION_AGE)
    return user


def logout(request) -> None:
    request.session.pop(SESSION_KEY, None)


def current_portal_user(request) -> PortalUser | None:
    """PortalUser из сессии (или None). Кэшируется на объекте запроса."""
    if hasattr(request, "_portal_user"):
        return request._portal_user
    user = None
    pk = request.session.get(SESSION_KEY) if hasattr(request, "session") else None
    if pk:
        user = PortalUser.objects.filter(pk=pk, is_active=True).first()
    request._portal_user = user
    return user
