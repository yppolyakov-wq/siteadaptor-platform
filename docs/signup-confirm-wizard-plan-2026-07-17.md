# AB5.1 + AB6.10: регистрация с подтверждением почты + мастер по порядку владельца

> Создан 2026-07-17 по запросу владельца: «Проработай страницу регистрации ещё раз…
> регистрация должна быть с подтверждением почты (в идеале бизнеса). Далее:
> язык → товар(ы) → настройка страницы товара → страница категории → главная →
> о компании → текстовые страницы → оплата/доставка если есть. Также разработать
> шаблоны этих страниц». ID: **AB5.1** (double-opt-in регистрации),
> **AB6.10** (порядок слайдов + слайды Produktseite/Über uns + шаблоны страниц).
> Ветка: `claude/registration-email-confirmation-698nwb`.

## 1. AB5.1 — double-opt-in регистрации бизнеса

### Текущий флоу (разведка 2026-07-17)
`/registrieren/` (public) → `BusinessSignupView.post` → `start_business_provisioning`
СРАЗУ создаёт `Tenant(PENDING)` + `Domain` и ставит Celery `provision_business`
(схема + User(хэш) + Membership + письмо «bereit»). Подтверждения почты НЕТ;
бот может плодить тенанты/Domain-записи (тот же класс риска, что T-5 LE-квота).
`allauth.account` — SHARED (таблицы только в public), User — TENANT ⇒ вязать
подтверждение на allauth `EmailAddress` НЕЛЬЗЯ (pk-коллизии между схемами —
причина SessionSchemaGuard). Делаем собственный механизм ДО создания тенанта.

### Целевой флоу
1. POST `/registrieren/` (форма без изменений) → валидация → **`SignupRequest`**
   (public-модель: токен + payload + `password_hash`, тенант НЕ создаётся) →
   письмо со ссылкой подтверждения → страница «Bitte E-Mail bestätigen»
   (`signup_confirm_sent.html`: адрес, resend-кнопка, спам-подсказка).
2. GET `/registrieren/bestaetigen/<token>/` → проверки (токен/срок 72ч/slug ещё
   свободен) → `start_business_provisioning(password_hash=…)` → редирект на
   существующую `signup-waiting` (провижининг как раньше). Идемпотентно:
   повторный клик по подтверждённому токену → редирект на waiting его тенанта.
3. POST `/registrieren/erneut-senden/` — переотправка письма (по токену,
   rate-limit).

### Решения
- **Модель `SignupRequest`** (apps.tenants, SHARED, миграция `tenants/0026`):
  token (уникальный, `secrets.token_urlsafe`), email, password_hash,
  business_name, slug, business_type, city, partner_code, locale,
  created_at, confirmed_at, tenant FK (SET_NULL). Хранить пароль только хэшем;
  токен в URL — случайный (не signed-payload: подпись читаема base64, пароль/хэш
  в URL недопустим). Просроченные (>7 дней) чистятся оппортунистически при
  новом POST (без beat).
- **`start_business_provisioning`** получает опц. `password_hash=` (существующие
  вызовы с `password=` не меняются).
- **Slug не резервируется** pending-заявкой; гонка решается на confirm
  (занят → страница ошибки с CTA заново зарегистрироваться). Дубль email в
  pending → старая заявка заменяется новой (новый токен).
- **Письмо**: `templates/emails/signup_confirm{_subject}.txt`, немецкие msgid
  (`{% trans %}`), рендер с `translation.override(signup.locale)` (язык
  публичной страницы на момент POST); переводы en/tr/ru/uk — в .po.
  Отправка синхронная `send_mail` (public-схема, notify() тенант-скоупный).
  Абсолютный URL — от public-хоста (`request.build_absolute_uri`).
- **Флаг `SIGNUP_EMAIL_CONFIRMATION`** (env, default **True**). False → прежний
  прямой флоу (страховка, пока Resend-ключ не прописан в проде).
  Console-бэкенд (dev/misconfig): confirm-ссылка показывается прямо на
  странице «проверьте почту» (регистрация не брикается; помечено в шаблоне).
- **Анти-бот**: honeypot-поле `website` (паттерн newsletter_signup) → фейковый
  успех без записи/письма; rate-limit `core.ratelimit.hit` — signup 5/ч/IP,
  resend 3/10мин/токен.
- Админка unfold: `SignupRequest` read-only список (диагностика доставки).

### Тесты (`apps/tenants/tests/test_signup_confirmation.py`)
POST создаёт заявку без Tenant + письмо с токеном · confirm создаёт
Tenant+Domain и редиректит на waiting · повторный confirm идемпотентен ·
просроченный/битый токен → страница ошибки без тенанта · slug занят между
POST и confirm → ошибка · resend шлёт второе письмо, rate-limit · honeypot →
без записи · флаг OFF → прежний прямой флоу (характеризация). Существующие
test_async_signup (сервисный слой) не трогаем.

## 2. AB6.10 — мастер: порядок владельца + 2 новых слайда + шаблоны страниц

### Порядок (запрос 2026-07-17: «язык → товар → стр. товара → категория →
главная → о компании → тексты → оплата в конце»)
`business(gate)` → `start` → **`language`** (поднят ДО company) → `company` →
`stil` → `menu` → `offer` → **`detail` НОВЫЙ** → `category` → `home` →
**`about` НОВЫЙ** → `texts` → **`payment` (перенесён В КОНЕЦ)** → `done`.
Реестр = единый источник порядка; state v2 хранит ключи ⇒ перестановка
безопасна (goto/advance идут по visible_keys). Замок HANDLERS==STEP_KEYS
обновляется.

### Слайд `detail` «Produktseite» (настройка страницы товара; v1 по решению
владельца 2026-07-11: стиль карточек + скрытие секций)
- Гейт: primary-модуль ∈ _OFFER_KINDS (catalog/booking/stays/events).
- (а) **стиль карточек** — 3 пресета `site_defaults` (Klar 0/0/'' ·
  Weich r16+shadow · Karte r12+shadow+padding12), мини-мокапы, live-превью;
- (б) **секции детали** — чекбоксы hideable-секций реестра
  `detail_sections.sections_for(module)` → `cfg[<module>_detail]={"hidden":[…]}`
  (та же семантика, что page_inspector; normalize уже поддерживает);
- превью iframe — на деталь ПЕРВОЙ сущности (контекст `preview_url`,
  фолбэк `/`).

### Слайд `about` «Über uns» (страница о компании + ШАБЛОНЫ)
- Переносит about_title/about_text (+i18n-панели) из `texts`;
- **шаблоны страницы**: 4 пресета блоков хоста `page_blocks["info"]`
  (рендерится на витринной `/ueber-uns/`): «Nur Text» (очистить) ·
  «Text + Bild» · «Geschichte» (text intro+quote) · «Vertrauen» (text+button),
  данные из `CBLOCK_DEMO_DATA`, id — `pb-about-<preset>-<n>`; повторное
  применение пресета заменяет ранее посеянные пресетом блоки (свои блоки
  владельца не трогаем: только id с нашим префиксом);
- check: about-контент; превью iframe → `/ueber-uns/`.
- `texts` слим-нится до «Texte & Recht» без about (Impressum + ссылки), check —
  только LegalDoc/Impressum.

### Шаблоны остальных страниц (инвентаризация «что уже есть»)
Главная — галерея `sitetemplates.TEMPLATES` (слайд `stil`) ✅ ·
категория — `_CATALOG_PRESET_CARDS` (слайд `category`) ✅ · текстовые/правовые —
LegalDoc-фолбэки + `legal-docs` ✅ · оплата/доставка — функциональный экран
W4-3 (решение 0d: без шаблонов) ✅. Новое в этом инкременте: страница товара
(слайд `detail`) + «О компании» (слайд `about`).

## 3. Риски
- normalize дропает неизвестные top-level ключи — НОВЫХ ключей не вводим
  (site_defaults / <module>_detail / page_blocks уже в normalize).
- Перестановка шагов: state с step из старой позиции остаётся валидным ключом.
- Письмо в проде: пока RESEND_API_KEY не прописан — console-бэкенд ⇒ на
  странице подтверждения виден прямой линк (регистрация работает, но без
  реальной проверки). ОПС-блокер прежний (Stage 0, Resend).
- `_check_texts` делится на `about`/`texts` — паритет completeness() не
  трогаем (это отдельный фасад из 5 пунктов).

## 4. Инкременты
1. AB5.1 модель+флоу+письма+тесты (миграция `tenants/0026` ⚠️ деплой).
2. AB6.10a порядок + слайд `detail` + замки.
3. AB6.10b слайд `about` (+шаблоны) + слим `texts` + замки.
4. Доки: build-log, CLAUDE.md §3, task-catalog (AB5.1/AB6.10).
