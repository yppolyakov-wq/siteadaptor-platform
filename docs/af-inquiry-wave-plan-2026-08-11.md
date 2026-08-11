# План AF-волны: событийные поля заявки + встраиваемый блок формы (2026-08-11)

Источник: `docs/goodkarma-catering-gap-analysis-2026-08-11.md` (пробелы C-2/C-3),
отмашка владельца 2026-08-11: «делаем C-2+C-3, присвой ID и начни с план-дока».
Требование владельца: **свободно добавлять в другие архетипы при целесообразности
и индивидуально наполнять** → всё через per-tenant конфиг с пресетами в демо-китах,
никаких хардкодов «только для кейтеринга».

ID (task-catalog, семейство **AF** «Anfrage-волна»):
- **AF-1** — событийные поля формы `/anfrage/` (Wunschdatum · Anzahl Personen ·
  Art der Veranstaltung) + per-tenant настройка + пресеты демо-китов. Закрывает
  дефолт-вариант **MB-3** (`archetype-behavior-specs-2026-07-23.md`).
- **AF-2** — встраиваемые ref-блоки форм на страницах витрины: `anfrage_ref`
  (форма заявки, гейт jobs) и `message_ref` (контакт-форма, гейт inbox).

Параллельная сессия в git (`claude/w11-5-website-studio-7qyojs`, SM-4 сайдбар) —
пересечений кода НЕТ (она: nav_registry/modules/кабинет-шаблоны; мы: jobs/siteconfig/
витрина). Пересечения только append-файлы (task-catalog, build-log, CLAUDE.md, .po,
app.css) — тривиальный мерж. Работаем на `claude/goodkarma-catering-analysis-fea071`,
в main не мержим.

## §1. Решения (по итогам разведки)

1. **Хранение полей заявки — колонки Job** (⚠️ миграция `jobs/0013`, аддитивная):
   `event_date` DateField(null=True, blank=True) · `guest_count`
   PositiveIntegerField(null=True, blank=True) · `event_type` CharField(100,
   blank=True, default=""). Прецедент — vehicle-блок (`0007`/`0008`). JSONField у
   Job нет; колонки дают сортировку/фильтр в кабинете и честные письма. Бюджет —
   НЕ делаем (у референса его тоже нет; v2 по спросу).
2. **Конфиг формы — `site_config["anfrage"]`, PRESENCE-MINIMAL** (класс page_blocks:
   ключ пишется только непустым; `"anfrage" not in normalize({})` — golden целы;
   антипример — `jobs_vehicle`, который always-present и сидит в golden).
   Форма ключа: `{"fields": [...], "event_types": [...]}`, где
   `fields ⊆ {"date","guests","event_type"}` (порядок канонический, не польз.),
   `event_types` — список строк ≤12 × ≤60 симв. Отсутствие ключа = форма прежняя
   (все существующие тенанты/киты не меняются). `normalize_anfrage()` +
   вызов из `_normalize_impl` рядом с `normalize_presence`.
3. **Валидация POST — fail-soft, сущность заявки важнее полей**: битая дата →
   None (заявка создаётся); guest_count → int, кламп 1..100000, иначе None;
   event_type принимается ТОЛЬКО из настроенного списка (fail-closed против
   мусора), иначе "". Все три поля опциональны (как у референса).
4. **Настройка per-tenant — панель в кабинете** на списке Aufträge
   (`templates/jobs/list.html`, прецедент «⚙️ Status-Namen anpassen»):
   `<details>` «⚙️ Anfrage-Formular» — 3 чекбокса полей + textarea «вариант на
   строку» для Art der Veranstaltung → POST `jobs:anfrage-form-settings`,
   **targeted-write** (копия ПОЛНОГО текущего конфига, правка одного ключа —
   инвариант W6; замок probe-ключом `notify`). Так ЛЮБОЙ архетип включает поля
   и наполняет варианты индивидуально.
5. **Пресеты демо-китов** («целесообразность»): поле `DemoKit.anfrage_form`
   (dict | None, по образцу `jobs_vehicle`), сидится в site_config. Включаем у
   4 китов с Catering/Partyservice: restaurant, bakery, butcher, retreat(pranasy)
   — каждому свой список Art der Veranstaltung (Firmenfeier/Hochzeit/Geburtstag/…
   по архетипу). Handwerker/werkstatt НЕ трогаем (демонстрация opt-in: ключа нет —
   форма прежняя). Мастер-пресет `apply_business_type` — v2 (вместе с архетипом
   Catering C-1, если владелец даст отмашку).
6. **Префилл из детали услуги**: request-CTA в `_buybox.html` (:101, :106) получает
   `?betreff={{ …|urlencode }}` — механика `betreff` в anfrage-вьюхе уже есть.
7. **AF-2 — два ref-блока, данные `{}`** (blanket-ветка `_clean_cblock_data`
   не трогается): `anfrage_ref` → base «anfrage», `message_ref` → base «message»
   (НЕ «contact_ref» — base «contact» коллидирует с home-секцией контактов в
   BLOCK_TEMPLATES). Per-instance заголовок блока — НЕ делаем v1 (ref-блоки без
   данных — инвариант семьи; ширina/позиция/ряды достаются бесплатно от
   `_clean_cblock`). v2 — за отдельным решением.
8. **Общий партиал формы**: разметка формы `/anfrage/` извлекается 1:1 в
   `templates/storefront/_anfrage_form.html` (страница и блок включают его);
   **характеризационный замок ДО извлечения** (ключевые маркеры разметки
   /anfrage/). Партиал читает гейты единообразно: `site.jobs_vehicle`,
   `site.anfrage`, `request.tenant.has_service_area/...` — anfrage-вьюха начинает
   передавать `site` (она уже зовёт normalize). CSRF в блоке работает:
   `page_blocks`/`render_block` рендерят с `request=request` (проверено разведкой).
   Аналогично `message_ref`: форма из `message_contact.html` → партиал
   `_message_form.html`; попутно закрываем пред-существующую дыру — вьюха
   принимает `phone`, инпута в шаблоне нет → добавляем инпут.
9. **Гейты блоков**: `anfrage_ref` рендерится только при активном модуле jobs
   (`storefront_jobs_enabled`), `message_ref` — при inbox
   (`storefront_inbox_enabled`); модуль выключен → пусто (паттерн «пустой
   референс рендерит ничего»).
10. **Билдер**: записи в `block_types` (apps/core/views.py:1920-1983) с
    `page_only: True` (иконки 📝/✉️, немецкие лейблы — стиль существующих
    ref-записей); CBLOCK_VARIANTS/DEMO_DATA не трогаем (у ref-семьи их нет —
    инсертер вставляет сразу).

## §2. Инкременты (батч-режим, каждый гейтится локально)

**AF-1a — модель + миграция** `jobs/0013_job_event_fields`: 3 колонки; smoke
create_job с новыми kwargs (дефолты — старые вызовы celы: rueckruf, ручной ввод
кабинета).
**AF-1b — normalize_anfrage** + замки: presence-minimal, кламп/whitelist, golden
не изменились, идемпотентность.
**AF-1c — витрина**: fieldset в `_anfrage_form.html`-извлечении рано? Нет:
сначала AF-1c правит `anfrage.html` НАПРЯМУЮ (fieldset date/guests/select под
гейтом `site.anfrage`), извлечение партиала — в AF-2a (один ход разметки за раз).
Вьюха: parse+create_job kwargs; `site` в контекст. Замки — зеркала
vehicle-гейтинга (показ при конфиге / скрыт без; POST сохраняет; мусор fail-soft;
event_type вне списка → "").
**AF-1d — кабинет+письмо**: карточка контакта job detail (строка 🎉 тип · 📅 дата ·
👥 гостей), строка в list.html-ряду (📅 при наличии), `job_new.txt` + subject не
трогаем; панель «⚙️ Anfrage-Formular» + endpoint (targeted-write + замок
не-затирания чужих ключей); префилл `?betreff=` в `_buybox.html` (замок href).
**AF-1e — демо-киты**: `DemoKit.anfrage_form` + 4 кита + замок (сид кита →
normalize держит ключ). ⚠️ ops: `seed_demo_tenants --kit restaurant|baeckerei|
metzgerei|retreat --recreate` после деплоя.
**AF-2a — партиалы**: характеризационные замки страниц `/anfrage/` и `/nachricht/`
ДО правок → извлечение `_anfrage_form.html` / `_message_form.html` (byte-парити
рендера страниц) + phone-инпут в message-форме.
**AF-2b — ref-блоки**: `PAGE_REF_BLOCKS += ("anfrage_ref","message_ref")`,
BLOCK_TEMPLATES += anfrage/message → секц. партиалы-обёртки
(`sections/_anfrage.html`, `_message.html`: заголовок + include формы + гейт
модуля), block_types записи. Замки: normalize (в page_blocks живёт, в sections
отбрасывается), рендер на service_detail/info с модулем и без, csrf в отдаче,
builder add_block + `data-bt` маркеры (зеркала test_page_ref_blocks).

## §3. Тесты/гейты (сводно)

- Зеркала существующих замков: vehicle-гейтинг (`test_public.py:77/84`),
  ref-блоки (`test_page_ref_blocks.py`), golden (`test_normalize_golden`),
  презенс-минимальность (`test_cblocks.py:464+`).
- `ruff format --check .` целиком; `test_template_comments` (правки шаблонов);
  новые Tailwind-классы не ожидаются (реюз классов формы) — если появятся,
  `npm run build:css` + коммит app.css.
- i18n: новые msgid (лейблы полей — англ. msgid как в anfrage.html; панель
  кабинета — стиль jobs/list.html) → записи в 5 `.po` (гейт `scripts/i18n_gap.py`
  в CI). `.mo` локально — `polib` при немецких ассертах.
- Прогоны: `apps/jobs`, `apps/tenants` (siteconfig+golden+ref+demo_kits smoke),
  `apps/core` (builder add_block), `--reuse-db`; финально — стопка на ветку,
  один CI.

## §4. Не-цели (v1)

Бюджет-поле · per-instance заголовок ref-блока · колонки Verkäufe-Liste ·
ручной ввод кабинета с событийными полями · пресет мастера/apply_business_type ·
архетип Catering (C-1 — отдельное решение владельца) · rueckruf без изменений.

## §5. Риски

- golden: единственный писатель нового ключа — normalize_anfrage, presence-minimal
  (замок «не в normalize({})»).
- Извлечение партиала формы — только с характеризационным замком ДО (правило HF/UA3).
- Миграция jobs/0013 аддитивная; у параллельной сессии миграций нет — нумерация
  свободна. ⚠️ Деплой владельцем + пересев 4 демо-китов.
- `_buybox.html` — правки гейтить ВКЛЮЧАЯ apps/tenants (урок CI 1145) и
  паритет-замки buybox.
