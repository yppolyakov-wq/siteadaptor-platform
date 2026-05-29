# Pattern: Magic-Link Auth (вход покупателя без пароля)

Статус: Phase 1, Sprint 5.
Ссылается из: `phase1-plan-additions.md` §5.3.

## Зачем

Покупателю агрегатора не нужен полноценный аккаунт с паролем — это барьер и
лишняя поверхность атаки (хранение хэшей, reset-флоу, брутфорс). Magic-link:
вводит email → получает одноразовую ссылку → переходит → залогинен. Ни паролей,
ни verification-флоу (сам переход по ссылке = подтверждение email).

Покупатель — это `subscriptions.Customer`, **не** `django.contrib.auth.User`
(те — владельцы бизнесов). Аутентификация покупателя отдельная, лёгкая, на
сессии.

## Токен: в Redis, не в БД

Токен короткоживущий и одноразовый — идеален для Redis (TTL + атомарный
расход). Храним хэш токена, не сам токен.

```python
# apps/aggregator/auth.py
import secrets
import hashlib
from django.core.cache import cache

TOKEN_TTL = 15 * 60   # 15 минут
RATE_TTL = 60 * 60


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_magic_link(email: str, *, portal) -> str | None:
    email = email.strip().lower()

    # rate-limit: не больше 3 ссылок на email в час (анти-спам/анти-энумерация)
    rl = f"ml_rate:{email}"
    if cache.get(rl, 0) >= 3:
        return None
    cache.incr(rl) if cache.get(rl) else cache.set(rl, 1, RATE_TTL)

    token = secrets.token_urlsafe(32)
    cache.set(f"ml_token:{_hash(token)}",
              {"email": email, "portal_id": portal.id},
              TOKEN_TTL)
    return token  # вкладывается в ссылку, письмо шлёт notifications


def consume_magic_link(token: str):
    """Возвращает payload и СРАЗУ инвалидирует токен (одноразовость)."""
    key = f"ml_token:{_hash(token)}"
    payload = cache.get(key)
    if payload is None:
        return None
    cache.delete(key)   # одноразовость: повторный переход не сработает
    return payload
```

## Вьюхи

```python
# POST /auth/request  — форма с email
def request_link(request):
    portal = resolve_portal(request)
    token = issue_magic_link(request.POST["email"], portal=portal)
    # ВСЕГДА один и тот же ответ, есть email в базе или нет (анти-энумерация)
    if token:
        send_magic_link_email.delay(
            dedupe_key=f"magic_link:{_hash(token)}",
            email=request.POST["email"].strip().lower(),
            url=request.build_absolute_uri(f"/auth/verify?t={token}"),
        )
    return render(request, "auth/check_inbox.html")


# GET /auth/verify?t=...
def verify(request):
    payload = consume_magic_link(request.GET.get("t", ""))
    if payload is None:
        return render(request, "auth/link_invalid.html", status=400)

    customer, _ = Customer.objects.get_or_create(
        email=payload["email"],
        defaults={"source": "magic_link"},
    )
    # лёгкая сессия покупателя, отдельно от auth.User
    request.session["customer_id"] = str(customer.id)
    request.session.set_expiry(60 * 60 * 24 * 30)  # 30 дней
    return redirect("aggregator:home")
```

## Безопасность

- **Токен**: `secrets.token_urlsafe(32)` (256 бит энтропии), храним только
  SHA-256-хэш — утечка дампа Redis не даёт валидных ссылок.
- **Одноразовость**: `consume` удаляет ключ до использования.
- **TTL 15 мин** — узкое окно.
- **Анти-энумерация**: ответ «проверьте почту» одинаков независимо от наличия
  email; rate-limit на email и на IP.
- **Не логиним в `auth.User`** — покупатель живёт в сессии (`customer_id`),
  middleware подгружает `request.customer`.
- **HTTPS обязателен** (ссылка = bearer-секрет); письмо с ссылкой — через
  очередь с `dedupe_key`, чтобы не задвоить.

## Опционально: персист-токен в БД

Если нужен аудит «когда логинился» или ссылки должны переживать рестарт Redis —
модель `MagicLinkToken(token_hash, email, portal, expires_at, used_at)` с теми
же правилами. Для Phase 1 Redis достаточно.

## Чек-лист

- [ ] Токен ≥256 бит, в хранилище — только хэш.
- [ ] Одноразовый расход (delete до использования), TTL ≤15 мин.
- [ ] Одинаковый ответ для существующего/несуществующего email.
- [ ] Rate-limit по email и IP.
- [ ] Сессия покупателя отдельна от `auth.User`.
- [ ] Письмо со ссылкой через очередь с dedupe; только HTTPS.
