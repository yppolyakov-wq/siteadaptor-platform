# Аудит наполненности архетипов + план доработок — 2026-06-30

> **Статус:** аудит (НИЧЕГО не разрабатывалось — только проверка). Документ —
> точка отсчёта волны доработок «комплект по умолчанию для каждого архетипа +
> языковой модуль». Ветка аудита: `claude/nifty-einstein-ix6huq`.
>
> **Метод:** 5 параллельных разведчиков (демо-киты/скрипты · витринные страницы ·
> ЛК клиента · правовые/текстовые · языковой модуль) + воркфлоу из 7
> адверсариальных верификаторов. Все 7 ключевых утверждений — **CONFIRMED** против
> кода (ссылки `файл:строка` в §8).

## 0. Хронология аудитов (ветвление по датам)

Чтобы хронология доработок читалась — каждый аудит/план датируем и линкуем
предыдущий. Срез строим инкрементально (что закрыто с прошлого раза).

| Дата | Документ | Охват | Статус |
|---|---|---|---|
| 2026-06-22 | `docs/kit-archetype-coverage.md` | покрытие 7 китов ↔ архетипы, бэклог #1–#7 | ✅ закрыт (retail-кит, обогащения) |
| 2026-06-22 | `docs/audit-2026-06-22.md` | срез Stage 0/1/2/3, A1–A9, M1–M23 | живой baseline |
| **2026-06-30** | **этот документ** | **наполненность 9 китов · витрина (главная/категории/деталь товара+услуги) · текст+право · ЛК клиента · языковой модуль** | 🟢 актуальный |

**Что изменилось с 2026-06-22:** китов теперь **9** (не 7 — добавлены `shop` и
`handwerker`); ЛК клиента `/konto/` построен (CA1–CA4) и **включён во всех 9 китах**
(старый пробел №5/№2 из coverage-аудита закрыт); языковой переключатель DE/EN
**уже есть на витрине тенанта** (на storefront-субдомене; на ПУБЛИЧНОМ/маркетинг-
домене его нет — там заметка roadmap корректна; см. §6).

---

## 1. Эталон «минимального комплекта» (требование владельца)

Для каждого архетипа в демо-версии пользователя ОБЯЗАН быть набор (минимум):

1. **Главная** (лендинг архетипа).
2. **Категории** (листинг каталога/номеров/событий/услуг).
3. **Детальная страница товара** И **детальная страница услуги**.
4. **Текстовая информация** (Über uns) + **описание услуг как FAQ**.
5. **Правовая информация** (Impressum / Datenschutz / Widerruf; для коммерции — AGB).
6. **Личный кабинет клиента** с его заказанными товарами/услугами/запросами —
   **кроме** того, что оформляется как быстрый заказ (напр. бронь акции).

> Владелец (2026-06-30): «структура — минимальная; для каждого архетипа нужно
> прописать **комплект по умолчанию для демо** + **описание услуг как FAQ**».
> Это §5 (комплекты) данного документа.

---

## 2. Матрица наполненности по архетипам

Легенда: ✅ есть · 🟡 частично · ❌ нет · — неприменимо.

| Архетип (кит) | Главная | Категории | Деталь **товара** | Деталь **услуги** | Текст/FAQ | Право | ЛК клиента | Демо-данные |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--|
| **A1/A2 Retail** (`shop`, `aktionsmarkt`) | ✅ | ✅ | ✅ | — | 🟡 | 🟡¹ | ✅ | ✅ богатые (варианты/Grundpreis/остаток/GTIN/PLZ-зоны) |
| **A3 Termin-Dienstleister** (`friseur`) | ✅ | ✅ (services) | — | ❌ **нет** | 🟡 | 🟡¹ | ✅ | ✅ 6 услуг, 2 мастера, Pass, лояльность |
| **A4 Gastro** (`restaurant`, `pranasy`) | ✅ | ✅ (+Combos) | ✅ (+combo) | — | 🟡 | 🟡¹ | ✅ | ✅ меню+модификаторы+аллергены+доставка |
| **A5 Übernachtung** (`hotel`) | ✅ | ✅ | ✅ (номер, 2 кол.+календарь) | — | 🟡 | 🟡¹ (+Hausordnung) | ✅ | ✅ 4 номера, тарифы, Kurtaxe, депозит |
| **A6 Event/Retreat** (`retreat`, `pranasy`) | ✅ | ✅ | ✅ (событие, agenda/teachers) | — | ✅ (+блог) | 🟡¹ | ✅ | ✅ события, ретрит-лендинг, блог, ведущие |
| **A7 Handwerker** (`handwerker`) | ✅ | ❌ нет публ. каталога | 🟡 (Angebot по токену) | ❌ **нет**² | 🟡 | 🟡¹ | ✅ | ✅ услуги, сметы, before/after |
| **A8 Aggregator/Portal** | ✅ | ✅ (переисп. catalog) | ✅ | — | 🟡 | 🟡¹ | n/a | ❌ **нет отдельного кита** (портал `hotels.<base>` как side-effect `--kit hotel`) |
| **A9 Kfz-Werkstatt** (`werkstatt`) | ✅ | ❌ нет публ. каталога | 🟡 (Angebot по токену) | ❌ **нет**² | 🟡 | 🟡¹ | ✅ | ✅ услуги, Fahrzeug-сметы (HSN/TSN), Teile |

¹ Право: Impressum/Datenschutz/Widerruf **есть** (автогенерация), но **AGB нет** и
правовые тексты **не засеваются** в демо → Datenschutz всегда показывает
placeholder «Bitte passen Sie diesen Text an…», Widerruf — placeholder у
не-доставочных демо (§4).
² A7/A9 имеют услуги (`booking.Service`) → попадают в ту же дыру «нет детальной
услуги», что и A3 (§3.1).

### Вывод матрицы
- **Главная / категории / правовое / ЛК** — закрыты практически везде.
- **Две настоящие функциональные дыры:**
  1. **Детальная страница УСЛУГИ отсутствует** (A3, и через `booking.Service` —
     A7/A9). У товаров/номеров/событий богатая деталь есть, у услуги — нет.
  2. **A7/A9 без публичного каталога** (только форма заявки + смета по токену).
- **Контентные дыры (демо/право):** AGB нет; правовое и язык — только DE; «описание
  услуг как FAQ» как отдельный блок не выделено.

---

## 3. Функциональные находки (что и где в коде)

### 3.1. Деталь услуги — ОТСУТСТВУЕТ (A3 + A7/A9) — CONFIRMED
- Маршруты `/termin/` только: `termin_index` (листинг) → `service_slots`
  (форма брони), `service_book`. **Нет** `service_detail` ни в URL, ни в шаблонах
  (`config/urls_tenant.py:161-172`, `apps/booking/public_views.py:79-98,147-187`).
- Шаблоны деталей есть для всех ОСТАЛЬНЫХ: `product_detail.html`,
  `stay_detail.html`, `event_detail.html`, `combo_detail.html`; **нет**
  `service_detail.html`.
- Ирония: `booking.Service` (`apps/booking/models.py:61-92`) уже несёт богатые
  поля (`description`, `image`, `price`, `duration`), seed-комментарий зовёт их
  «A3 богатая карточка» (`demo_kits.py:3726`) — но контент рендерится только
  line-clamp карточкой в листинге (`service_index.html:13-17`), не на деталке.
- Werkstatt/Handwerker сеют `booking.Service` и идут тем же путём без деталки.

### 3.2. A7/A9 без публичного каталога работ — CONFIRMED (by-design, но дыра под требование)
- Только `/anfrage/` (форма заявки) + `/angebot/<token>/` (смета, доступна по
  приватной email-ссылке). Нет публичной витрины «наши услуги/работы» с деталкой.
- Под требование «деталь услуги» это решается тем же `service_detail` (§3.1) +
  опц. галереей кейсов (before/after уже есть в ките как секция).

### 3.3. ЛК клиента `/konto/` — ПОЛНЫЙ, активен во всех 9 китах — CONFIRMED
- Magic-link вход (без пароля), 11 разделов: Bestellungen `/bestellung/<code>/`,
  Termine `/t/<code>/`, Übernachtungen `/s/<code>/`, Tickets `/e/<code>/`, Angebote
  `/angebot/<token>/`, Reservierungen `/r/<code>/`, Rechnungen, Gutscheine,
  Bonuskarten, Mehrfachkarten, Nachrichten `/nachricht/<token>/`. GDPR-экспорт/
  удаление, self-cancel брони/билета (`apps/account/`).
- Активен во всех 9 китах: транзакционные типы — по `recommended_for`; 4 «other»-
  кита (friseur/werkstatt/handwerker/retreat) явно добавляют `"customer_account"`
  в `enable_modules`. `seed_records=True` у всех 9 → `/konto/` наполнен записями
  по активным модулям кита (`apps/account/account_data.py`).
- **Это и есть требуемый «личный кабинет с заказанными товарами/услугами/
  запросами»** — он есть. «Быстрый заказ» (бронь акции `/r/<code>/`) тоже доступен
  по коду без входа — соответствует исключению из требования.

### 3.4. Демо-данные — богатые, но 3 контентных пробела
- 9 китов с глубоким наполнением (каталог/услуги/номера/события/акции/ваучеры/
  отзывы/блог) + наполненный кабинет. Подробный per-kit инвентарь — §5.
- Пробелы: (а) правовое не засеяно (§4); (б) EN-контент только у `pranasy`
  (§6.4); (в) «описание услуг как FAQ» отдельным блоком не выделено (§5.10).

---

## 4. Правовые и текстовые страницы

- **Есть** (автогенерация из полей `Tenant`, `apps/tenants/models.py:213-313`,
  вьюхи `apps/promotions/public_views.py:625-666`): Impressum `/impressum/`,
  Datenschutz `/datenschutz/`, Widerruf `/widerruf/` (+ онлайн-форма
  `/widerruf-formular/`), Über uns `/ueber-uns/`. У отеля бонус — Hausordnung.
- **AGB — ОТСУТСТВУЕТ полностью** (CONFIRMED): нет маршрута `/agb/`, нет поля
  `Tenant.agb/terms`, нет шаблона. ⚠️ В доках есть ошибочное «AGB уже есть»
  (`hotel-archetype-plan.md:152`) — код это опровергает; есть и план-набросок
  «Rechtstexte-Wizard» (`market-analysis/a1a2-retail-online-shop.md`).
- **Правовое НЕ засевается в демо** (CONFIRMED): `apply_kit`/`seed_demo_tenants`
  не пишут `impressum/privacy_policy/withdrawal_policy` → Datenschutz во ВСЕХ демо
  рендерит placeholder «Bitte passen Sie diesen Text an Ihr Geschäft an.»
  (`models.py:248`); Widerruf — placeholder у не-доставочных демо (у доставочных,
  напр. restaurant/pranasy/shop, генерится полноценная Widerrufsbelehrung für Waren).
- **Только DE**: правовые поля — одноязычные `TextField` (§6).

---

## 5. Комплект по умолчанию для демо — по архетипам (требование владельца)

Спецификация «что seed обязан положить в демо каждого архетипа». Помечено:
**[✓]** уже сеется · **[+]** добавить (доработка). Источник «есть» — §1 demo-аудита.

### 5.1. A1/A2 Retail — кит `shop` (эталон), `aktionsmarkt` (промо-витрина)
- **[✓]** Главная (слайдер/категории/акции), 3 категории, 12 товаров.
- **[✓]** Деталь товара (варианты R1, Grundpreis R2, остаток R3, GTIN, отзывы о товаре).
- **[✓]** Доставка A2 (PLZ-зоны, Mindestbestellwert), лояльность, ваучеры.
- **[✓]** ЛК: заказы C&C + доставка.
- **[+]** Правовое: засеять Impressum (полное)/Datenschutz/Widerruf/**AGB** под retail.
- **[+]** FAQ-блок «Versand & Rückgabe» (описание условий как FAQ, §5.10).

### 5.2. A3 Termin-Dienstleister — кит `friseur`
- **[✓]** Главная, листинг услуг (6), 2 мастера, Pass (10er), лояльность, мини-каталог (4).
- **[✓]** ЛК: брони `/t/<code>/`, Mehrfachkarte.
- **[+] Деталь услуги** (`service_detail` — §3.1): фото/галерея, полное описание,
  длительность/цена, мастера, превью доступности, CTA «Termin buchen».
- **[+]** FAQ услуги (что входит, подготовка, отмена) — §5.10.
- **[+]** Правовое: Impressum/Datenschutz/Widerruf засеять (услуги — без Versand-Widerruf).

### 5.3. A4 Gastro — киты `restaurant`, `pranasy`
- **[✓]** Главная, меню (категории+подкатегории), деталь блюда + **Combo-деталь**,
  модификаторы, аллергены/диеты, доставка+зоны, события, лояльность, отзывы.
- **[✓]** ЛК: заказы, брони стола, билеты событий.
- **[+]** Демо-бронь стола в кабинете (сейчас seed_records не льёт booking для gastro — мелочь из coverage-аудита).
- **[+]** Правовое + FAQ (Lieferung/Allergene) — §5.10.

### 5.4. A5 Übernachtung — кит `hotel`
- **[✓]** Главная, листинг номеров, **богатая деталь номера** (2 кол.+календарь
  наличия), тарифы/Verpflegung, Kurtaxe, депозит, авто-скидки, Hausordnung,
  Gutschein, Online-Checkin, extras.
- **[✓]** ЛК: брони `/s/<code>/`, self-cancel, чек-ин.
- **[+]** Правовое засеять; FAQ (An-/Abreise, Stornо, Haustiere) — §5.10.

### 5.5. A6 Event/Retreat — киты `retreat`, `pranasy`
- **[✓]** Главная, листинг+календарь событий, **богатая деталь события** (agenda/
  Programm/ведущие/анкета/before-after/отзывы), блог, ведущие, связка stays.
- **[✓]** ЛК: билеты `/e/<code>/` (QR), self-cancel.
- **[+]** Ценовые тиры билета (Frühbucher/Standard/Kind) — реальная дыра A6 (из coverage-аудита).
- **[+]** Правовое + FAQ (Teilnahme/Anreise/Erstattung) — §5.10.

### 5.6. A7 Handwerker — кит `handwerker`
- **[✓]** Главная, 5 услуг, форма заявки `/anfrage/`, смета `/angebot/<token>/`,
  before/after, отзывы.
- **[✓]** ЛК: Angebote/Aufträge.
- **[+] Деталь услуги** (§3.1) + публичный листинг «Leistungen» (§3.2) — каталог
  фикс-услуг с деталкой.
- **[+]** FAQ (Ablauf Anfrage→Angebot→Auftrag, Anfahrt, Garantie) — §5.10.
- **[+]** Правовое + **AGB** (B2C-ремонт).

### 5.7. A8 Aggregator/Portal — отдельного кита НЕТ
- **[✓]** Портал `hotels.<base>` как side-effect `--kit hotel`.
- **[+]** Опц. собственный demo-кит портала (мультивендор-листинг + поиск/фильтры/
  гео) — низкий приоритет, отдельный трек.

### 5.8. A9 Kfz-Werkstatt — кит `werkstatt`
- **[✓]** Главная, 5 услуг, Fahrzeug-сметы (Kennzeichen/HSN/TSN), Teile-каталог,
  before/after, отзывы.
- **[✓]** ЛК: Angebote/Aufträge, заказы Teile.
- **[+] Деталь услуги** + листинг (§3.1/§3.2); FAQ (HU/AU, Ersatzwagen, Kosten) — §5.10.
- **[+]** Засеять смету с расходником из каталога (G11 симбиоз не виден в демо).

### 5.9. Сквозной минимум для ВСЕХ китов (добавить в seed)
- **[+]** Засев правового (Impressum полный + Datenschutz + Widerruf + AGB) —
  убрать placeholder из демо (§4).
- **[+]** EN-контент во всех китах (сейчас только `pranasy`) — §6.4.
- **[+]** Блок «Leistungsbeschreibung / FAQ» (§5.10).

### 5.10. Блок «Описание услуг / FAQ» (требование владельца) — НОВОЕ
Сейчас FAQ-секция витрины есть (`DemoKit.faq`), но это общий FAQ бизнеса. Нужен
**per-услуга / per-направление** разъясняющий блок:
- На **детальной услуги** (когда появится, §3.1): «Was ist enthalten / Ablauf /
  Dauer / Vorbereitung / Stornо» — структурированное описание-FAQ.
- В каждом ките — заполнить осмысленным текстом под вертикаль (примеры по
  архетипам выше). Реализация — поверх существующих полей (`Service.description` +
  опц. JSON `faq` у услуги) либо секция детальной; миграция — решается планом.

---

## 6. Языковой модуль — «время пришло» (статус + план)

### 6.1. Что просил владелец и что в CLAUDE.md
- Владелец: «договаривались, что языковой модуль — позже; время пришло. В CLAUDE.md
  должна быть информация».
- **Факт:** в `CLAUDE.md` отдельной записи «языковой модуль отложен» **НЕТ** —
  только I18n-миксин (§2) и «язык задач» в AB3 (это формулировки, не локализация).
  Решение об отсрочке зафиксировано в **`docs/roadmap-next-sprints.md` §«Отложено»**
  (стр. 611-613, 644, 668). → **рекомендация:** добавить в CLAUDE.md строку-статус
  языкового модуля (сделано в этой сессии — пойнтер в §7 памяти).

### 6.2. Что УЖЕ есть (фундамент — больше, чем казалось)
- Django i18n включён: `USE_I18N=True`, `LANGUAGES=[de,en]`, `LocaleMiddleware`,
  `LOCALE_PATHS` (`config/settings/base.py:133,184-192`).
- **Переключатель DE/EN РАБОТАЕТ на витрине тенанта** (CONFIRMED): вьюха
  `set_language` (`public_views.py:445`), URL `storefront-set-language`
  (`urls_tenant.py:133`), видимый переключатель с `hreflang` в шапке витрины
  (`_base.html:86-91`), язык в cookie → `LocaleMiddleware`. **Уточнение к C1:**
  переключатель только на storefront (`urls_tenant`); на ОСНОВНОМ/публичном домене
  (`urls_public`) его НЕТ — поэтому заметка `roadmap-next-sprints.md:668` («на
  основном домене нет публичного `set_language`») **корректна** (относится к
  публичному домену, не к витрине). Т.е. фундамент языкового модуля на витрине уже
  есть; на публичном домене — нет.
- Модельная i18n: `I18nMixin.get_i18n()` + `JSONField {de,en}` у `Product`/
  `Category`(+description)/`Event` (`apps/core/models.py:31-52`).
- Оверлей `site_config`: `siteconfig.localize(cfg, locale)` накладывает EN поверх DE
  (`apps/tenants/siteconfig.py:974-1020`); рендер берёт `get_language()`
  (`apps/core/context.py:123-129`).
- Поля тенанта `default_locale` + `enabled_locales` СУЩЕСТВУЮТ (`models.py:32-33`).

### 6.3. Что НЕ работает / пробелы (CONFIRMED)
1. **`enabled_locales`/`default_locale` не используются в рантайме** — активный язык
   определяют ТОЛЬКО `settings.LANGUAGES` + cookie; оверлей хардкодит
   `OVERLAY_LOCALES=("en",)`. Тенант не может задать свой набор языков/дефолт.
   (Доковая ремарка `I18nMixin` про «default_locale» — обманка, поле не читается.)
2. **Нет скомпилированных `.po/.mo`** — `locale/` пуст (`.gitkeep`). UI-строки,
   обёрнутые в `{% trans %}`, при EN показывают исходный msgid (немецкий).
3. **Витринный «хром» в основном хардкод-DE** — навигация/кнопки/футер не обёрнуты
   в `trans` (переводятся лишь поля `site_config` через оверлей, если заполнены).
4. **Письма — только DE** (нет locale-вариантов шаблонов).
5. **Правовое — только DE** (`impressum/privacy/withdrawal` — одноязычные `TextField`).
6. **EN-контент заполнен только у `pranasy`** — остальные 8 китов DE-only → при
   переключении на EN показывают немецкий (оверлея нет).
7. **Нет кабинетного UI** для владельца: выбрать включённые языки, ввести переводы
   полей/контента, переключать язык контента в формах.

### 6.4. План языкового модуля (фундамент готов → «достройка», фазами)
- **L1 — связать тенанта с языками (S, без больших миграций):** читать
  `tenant.enabled_locales`/`default_locale` в `set_language` (валидация), в
  переключателе шапки (показывать только включённые), в `OVERLAY_LOCALES`
  (динамически). Это «настоящий» per-tenant выбор языков.
- **L2 — кабинет «Sprachen» (M):** форма владельца: включить языки, дефолт. Тумблер
  попадает в `enabled_locales`. (Расширяемо за пределы de/en — `LANGUAGES` уже список.)
- **L3 — перевод контента в UI (M):** в формах товара/категории/услуги/события/
  site_config — поля per-locale (есть `*_de/*_en` паттерн у `Category.description`,
  расширить). Заполнить EN во всех демо-китах (`DemoKit.i18n`, как у `pranasy`).
- **L4 — UI-хром и письма (M):** обернуть витринные строки в `{% trans %}`,
  `makemessages`+`compilemessages` (наполнить `locale/de,en`), locale-aware email.
- **L5 — правовое многоязычно (M):** `impressum/privacy/withdrawal/agb` — per-locale
  (JSON или отдельные записи), EN-шаблоны автогенерации.
- **L6 (опц., отложено) — язык в URL** (`/en/...`) + корректный `hreflang`/canonical
  — большое SEO-решение с редиректами (как в roadmap). Делать только при спросе.

> Порядок рекомендуемый: **L1 → L3 (EN в киты) → L2 → L4 → L5**; L6 — позже.

---

## 7. Скрипты обновления демо (`seed_demo_tenants`)

Источник: `apps/tenants/management/commands/seed_demo_tenants.py`. Субдомен —
`<key>.<base>` (кастомный у каждого кита; иначе `<key>-demo`). Реестр `KITS` —
9 ключей.

```bash
# Все 9 китов (каждый — отдельная схема/субдомен)
uv run python manage.py seed_demo_tenants

# Один кит (примеры)
uv run python manage.py seed_demo_tenants --kit shop          # → shop.<base>      (A1/A2 retail-эталон)
uv run python manage.py seed_demo_tenants --kit aktionsmarkt  # → aktionsmarkt.<base> (A1 промо-витрина)
uv run python manage.py seed_demo_tenants --kit friseur       # → friseur.<base>   (A3 услуги)
uv run python manage.py seed_demo_tenants --kit restaurant    # → restaurant-demo  (A4 gastro)
uv run python manage.py seed_demo_tenants --kit pranasy       # → pranasy.<base>   (A4 + EN + ретриты)
uv run python manage.py seed_demo_tenants --kit hotel         # → hotel.<base>     (A5 + портал hotels.<base>)
uv run python manage.py seed_demo_tenants --kit retreat       # → retreat.<base>   (A6 события)
uv run python manage.py seed_demo_tenants --kit handwerker    # → handwerker.<base> (A7 Handwerker)
uv run python manage.py seed_demo_tenants --kit werkstatt     # → werkstatt.<base> (A9 Kfz)

# Пересоздать (drop + reseed) — после изменения китов/контента
uv run python manage.py seed_demo_tenants --recreate
uv run python manage.py seed_demo_tenants --kit hotel --recreate

# Удалить демо-тенанты
uv run python manage.py seed_demo_tenants --delete
```

| Кит | Субдомен | Архетип | business_type | enable_modules |
|---|---|---|---|---|
| `restaurant` | restaurant-demo | A4 | restaurant | orders,events,jobs |
| `pranasy` | pranasy | A4 (+EN) | restaurant | orders,events,jobs,loyalty |
| `hotel` | hotel | A5 | hotel | stays |
| `aktionsmarkt` | aktionsmarkt | A1/A2 | grocery | orders,loyalty |
| `friseur` | friseur | A3 | other | booking,loyalty,orders,customer_account |
| `werkstatt` | werkstatt | A9 | other | booking,jobs,orders,customer_account |
| `handwerker` | handwerker | A7 | other | jobs,booking,customer_account |
| `retreat` | retreat | A6 | other | events,booking,orders,customer_account,stays,jobs |
| `shop` | shop | A1/A2 | retail | orders,loyalty |

> ⚠️ При доработках, добавляющих миграции, на сервере: `git pull origin main &&
> ./scripts/deploy.sh single`, затем `seed_demo_tenants --recreate`.

---

## 8. Доказательная база (file:line — все CONFIRMED)

| # | Утверждение | Вердикт | Ключевое доказательство |
|---|---|---|---|
| C1 | Переключатель DE/EN есть на витрине тенанта (storefront) | ✅* | `public_views.py:445`, `urls_tenant.py:133`, `_base.html:86-91`. *Уточнение: на публичном домене (`urls_public`) переключателя НЕТ → `roadmap:668` корректен для него |
| C2 | Деталь услуги (A3, и A7/A9) отсутствует | ✅ | `urls_tenant.py:161-172`, `booking/public_views.py:79-98,147-187`; нет `service_detail.html` |
| C3 | AGB отсутствует полностью | ✅ | `urls_tenant.py:268-272`, `tenants/models.py:115-118`; нет поля/маршрута/шаблона |
| C4 | Правовое не засевается → placeholder в демо | ✅ | `demo_kits.py:52-178` (нет полей), `seed_demo_tenants.py` (нет записи), `models.py:248,268` |
| C5 | `enabled_locales`/`default_locale` не читаются в рантайме | ✅ | `public_views.py:447-449`, `context.py:123-129`, `siteconfig.py:974` |
| C6 | `customer_account` активен во всех 9 китах; `/konto/` наполнен | ✅ | `demo_kits.py` enable_modules ×9, `modules.py:288-307`, `account_data.py` |
| C7 | Ровно 9 китов; A8 без кита (портал side-effect) | ✅ | `demo_kits.py:3218-3228`, `seed_demo_tenants.py:89-128` |

---

## 9. Приоритизированный бэклог доработок (волна 2026-06-30)

Размер: S ≤полдня · M ~1-2 дня · L >2 дней. Порядок — на владельце.

| # | Доработка | Архетип | Размер | Зачем |
|---|---|---|---|---|
| **D1** | **Деталь услуги** `service_detail.html` + маршрут | A3, A7, A9 | **M** | Главная функц. дыра под требование «деталь услуги» |
| **D2** | Блок «Описание услуг / FAQ» (per-услуга) + наполнить киты | A3/A7/A9 (+все) | M | Требование владельца §5.10 |
| **D3** | **L1**: связать `enabled_locales`/`default_locale` с переключателем и оверлеем | сквозное | S | Старт языкового модуля поверх готового фундамента |
| **D4** | **L3**: EN-контент во ВСЕ 8 китов (как у pranasy) | сквозное | M | Переключатель есть, но контент DE-only |
| **D5** | Засев правового в демо (Impressum/Datenschutz/Widerruf) — убрать placeholder | сквозное | S | Демо «как настоящее», без TODO-текста |
| **D6** | **AGB**: поле `Tenant.agb` + маршрут `/agb/` + автошаблон + футер | A1/A2/A4/A7/A9 | M | Правовая полнота коммерции (DACH) |
| **D7** | **L2/L4/L5**: кабинет «Sprachen», UI-перевод, `.po/.mo`, письма, правовое i18n | сквозное | L | Полноценный языковой модуль |
| **D8** | A7/A9 публичный листинг «Leistungen» (каталог фикс-услуг) | A7, A9 | S-M | Снять дыру «нет каталога» |
| **D9** | Ценовые тиры билета (Frühbucher/Standard/Kind) | A6 | M | Реальная дыра A6 (из coverage-аудита) |
| **D10** | Опц. demo-кит портала-агрегатора | A8 | M | Единственный архетип без кита |

**Рекомендация по старту:** D1+D2 (закрывают «деталь услуги + FAQ» — прямое
требование), затем D3+D4 (включить языковой модуль на готовом фундаменте), затем
D5+D6 (правовое/AGB), затем D7 (полная языковая достройка).

---

## 10. Связанные документы
- `docs/kit-archetype-coverage.md` (2026-06-22, предыдущий срез) ·
  `docs/audit-2026-06-22.md` (baseline) · `docs/micro-business-verticals.md`
  (карта вертикалей) · `docs/archetype-market-analysis.md` (рынок) ·
  `docs/roadmap-next-sprints.md` §Отложено (язык/hreflang — частично устарело, см. C1) ·
  `apps/core/modules.py` (реестр модулей) · `apps/core/archetypes.py` (primary_item).
