# Meta соц-постинг — настройка адаптеров каналов (M23a)

Авто-публикация активных акций в **Facebook** и **Instagram** через Meta Graph
API: акция → `active` → пост на странице FB / в профиле IG со ссылкой на
страницу акции; акция завершилась → пост снимается (FB удаляется; **IG — no-op**,
Graph API не умеет удалять органические посты — пост остаётся в ленте). Код
готов; нужны доступы Meta (как со Stripe/GBP: всё внешнее настраивает владелец,
тесты ключей не требуют).

## 1. Meta (один раз, на платформу)
1. Создать приложение в [Meta for Developers](https://developers.facebook.com/apps/)
   (тип «Business»).
2. Добавить продукты **Facebook Login** и **Instagram Graph API**.
3. Запросить разрешения (App Review): `pages_manage_posts`, `pages_read_engagement`,
   `instagram_basic`, `instagram_content_publish`, `business_management`. До
   одобрения работает только в режиме разработки на тестовых страницах.
4. Версия Graph API фиксируется в `META_GRAPH_API_VERSION` (default `v21.0`).

## 2. `.env.prod` на сервере (опционально)
```dotenv
# по умолчанию v21.0 — менять только при апгрейде версии API
META_GRAPH_API_VERSION=v21.0
```
App ID/Secret платформы тут не нужны: постим **page access token**'ом, который
вводится per-tenant (см. ниже). OAuth-«Connect»-кнопка — следующая итерация.

## 3. Подключение бизнеса (per tenant)

### Facebook
1. Узнать **Page ID**: страница FB → About → внизу «Page ID» (или через
   `GET /me/accounts` авторизованным пользователем).
2. Получить **долгоживущий page access token** (60 дн. или бессрочный, если
   выведен из never-expiring user token) — через
   [Graph API Explorer](https://developers.facebook.com/tools/explorer/):
   выбрать приложение → права из п.1.3 → Generate Access Token → обменять на
   long-lived (`GET /oauth/access_token?grant_type=fb_exchange_token`) →
   `GET /me/accounts` вернёт `access_token` страницы.
3. В кабинете: **Channels → Facebook → Configuration** → вставить `Page ID` и
   `Page access token` → Save → Enable.

### Instagram
1. IG-аккаунт должен быть **Business/Creator** и привязан к FB-странице.
2. Узнать **Instagram Business account ID**:
   `GET /{page-id}?fields=instagram_business_account`.
3. Токен — тот же page access token, что у связанной FB-страницы.
4. В кабинете: **Channels → Instagram → Configuration** → вставить
   `Instagram Business account ID` и `Access token` → Save → Enable.
5. **Важно:** Instagram требует изображение — у акции (или связанного товара)
   должно быть фото, иначе публикация уходит в `failed` («benötigt ein Bild»).

## 4. Проверка
Активируй акцию → в панели публикаций каналы Facebook/Instagram должны стать
`published` (пост виден в ленте). Заверши акцию → FB `removed` (пост удалён),
IG `removed` (пост остаётся — ограничение Graph API). Ошибки видны в `last_error`
публикации.

## Заметки
- **Привязка ссылки:** FB-пост со ссылкой использует `link` (без фото) или
  ссылку в тексте (фото-пост через `/photos`); IG-подпись несёт URL текстом
  (кликабельных ссылок в подписи IG нет).
- In-app OAuth-подключение одной кнопкой — следующая итерация (как и у GBP).

## M23b — каталог-фид (Meta Commerce / Google Merchant)
Витрина бизнеса отдаёт product-feed по адресу **`https://<субдомен>/feed/google.xml`**
(RSS 2.0 с namespace `g:`, его принимают и Google Merchant Center, и Meta Commerce
Manager). Активные товары; варианты (R1) — отдельными `item` с общим
`g:item_group_id`; наличие — из остатка (R3); цена — base/variant.

Подключение (раз на бизнес):
- **Google Merchant Center** → Products → Feeds → *Scheduled fetch* → вставить URL.
- **Meta Commerce Manager** → Catalog → Data sources → *Scheduled feed* → тот же URL.

Фид публичный (как `sitemap.xml`), ключей не требует. Грядущее: GTIN/MPN-маппинг,
`unit_pricing_measure` из Grundpreis (R2).

## Дальше M23
Pinterest + Telegram-канал (постинг, как FB/IG) → платная реклама
`Campaign`/`AdInsight` (M23c). Telegram-бот для бизнесов (свой бот на тенанта +
боты порталов, Mini App) — отдельный модуль. См. `docs/master-plan.md §M23`.
