# AIS-W W4-1 — мастер v4: шаг «Rechtliches & Veröffentlichen» + часы сеткой (2026-11-05)

План — агент ECC `planner` (2026-11-05); ревью `architect` — §9 (вводит ОДНУ миграцию: `Tenant.published_at`). Источник структуры —
`ais-wizard-v4-structure-2026-11-05.md` §3; правки ревью — `ais-modules-directions-assistant-plan` §5.

## 1. «Опубликовать» технически

Состояния «черновик/опубликован» нет: витрину прячет только `PendingStorefrontMiddleware`
(503 «bald online») при `email_pending`; обычная регистрация живёт сразу, без Impressum.
**Решение (минимум):** в `site_config["onboarding"]` += `flow: "v4"` и `published_at`;
middleware прячет витрину гостю при `flow=="v4"` и пустом `published_at` (владелец/сотрудник
видят — превью работает). Текущие тенанты (v3/легаси/демо/быстрый старт) без `flow` — не
затронуты. В v4 `completed` и `times.completed` ставит ТОЛЬКО действие `publish` (= финиш
замера AIS-0). Отдельного ключа в корне не заводим — `normalize` пропускает `onboarding` как есть.

## 2. v4 за флагом

`settings.SETUP_WIZARD_V4` (env, default False; по умолчанию — в W4-6). v4 «прилипает» в
`touch_start` при флаге и нетронутом состоянии; тронутый v3 остаётся v3; `mark_complete`
(быстрый старт/демо/импорт) v4 не даёт и ставит `published_at`, если `flow=="v4"`.
Реестр `SETUP_STEPS_V4` (промежуточный в W4-1): `company` (контакт + часы сеткой) → `offer`
(слайд v3 до W4-2) → `recht` → `done`. Функции onboarding читают шаги через `_steps(state)`;
`get_state` переносит `flow`/`published_at` явно. `HANDLERS` += `recht`; замок
`set(HANDLERS) == STEP_KEYS ∪ STEP_KEYS_V4`. Блокировки: `skip` на `recht` нельзя;
`goto("done")` без публикации → `recht`; `advance` в v4 мастер не завершает.
Маппинг v2→v4 (если понадобится): company→company, texts→recht, offer→offer; `completed` не
понижать, при `completed` ставить `published_at`.

## 3. Шаг `recht`

Поля — общий набор с `LiteBusinessForm` (раздел `recht` + `contact_email`, `tax_choice`,
`ustva.apply_regime`), запись `update_fields` только этих полей. Регулируемые типы
(`handwerker`, `werkstatt`, `friseur` — Handwerk Anlage A): показать `chamber` и `profession`,
в `impressum_text` строка «Berufsrechtliche Regelung: Handwerksordnung (HwO)» при заполненной
палате. Превью текста Impressum (live) + iframe `/impressum/`; Datenschutz — ссылка.
Кнопка «Website veröffentlichen»: гейт `readiness` базовых must (contact/impressum/email),
**fail-closed** (`is_done is not True` блокирует), сервер перепроверяет при POST, список
недостающего со ссылками; право — как у правовых экранов; в Telegram-сессии правовые поля
заперты (SEC-A11) — «nur per E-Mail-Login».

## 4. Часы сеткой в `company`

Виджет сетки вынести из `lite_business.html`/`settings.html` в `tenant/_hours_grid.html`
(замок разметки до выноса), подключить в шаг; сентинел `oh_present` (нет поля — часы не
трогать, W0). Свободный текст — «Hinweis (z. B. Feiertage)». Новый
`openinghours.parse_text` (правила: «Mo–Fr 8–18», «Sa 8:00-13:00», «geschlossen»; два интервала
→ день пустой с подсказкой) — только предзаполнение сетки при пустых структурных часах.

## 5. Замки до кода

v3 без изменений · свойства v4 (прилипание, быстрый старт/демо мимо, перенос ключей, без
понижения) · publish (отказ без Impressum/контактов, метки после, идемпотентность) · middleware
(503 гостю до публикации, 200 владельцу, v3 200) · presence-guard правовых полей и часов,
чужие ключи site_config целы, TG не пишет правовое · регулируемые типы и строка HwO ·
`parse_text` таблицей · HANDLERS ↔ ключи · i18n.

## 6. Риски

`save_state` пишет весь `site_config` — для `publish`/flow писать только `onboarding` под
`select_for_update` (паттерн `page_settings.write`) · скрытие только CSS, без `required` в
скрытой части · ветка middleware последней в условии · проверить, не пишет ли провижининг
`onboarding` раньше `touch_start` · выключение флага оставляет v4-тенантов на v4 (осознанно).

## 7. ECC-прогоны

Скиллы: django-patterns, django-tdd, django-security, accessibility, e2e-testing.
Сразу после плана — `architect`. Перед мержем — `django-reviewer`, `security-reviewer`
(publish/права/TG/middleware), `silent-failure-hunter` (fail-open vs fail-closed),
`a11y-architect` (сетка часов, disabled-кнопка со списком, live-превью), `e2e-runner`
Playwright 390/1440 (регистрация → company → recht → блок → заполнение → publish → витрина 503→200;
отдельно handwerker с палатой).

## 8. Вопросы владельцу

1. Новые сайты v4 не видны гостям до «Website veröffentlichen» (сегодня видны сразу после
   регистрации). Рекомендация — да: так Impressum есть до выхода в сеть.
2. Палата/профессия у регулируемых типов: блокировать публикацию без них или мягкое
   предупреждение? Рекомендация — предупреждение (есть Anlage B без Meisterpflicht).

## 9. Ревью `architect` (2026-11-05) — правки, имеющие приоритет над §1–§8

1. **CRITICAL — хранение.** `published_at` в `site_config["onboarding"]` теряется: ~30 писателей
   (Studio Save, `site_view`, promotions, booking, stays, demo, sitetemplates, cscart, platform_bot,
   telegram/notify, transition_rules, status_labels) пишут ВЕСЬ `site_config` из снимка начала
   запроса — старая копия `onboarding` затрёт метку, сайт исчезнет у гостей. **Решение: SHARED-поле
   `Tenant.published_at` (DateTime, null) — миграция `tenants/00xx`, бэкфилл существующих
   `published_at = created_at`.** Публикация — одно `update()`; middleware и каталог читают поле.
2. **HIGH — каталог города и выходы наружу.** `aggregator/visibility.listable` и
   `withheld_schemas()` должны учитывать «не опубликован»; при публикации — `apply_visibility`
   (как при подтверждении почты, T-8.6). Проверить фиды Merchant/метапоиска, MCP, publishing,
   ссылки в письмах.
3. **HIGH — хелперы онбординга на v3-реестре:** `_remap_key`, `_clean_times`/`_TIME_KEYS`,
   `_ordered`, `non_final`/`_FINAL`, `visible_keys`, `progress`, `steps_with_status`,
   `setup_checklist`, проверка «нетронутого» в `dashboard` (`STEP_KEYS[0]`) — все получают реестр
   из состояния (`_steps(state)`), по замку на каждый.
4. **HIGH — окно до `touch_start`:** признак v4 ставить при создании тенанта (`create_business`
   при включённом флаге: `published_at=None` + `flow`), `touch_start` — только метка времени.
5. **MEDIUM — Telegram:** v4-владелец из Mini App не может опубликовать (правовое заперто) →
   карточка «Website noch nicht online — per E-Mail-Login veröffentlichen» на `lite_home`; быстрый
   старт/бот/демо/импорт — опубликованы сразу (замок).
6. **MEDIUM — middleware/кэш:** проверка поля ДО `has_cabinet_access` (тот ходит в БД); 503 с
   `Cache-Control: no-store`, свой текст «noch nicht veröffentlicht»; после публикации
   `bump_storefront_cache`. Общий кэш P0-1 безопасен (декоратор вьюхи работает после middleware).
7. **MEDIUM — гейт:** проверка внутри блокирующей транзакции с перечитыванием тенанта; публикация
   после записи правовых полей, обновить `request.tenant` в памяти; повтор не перезаписывает время.
8. **Не хватало:** пункт «Website veröffentlichen» в `setup_checklist` и на главной кабинета,
   бейдж «Offline» в шапке, замок «выключение флага не прячет опубликованных», проверка демо-китов
   при включённом флаге.
