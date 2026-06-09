# Google Business Profile — настройка адаптера каналов (Track B1)

Авто-публикация активных акций постами в Google Business Profile (Google Posts):
акция → `active` → пост с кнопкой «Mehr erfahren» на страницу акции; акция
завершилась → пост удаляется. Код готов; нужны доступы Google (по аналогии со
Stripe-ключами: всё внешнее настраивает владелец, тесты ключей не требуют).

## 1. Google Cloud (один раз, на платформу)
1. Создать проект в [Google Cloud Console](https://console.cloud.google.com/).
2. **Подать заявку на доступ к Business Profile APIs** — Google одобряет доступ
   по форме (обычно дни–недели): https://developers.google.com/my-business/content/prereqs
   До одобрения API возвращает 403 — это нормально.
3. Включить APIs: «My Business Account Management API», «My Business Business
   Information API» (+ classic «Google My Business API» для localPosts).
4. OAuth consent screen (External) → scope `https://www.googleapis.com/auth/business.manage`.
5. Credentials → Create OAuth client ID (Web application). Сохранить
   **Client ID** и **Client Secret**.

## 2. `.env.prod` на сервере
```dotenv
GOOGLE_OAUTH_CLIENT_ID=....apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-...
```

## 3. Подключение бизнеса (per tenant)
1. Получить **refresh token** владельца GBP-профиля: проще всего через
   [OAuth 2.0 Playground](https://developers.google.com/oauthplayground) — шестерёнка
   → «Use your own OAuth credentials» (Client ID/Secret из п.1.5) → scope
   `https://www.googleapis.com/auth/business.manage` → Authorize (войти Google-
   аккаунтом, владеющим профилем бизнеса) → Exchange authorization code →
   скопировать **Refresh token**.
2. Узнать **location**: `GET https://mybusinessaccountmanagement.googleapis.com/v1/accounts`
   → account name; затем `GET https://mybusinessbusinessinformation.googleapis.com/v1/{account}/locations?readMask=name,title`
   → location id. Для classic localPosts формат: `accounts/{accountId}/locations/{locationId}`.
3. В кабинете бизнеса: **Channels → Google Business Profile → Configuration** →
   вставить `location` и `refresh token` → Save → Enable.

## 4. Проверка
Активируй акцию → в панели публикаций канал GBP должен стать `published`
(пост виден в профиле Google). Заверши акцию → `removed` (пост удалён). Ошибки
видны в `last_error` публикации.

## Заметки
- In-app OAuth-подключение («Connect Google» одной кнопкой) — следующая
  итерация B1; сейчас refresh token вводится вручную (см. roadmap).
- Дальше по списку (то же место, где вводится конфиг): Instagram, и т.п. — Phase 2 P2.9.
