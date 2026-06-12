# Stripe — настройка биллинга (.env.prod)

Что нужно прописать, чтобы заработали оплата (Checkout), Customer Portal и
вебхуки Sprint 5. Сначала в **Test mode** (карта `4242 4242 4242 4242`), потом
аналогично Live.

Код читает переменные: `STRIPE_LIVE_MODE`, `STRIPE_TEST_PUBLIC_KEY`,
`STRIPE_TEST_SECRET_KEY`, `STRIPE_LIVE_SECRET_KEY`, `STRIPE_PRICE_ID`,
`STRIPE_WEBHOOK_SECRET` (см. `config/settings/base.py`).

## 1. В Stripe Dashboard (Test mode включён)
1. **Product + Price:** Products → Add product → название «siteadaptor Standard»,
   цена **€39.00**, **Recurring / monthly** → Save. Скопировать **Price ID**
   (`price_...`).
2. **API-ключи:** Developers → API keys → скопировать **Publishable key**
   (`pk_test_...`) и **Secret key** (`sk_test_...`).
3. **Webhook:** Developers → Webhooks → Add endpoint:
   - Endpoint URL: `https://siteadaptor.de/stripe/webhook/`
   - События: `checkout.session.completed`, `invoice.payment_failed`,
     `customer.subscription.updated`, `customer.subscription.deleted`
   - Add endpoint → скопировать **Signing secret** (`whsec_...`).

## 2. В `.env.prod` на сервере (НЕ коммитить)
```dotenv
STRIPE_LIVE_MODE=False
STRIPE_TEST_PUBLIC_KEY=pk_test_...
STRIPE_TEST_SECRET_KEY=sk_test_...
STRIPE_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

## 3. Проверка после деплоя
1. На субдомене бизнеса войти → `/dashboard/billing/` → «Activate subscription —
   €39/mo» → Stripe Checkout → тестовая карта `4242 4242 4242 4242`, любая будущая
   дата и CVC → оплатить.
2. Stripe шлёт `checkout.session.completed` на вебхук → тенант становится
   `active` (проверь статус на странице биллинга; доставку вебхука видно в Stripe
   → Webhooks → Recent deliveries).
3. «Manage subscription» → Customer Portal (карта/инвойсы/отмена).

## 4. Featured-продвижение листинга (P2.4b)
Самообслуживание: владелец активной акции из кабинета (`/promotions/<pk>/feature/`)
покупает закрепление листинга наверху агрегатора/порталов («★ Empfohlen»).

- **Отдельной настройки Stripe не требует** — суммы передаём inline `price_data`
  (никаких новых Product/Price в дашборде). Достаточно тех же ключей Stripe и
  вебхука, что и для подписки. Кнопка покупки появляется, когда задан
  `STRIPE_TEST_SECRET_KEY` (или live-ключ при `STRIPE_LIVE_MODE=True`).
- **Тот же вебхук** `checkout.session.completed`: события различаем по
  `metadata.kind` (`featured` → `featured_until` листинга; иначе — подписка).
  Доп. событий в Stripe включать не нужно.
- **Цены/сроки** — в коде (`apps/billing/featured.py`), дефолт 7/14/30 дн. =
  9/15/25 €. Оверрайд в `.env.prod` (формат «дни=центы»):
  ```dotenv
  BILLING_FEATURED_PRICES=7=900,14=1500,30=2500
  ```
- Проверка: активная акция → «Bewerben» → Checkout (тестовая карта
  `4242 4242 4242 4242`) → после оплаты листинг закреплён наверху на городской
  странице (бейдж «★ Empfohlen»). Повторная покупка продлевает срок.

## Заметки
- Вебхук-эндпоинт живёт на основном домене (public-схема), не на субдомене:
  `https://siteadaptor.de/stripe/webhook/`. Должен быть доступен по HTTPS (Caddy).
- **Live:** создать Product/Price в Live mode, затем `STRIPE_LIVE_MODE=True`,
  `STRIPE_LIVE_SECRET_KEY=sk_live_...`, live `STRIPE_PRICE_ID`, live
  `STRIPE_WEBHOOK_SECRET`.
- Идемпотентность: повторные вебхуки с тем же `event.id` игнорируются; смена
  статуса идёт через SubscriptionSM (повтор статуса — no-op).
