# Нагрузочные тесты (Hardening H6)

Инвариант anti-oversell под конкуренцией покрыт в CI
(`apps/promotions/tests/test_concurrency.py` — потоки против Postgres).
Здесь — прогон на реальном железе через [k6](https://k6.io): полная цепочка
Caddy/gunicorn/Postgres/Redis и реальные latency.

## anti_oversell.js

Толпа виртуальных пользователей бронирует одну акцию через публичную форму
(GET страницы → CSRF → POST), как браузер.

```bash
# на сервере (или с ноутбука против staging)
# 1) тестовая акция: создать в кабинете акцию с остатком, скопировать uuid
# 2) прогон против внутреннего порта gunicorn (минуя Caddy):
k6 run \
  -e BASE_URL=http://127.0.0.1:8000 \
  -e HOST_HEADER=<shop>.siteadaptor.de \
  -e PROMO_ID=<uuid акции> \
  -e VUS=50 -e ITERATIONS=500 \
  scripts/load/anti_oversell.js
```

**Почему мимо Caddy:** скрипт шлёт рандомный `X-Forwarded-For`, чтобы per-IP
rate-limit (H8) не схлопнул прогон с одной машины. Gunicorn заголовку верит,
Caddy на проде его перезаписывает — против публичного URL прогон упрётся в
лимит (что само по себе подтверждает работу H8).

## Проверка результата (DoD: 0 перепродаж)

После прогона в `manage.py shell` тенанта:

```python
from django_tenants.utils import schema_context
with schema_context("<schema>"):
    from apps.promotions.models import Promotion, Reservation
    from django.db.models import Sum
    p = Promotion.objects.get(pk="<uuid>")
    sold = Reservation.objects.filter(promotion=p).aggregate(n=Sum("quantity"))["n"] or 0
    print("остаток:", p.available_quantity, "продано:", sold)
    assert p.available_quantity >= 0 and sold <= <начальный остаток>
```

Метрики k6 (latency p95, ошибки) — в stdout прогона; порог `p(95)<1500ms`
зашит в скрипт (`thresholds`). Чистка после прогона: удалить тестовую акцию —
брони и клиенты `lt-*@example.com` уйдут каскадом (или DSGVO-очисткой
по retention).
