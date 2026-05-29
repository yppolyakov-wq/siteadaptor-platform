# Pattern: Outgoing Webhooks с HMAC-подписью

Статус: Phase 1, Sprint 1 (scaffold: модели+admin), отправка — Phase 2.
Ссылается из: `phase1-plan-additions.md` §1.4.

## Зачем

Арендатор хочет получать события платформы (`promotion.published`,
`reservation.confirmed`) в свою систему. Webhook = HTTP POST на его URL.
Получатель должен (1) убедиться, что запрос реально от нас (HMAC-подпись), и
(2) не обработать его дважды (idempotency key). Доставка ненадёжна → нужны
ретраи с backoff и журнал попыток.

В Sprint 1 ставим **только модели и admin** (нельзя backfill подписки/секреты
постфактум красиво), сама отправка — Phase 2.

## Модели (SHARED-схема)

```python
# apps/integrations/webhooks/models.py
import secrets
from django.db import models
from apps.core.models import TimestampedModel


class OutgoingWebhook(TimestampedModel):
    tenant_schema = models.CharField(max_length=100, db_index=True)
    url = models.URLField()
    # секрет для HMAC; генерится при создании, показывается один раз
    secret = models.CharField(max_length=64, default=lambda: secrets.token_hex(32))
    event_types = models.JSONField(default=list)  # ['promotion.published', ...]
    is_active = models.BooleanField(default=True)


class WebhookDelivery(TimestampedModel):
    webhook = models.ForeignKey(OutgoingWebhook, on_delete=models.CASCADE,
                                related_name="deliveries")
    event_type = models.CharField(max_length=100, db_index=True)
    # idempotency-ключ события, попадает в заголовок и не меняется между ретраями
    event_id = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default="pending")  # pending|delivered|failed
    attempts = models.IntegerField(default=0)
    response_code = models.IntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["status", "next_retry_at"])]
```

## Подпись (Phase 2, отправка)

Подписываем сырое тело + таймстамп — схема в стиле Stripe.

```python
import hashlib
import hmac
import json
import time


def sign(secret: str, body: bytes, ts: int) -> str:
    msg = f"{ts}.".encode() + body
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def deliver(delivery: WebhookDelivery):
    wh = delivery.webhook
    body = json.dumps(delivery.payload, separators=(",", ":")).encode()
    ts = int(time.time())
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Id": delivery.event_id,        # idempotency для получателя
        "X-Webhook-Event": delivery.event_type,
        "X-Webhook-Timestamp": str(ts),
        "X-Webhook-Signature": f"v1={sign(wh.secret, body, ts)}",
    }
    resp = httpx.post(wh.url, content=body, headers=headers, timeout=10)
    resp.raise_for_status()
```

## Верификация (для документации получателю)

```python
expected = "v1=" + hmac.new(secret, f"{ts}.".encode()+raw_body,
                            hashlib.sha256).hexdigest()
assert hmac.compare_digest(expected, header_signature)   # constant-time
assert abs(time.time() - int(ts)) < 300                  # анти-replay, 5 мин
# обработать только если X-Webhook-Id ещё не встречался (idempotency)
```

## Доставка и ретраи (Phase 2)

- Отправка — Celery-задача `idempotent_task(dedupe_key=f"wh:{delivery.id}")`.
- Backoff на `5xx`/timeout: 1м → 5м → 30м → 2ч → 6ч (до ~24ч), затем `failed`.
- `4xx` (кроме 429) — перманентная ошибка, не ретраить.
- Beat-задача поднимает `status=pending|failed` с наступившим `next_retry_at`.
- Это та же модель надёжной доставки, что у уведомлений (см. §6.5).

## Безопасность

- **Constant-time** сравнение подписи (`hmac.compare_digest`).
- **Таймстамп в подписи** + окно 5 мин против replay.
- **Подписываем сырые байты тела**, не пересериализованный объект (иначе
  пробел/порядок ключей ломают подпись).
- `secret` показываем владельцу **один раз** при создании; в API/логах — маска.
- Только **HTTPS** URL; запретить приватные/loopback адреса (SSRF).

## Чек-лист

- [ ] `OutgoingWebhook` + `WebhookDelivery` в SHARED-схеме (Sprint 1).
- [ ] HMAC-SHA256 по `"{ts}." + raw_body`, заголовок `v1=...`.
- [ ] `X-Webhook-Id` = idempotency-ключ, неизменен между ретраями.
- [ ] Backoff на 5xx/timeout, no-retry на 4xx; журнал в `WebhookDelivery`.
- [ ] Только HTTPS, блок приватных адресов (SSRF), секрет — один раз.
