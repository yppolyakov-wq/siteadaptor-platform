# Точка входа следующей сессии (обновлён 2026-07-02)

> Отвечаем **по-русски**. Это ТЗ-хэндофф: с чего начать, что уже сделано, что недостаёт,
> какие условия соблюдать. SOURCE OF TRUTH порядка работ — очередь волн (см. §3).

## 0. Условия работы (обязательно, из CLAUDE.md §5)

- **Docs до кода.** Перед каждым нетривиальным инкрементом — план-док/разведка ДО кода.
  Крупные доработки — план-доком; источник правды — соответствующий план в `docs/`.
- **Рабочий цикл по подзадачам.** Крупную задачу дробим, разбивку показываем владельцу.
  Одна подзадача = один инкремент: ветка `claude/<кратко>` → локальный гейт → push →
  **CI на git зелёный** → чекпоинт с владельцем → следующая. **FF-мерж в `main`** после
  зелёного CI (`git push origin <sha>:main`; main не защищён). После мержа с миграциями —
  деплой на сервере (владелец): `git pull origin main && ./scripts/deploy.sh single`.
- **Батч-режим.** Связные зависимые шаги пишем подряд, каждый гейтим ЛОКАЛЬНО
  (`ruff check` + `ruff format --check` + `pytest` затронутых модулей), коммитим отдельно,
  пушим стопкой → один прогон CI на верхушке. На ветке `concurrency: cancel-in-progress`.
- **Скорость pytest: `--reuse-db`** (69с→1.1с). ⚠️ При изменении **миграций** — `--create-db`
  (иначе стале-схема даст ложные падения).
- **Git commit — только `git commit -F -` (heredoc)**, НЕ `-m` с бэктиками (бэктики в
  двойных кавычках → command substitution). Секреты не коммитить.
- **Идентификатор модели НЕ светим** в коммитах/PR/коде/артефактах — только в чате.
- Коммиты завершаем: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` +
  `Claude-Session: …`.
- Смена статусов — только через FSM `.apply()`; внешние действия (письма/публикации) —
  через Celery + `idempotent_task`/`dedupe_key`. Новые TENANT-приложения — в `base.py`
  TENANT_APPS. Billing — SHARED.
- UX-принцип: для потребителя максимально просто, без навязчивости (бронь без аккаунта,
  one-click отписка, Double-Opt-In по UWG §7 до маркетинга, без трекинг-куки на витрине).

## 1. Состояние git / deploy

- **`origin/main` = `d92fec4`** — Волна U-A (UA1–UA4) и Волна L (L1/L2/L3-модель/L3c) уже в main.
  `apps/reviews`, `service_detail.html`, миграции `booking/0011-0012`, `stays/0020`,
  `reviews/0001-0002` — присутствуют в main.
- **Ветка `claude/siteadaptor-audit-analysis-imb7gk`** = main + 2 docs-коммита (аудит
  2026-07-01 + вплетение пробелов в ТЗ). Только документация, кода не меняли. FF-мержится в
  main чисто (если владелец захочет закрепить аудит в main).
- **Для нового КОДА** — ветвиться от свежего `origin/main` новой `claude/<topic>` (не от ветки аудита).
- Деплой на сервере — вручную владельцем; локальные службы (Postgres/Redis) уже подняты
  SessionStart-хуком.

## 2. Что уже сделано (верифицировано аудитом против кода)

- **Волна L:** L1 ✅ (рантайм-биндинг локалей `Tenant.active_locales`), L2 ✅ (кабинет «Sprachen»),
  L3-модель ✅ (i18n `Service`/`StayUnit`, overlay-семантика), L3c-рендер ✅ (локализованные
  имя/описание услуг и номеров на витрине). Всё с осознанными отклонениями (см. `…-L-plan §10`).
- **Волна U-A:** UA1-1/1-2/1-3 ✅ (деталь услуги + контракт `SellableEntity` + 5 адаптеров),
  UA2-1 ✅ (контракт в контексте деталей), UA4-1/4-2 ✅ (реестр секций + data-driven рендер),
  UA4-3 ✅ (attributes/FAQ/primary_action услуги), UA4-4a/4-4b ✅ (generic `reviews.Review` +
  верифиц. отзывы Service/Stay/Event + per-entity JSON-LD).
  ⚠️ **«U-A закрыта» НЕТОЧНО** — из UA3 сделан только override primary-CTA; единый `_buybox`
  (UA3-1 слайс 2) и двухшаговый buy-box (UA3-2) НЕ сделаны (см. `…-ua-plan §7`).
- **U-B / U-C / U-D / U-E — НЕ начаты.**

## 3. Очередь волн (SOURCE OF TRUTH — `unified-sellable-entity-master-track-2026-06-30.md §4`)

```
0. Волна L: L1 → L2 (ДО кода U-A, без миграции) ; L3 (i18n Service/Stay, миграция) ∥ U-A.
1. U-A (UA1-2 → UA1-3 → UA2-1 → UA3-* → {UA4-3 ∥ UA4-4a} → UA4-4b). UA1-1 уже реализован.
2. U-B → U-C (UB3-2 = M2M Collection, мини-разведка до UB3-1; E-2 правовой засев внутри U-C).
3. U-D (Order.payment_method в UD1-1 + параллельный трек E-7 платежи; UD3-1-схема ∥ UD1-1; SMS отложен).
4. U-E (slots-first канва акций).
```

## 4. Аудит 2026-07-01 — что недостаёт (уже вплетено в ТЗ)

Полный отчёт — **`docs/audit-2026-07-01.md`** (план↔факт + рынок A1–A9 + security, всё
адверсариально верифицировано). Пробелы разложены по очереди волн:

- **`master-track §7`** — сводная карта «что недостаёт» по волнам 0→4 + вертикали E-9…E-15.
- **`…-ua-plan §7`** — остаток U-A (единый `_buybox`, UA3-2, AutoRepair @type, демо-A9,
  reviews-email wiring, combo i18n, пробелы тестов) с уликами `file:line`.
- **`…-L-plan §10`** — остаток L (L3-ввод форм + мультиязычный демо, L4 хром/`.po/.mo`/письма,
  L5 `LegalDoc`/AGB, L6 URL) + отметки отклонений.
- **Pointer'ы** в `ub/uc/ud`-планах (поиск+фасеты→U-B; правовой пакет E-2 + JSON-LD→U-C;
  E-7 платежи + A7/A9 финансы→U-D).

**Рынок (метод `(full + 0.5·partial)/total`):** A5 79.6% · A6 72.4% · A8 61.1% ·
A1/A2 57.7% · A3 57.4% · A4 54% · A9 ~47.8% · A7 43.8%. **Сквозной блокер №1 — E-7
платёжный микс DACH** (PayPal/Klarna Kauf-auf-Rechnung/SEPA + `Order.payment_method`),
критичен для 6 архетипов, не покрыт ни одной волной.

## 5. Рекомендованный первый шаг новой сессии (нужно решение владельца)

Три кандидата, по убыванию срочности:

- **(A) Багфиксы безопасности — сделать ПЕРВЫМИ (быстро, вне волн).** 2× HIGH stored/DOM XSS
  в карте агрегатора: `templates/aggregator/_map.html` — (1) `{{ map_points_json|safe }}` в
  `<script>` идёт мимо экранирования (в отличие от `apps/core/seo.py::_dumps`); источник
  `apps/aggregator/views.py:359` и `portal_views.py:184` (`json.dumps` без `.translate`);
  (2) Leaflet `bindPopup(...)` вставляет `p.title`/`p.url` как innerHTML (`_map.html:35`).
  Данные — из tenant-редактируемого `Promotion.title`. Фикс: прогнать map-JSON через `_dumps`
  + экранировать title/href в попапе (textContent/`encodeURI`). + medium: newsletter-форма без
  rate-limit/honeypot (`promotions/public_views.py:781`); фолбэк Fernet-ключа секретов без
  гейта DEBUG (`apps/secrets/crypto.py:19-24`). Детали — `audit §4`.
- **(B) Доделать остаток U-A** (`…-ua-plan §7`): единый `_buybox.html` (UA3-1 слайс 2) →
  UA3-2 двухшаговый → AutoRepair @type + демо-A9 + reviews-email wiring. Закрывает «U-A закрыта»
  честно, чистит фундамент перед U-B.
- **(C) Двинуться по очереди волн:** старт **U-B** (единый листинг → facet-framework →
  UB3-2 M2M `Collection` с мини-разведкой ДО UB3-1) ЛИБО внутренняя часть **E-7**
  (`Order.payment_method` + Vorkasse — дёшево, без внешнего провайдера, снимает топ-блокер).

**Рекомендация:** (A) багфиксы XSS сразу (маленькие, безопасность), затем спросить владельца
(B) vs (C). Все три — с план-доком до кода.

## 6. Перед боевым запуском (владелец, блокеры Stage 0)

Stripe live (ключи/Price 39€/Connect/webhook — `billing-stripe-setup.md`), инфра (отд.
Postgres, бэкапы, `SECRETS_ENCRYPTION_KEY`, `SENTRY_DSN`, `RESEND_API_KEY`), право DACH
(AVV — `dsgvo-review.md`, прогон k6). Внешние интеграции — `external-integrations-backlog.md`.
