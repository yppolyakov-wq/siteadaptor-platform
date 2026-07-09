# Глобальный аудит кабинета — работоспособность, архетипы, упрощение (2026-07-09)

Заказ владельца: пройти по КАЖДОМУ разделу/подразделу/сущности кабинета — проверить
работоспособность, соответствие архетипу и упростить (визуально, понятно). Отдельно
названо: форма товара громоздка; не найдены настройки Kanban-доски; левая панель
редактора «прыгает» при входе (выключить, не удаляя); проверить настройки создания
компании + демоданные + полноту архетипов + пройти путь «регистрация → рабочий сайт».

Метод: 6 параллельных разведок кода + живой стенд (dev-БД, засеян демо `friseur`) с
реальным рендером форм/сайдбара. Все ключевые факты верифицированы против кода/стенда.

---

## 0. Сводка по важности (что чинить в первую очередь)

| # | Находка | Важность | Объём |
|---|---|---|---|
| A | **БАГ ПОТЕРИ ДАННЫХ:** форма «Einstellungen» стирает 6 полей при каждом Save (в т.ч. `small_business`=Kleinunternehmer/НДС, `owner_digest_enabled`, `tax_number`, `voucher_max_percent`, `service_area_*`) | 🔴 Критично | XS |
| B | Форма товара: порядок сломан (Name — 17-е поле), нет группировки, 33 чекбокса, help_text не выводится | 🟠 Высокая | M |
| C | Онбординг «Mit Beispielen» пуст для 4 новых архетипов; handwerker-витрина ведёт с пустого каталога | 🟠 Высокая | M |
| D | Редактор: левая панель «прыгает/прячется» при входе | 🟡 Средняя | S |
| E | Kanban-доска: настроек нет вообще (столбцы/названия/правила захардкожены) | 🟡 Средняя | S→L (по амбиции) |
| F | Настройки: Zahlung/Versand разорваны на 3 экрана; дубли (часы, право, акцент/шрифт); длинная форма | 🟡 Средняя | M |
| G | Архетип-гейтинг: часть настроек/полей нерелевантна вертикали (не скрыта) | 🟢 Низкая | S |
| H | Структурные мелочи: `collections` без ModuleSpec; `blog` в неверной группе; много «сирот»-страниц | 🟢 Низкая | S |

Рекомендуемый порядок исполнения — §9.

---

## 1. Путь пользователя «регистрация → рабочий сайт» (с точками трения)

Реестр витринных архетипов (`apps/core/archetypes.py`) считает «главный товар» по активному
МОДУЛЮ (`_PRIORITY=[events,stays,booking,catalog,promotions]`), не по business_type.

1. **Регистрация** (`apps/tenants/forms.py:17-41`): slug / business_type / email / пароль.
   `business_type` — ПРОСТОЙ `<select>` из 14 типов; красивые карточки-эмодзи
   (`onboarding.business_type_cards`) здесь НЕ используются (только позже в мастере). ⚠ трение.
2. **Дашборд** → плашка «Setup N/7» → мастер `/dashboard/setup/` (7 шагов, `onboarding.py:17`).
3. **Шаг 1 «Was machst du?»** — 14 карточек-архетипов (эмодзи+blurb). Кнопки: 🎁 Mit Beispielen /
   Ohne Beispiele / Überspringen.
   - ⚠ **«Mit Beispielen» зовёт `demo.load_demo` (тонкий `apps/tenants/demo.py`), НЕ богатый кит.**
     Для friseur/handwerker/werkstatt/events в `demo.py` НЕТ записей → пользователь получает
     дженерик «Beispiel-Produkt 1/2/3», а не Termine/Aufträge/Events. Богатые киты
     (FRISEUR/…) доступны ТОЛЬКО как отдельные демо-субдомены, из онбординга недостижимы.
4. **Шаг 2 «Stil & Farbe»** — карточки шаблонов. ⚠ у friseur/handwerker/werkstatt/events нет
   архетип-подобранного шаблона (`sitetemplates.recommended_for` их не знает) → дженерик.
5. **Шаг 3 «Was willst du anbieten?»** — тумблеры модулей, рекомендованные сверху, «Untypisch»
   в `<details>`. Чисто, архетип-осознанно. ✓
6. **Шаг 4 «Basics»** — адрес/часы/телефон/почта, live-save. ✓
7. **Шаг 5 «Banner»** — hero заголовок/текст/фото. ✓
8. **Шаг 6 «Erster Inhalt»** — ⚠ CTA каталог-центричен ВСЕГДА («Produkt anlegen» + промо-пресеты),
   независимо от архетипа. У friseur/events/handwerker главный товар — услуги/билеты/заявки, а
   их гонят создавать *товар*. (Хотя `onboarding.completeness._OFFER_CTA` архетип-осознан —
   шаг 6 его не переиспользует.)
9. **Шаг 7 «Geschafft»** — ссылки на дашборд/модули. Достижение = завершено. ✓

**Итог витрины после онбординга** для handwerker/friseur/events без ручного ввода — пустая
главная секция (пустые товары / пустые «Leistungen» / пустые события).

---

## 2. Карта кабинета (сущности по разделам)

Сайдбар = 4 группы (`NAV_GROUPS`), ~10 видимых пунктов (5 якорей-хабов + standalone).
Модули с `nav_items=()` — только вкладки хаба/URL.

- **Sortiment** (catalog, core): Produkte(`Product`+варианты+модификаторы) · Kategorien(`Category`) ·
  Lager(`inventory.StockMovement`) · Kombi(`Combo`) · Import(`imports`).
- **Verkäufe** (board, core): Board(Kanban всех транзакций) · Bestellungen(`Order`) · Termine(`Booking`) ·
  Übernachtungen(`StayBooking`) · Tickets(`Event`) · Aufträge(`Job`). Вкладки гейтятся по модулю.
- **Marketing** (promotions): Aktionen(`Promotion`) · Bewertungen(`reviews.Review`) · Kampagnen(`CouponCampaign`) ·
  Gutscheine(`Voucher`) + Erweitert: Reservierungen/Einlösen/Treuepunkte/Kanäle/Beiträge.
- **Kunden** (crm): Kontakte(`Customer`) · Nachrichten(`inbox`) · Telegram(`TelegramBot`).
- **Einstellungen** (settings, core): Einstellungen · Benachrichtigungen · Rechtstexte(`LegalDoc`) ·
  Zusatzleistungen(`Extra`) + Erweitert: Sprachen/Medien/Domains/Funktionen/Hilfe.
- **Standalone:** Dashboard · Website(конструктор) · Blog(`BlogPost`) · Auswertungen · Finanzen(`RevenueEntry`) · Abrechnung.

**Структурные замечания (низкий приоритет):**
- `collections` — сущность-подборки БЕЗ `ModuleSpec` в реестре → не подчиняется тумблерам
  «Funktionen», видимость хардкод (booking||stays). Единственная сущность без модуля-владельца.
- `blog` не перечислен в `NAV_GROUPS` → падает в группу «Verkaufen», хотя это Marketing/контент.
- Много «сирот» — под-страницы доступны только кнопками с родителя (orders settings/kitchen/table-qr,
  booking resources/services/passes, stays units/channels/checkins/reports, events teachers, newsletter,
  invoices). Гейтятся по url_prefixes, но в навигации их нет.
- gift / customer_account — без кабинетного UI (только витрина).

---

## 3. Форма товара (жалоба «громоздко/непонятно») — подтверждено вживую

Файлы: `apps/catalog/forms.py:102-206`, `templates/catalog/product_form.html`, модель
`apps/catalog/models.py:48-117`. Живой рендер (friseur): **23 поля формы**.

- 🔴 **Порядок сломан:** шаблон — плоский `{% for field in form %}` (`:47-53`) → `name_de`
  рендерится **17-м** (после цены/валюты/единиц/склада/EK/reorder/происхождения/ингредиентов).
  Новичок сначала видит «Einkaufspreis netto» и «Meldebestand», а название — почти внизу.
- **help_text НЕ выводится** в форме товара (в `category_form.html` — выводится). Подсказки
  написаны в модели/форме, но невидимы.
- **Обязательны только 2:** `base_price` (поз. 2) + `name_de` (поз. 17). Всё прочее optional.
- **Нет группировки:** 33 чекбокса маркировки (allergens 14 + additives 13 + diets 6) + весь
  T5-блок (cost/reorder_point/reorder_target) + unit/content_amount + sku/gtin навалены в одну
  колонку `max-w-xl` → длинный скролл.
- **Дубли/путаница:** stock/cost/reorder есть и на товаре, и на КАЖДОМ варианте (9 инпутов в
  ряд, `product_form.html:80-90`) с fallback-логикой; `is_featured` vs `badge` — оба «выделить».
- `currency` — свободный `TextInput` (легко опечатать), почти никогда не меняется.
- **SEO-полей у товара НЕТ** (у `Product` нет slug/meta) — пункт «SEO» из брифа не подтверждён;
  slug есть только у категории.

**Предложение упрощения:** (1) починить порядок (field_order/явные секции — name/description
первыми); (2) секции + аккордеон «Erweitert»: **Basis** (name/desc/category/base_price/фото/
is_active) всегда видно, свёрнуто **Preis&Einheit** / **Lager&Einkauf (T5)** / **Lebensmittel-
Kennzeichnung** / **Marketing**; (3) режим Простой/Эксперт над формой; (4) рендерить help_text +
дефолты (currency=бейдж EUR, пустое=не ведётся); (5) визуал: drag-drop фото с превью, toggle-
свитчи, чипы вместо 33 чекбоксов, live-превью карточки, live Grundpreis/маржа (формулы готовы
`models.py:181-197`). Category — почти ок (slug/sort/icon в Erweitert, icon-пикер). Variant/Combo —
прятать T5-тройку. Import — уже прост.

---

## 4. Kanban-доска — настроек НЕТ (подтверждено)

Ни столбцов/стадий, ни их названий/порядка, ни правил перехода — всё захардкожено на уровне
платформы, одинаково для всех тенантов.
- Столбцы = `apps/core/pipeline.py:16` `STAGES=(intake,in_progress,done,terminal)` + `STAGE_LABELS`
  (DE) + `PIPELINE` per-kind `{status:stage}`. `pipeline_for(kind)` тенанта НЕ принимает.
- Переходы = FSM per-app (`apps/*/state_machine.py`); `on_transition` зашивает сайд-эффекты
  (finance-выручка, склад-леджер, письма, unredeem ваучеров) на КОДЫ статусов.
- Drag-drop: target = первый допустимый FSM-переход, чья стадия совпала с колонкой.

**Варианты дать настройку (по возрастанию сложности):**
- **V1 — переименование колонок** (визуальные подписи per-tenant в `site_config["board"]`). Низкий
  риск, XS-S. Протянуть `tenant` в `pipeline_for`/`manage_sections_for`.
- **V2 — порядок/скрытие колонок** (перестановка/видимые стадии per-tenant). Низкий-средний риск.
- **V3 — кастомная группировка статусов по бóльшему числу колонок** (FSM не трогаем, меняем
  раскладку status→stage per-tenant). Средний-высокий.
- **V4 — свои статусы/правила перехода** = редактирование FSM per-tenant. Высокий риск/новая
  подсистема (статусы — CharField без справочника; сайд-эффекты привязаны к кодам). **НЕ делать**
  без переработки FSM-слоя.
Рекомендация: V1(+V2) поверх `site_config`.

---

## 5. Редактор сайта — «прыгающая левая панель» (найдена причина)

Редактор = `templates/tenant/site_home.html` (вьюха `home_builder_view`, `core/views.py:926`).
(`site.html` — это хаб-дашборд «Website» со ссылками, НЕ редактор.)

- «Прыгает» именно `#bld-editor-pane` (360px инспектор-шторка, `:92`): стартует классом
  `.bld-collapsed`, а правило `translateX(calc(-100% - 5rem))` лежит в inline `<style>` (`:1131`),
  который парсится ПОСЛЕ рендера элемента → при наличии `transition-transform duration-200`
  панель ВИДИМО выезжает влево на первом кадре = «прыгает и прячется». Плюс restore из
  localStorage (`:1326-1336`) повторяет анимацию при повторном входе.
- **Фикс «прыжка» (низкий риск):** снять `transition-transform` с начальных классов (`:92`) ИЛИ
  добавить `no-anim`-класс, снимаемый через `requestAnimationFrame` после первого кадра — паттерн
  уже используется для этой же панели (`:1863`/`:1903`).
- **«Выключить, но не удалять»:** флаг на `#bld-root` (напр. `rail-off`) — держать rail+pane в
  DOM, но принудительно collapsed, short-circuit `toggleRail()`/`showArea()`, глушить restore.
  Настройки областей — `[data-bld-area]` внутри `#home-form`, поэтому скрытие шторки НЕ ломает Save.
- **«Перенести настройки верхнего тулбара в панель»** = БОЛЬШОЙ рефактор (обработчики привязаны к
  id; конфликт с `.bld-ribbon-open`, которая прячет панель `visibility:hidden`; тренд UC6-9/10 был
  ОБРАТНЫЙ — из панели в тулбар). Рекомендация: сначала СТАБИЛИЗИРОВАТЬ панель (фикс прыжка),
  перенос тулбара обсудить отдельно (значимый объём).

Верхний тулбар (`site_home.html:11-63`): ←Dashboard · Undo/Redo · статус · hint · `.bld-ctx`
(имя блока + Простой/Эксперт + свернуть/закрыть, виден при выбранном блоке) · Desktop/Tablet/
Mobile · ☰Menu · 🧱Blocks · ⚙️Template · 🔗Share · Save.

---

## 6. Настройки + дизайн

- 🔴 **БАГ ПОТЕРИ ДАННЫХ (verified live).** `BusinessSettingsForm.Meta.fields` = 21 поле,
  `settings.html` рендерит только 15. 6 полей в форме, но без инпутов → на КАЖДОМ Save приходят
  пустыми и перезаписывают БД: `small_business` True→False (Kleinunternehmer §19, НДС!),
  `owner_digest_enabled` True→False, `tax_number`→'', `voucher_max_percent` 25→0,
  `service_area_plz`/`service_area_note`→''. Файлы: `apps/tenants/forms.py:56-78` vs
  `templates/tenant/settings.html:22,51`. **Фикс:** вывести поля ИЛИ убрать из `Meta.fields`.
- **Разрыв ментальной модели:** Zahlungen — на экране Billing (`billing/payments.html`); Versand/
  Vorkasse/Prepay — на экране Bestellungen (`orders/views.py:274-321`); а НЕ в хабе Einstellungen.
  «Настройки бизнеса» разорваны на 3 места. Кандидат — собрать таб «Zahlung & Versand».
- **Дубли:** часы работы (свободный текст `opening_hours` + структурный `oh_*`); правовые тексты
  (плоские в settings vs per-locale в Rechtstexte); **акцент/шрифт правятся в ДВУХ экранах**
  (`site.html` «Design & content» и `site_home.html` «Theme») — рассинхрон; типографика/стиль
  карточек только в builder-теме.
- **`settings.html` длинная одностраничная форма** (3 fieldset + 7 строк часов + 3 больших
  правовых textarea) → разбить на in-page аккордеоны (Kontakt / Öffnungszeiten / Einzugsgebiet /
  Betrieb / Recht & Steuer); toggle-свитчи и слайдер (`voucher_max_percent`) вместо голых полей.
- Остальные вкладки в целом ок: notifications (матрица, гейтится по модулю ✓), languages,
  media, domains, modules (образец архетип-осознанного UI ✓), extras.

---

## 7. Архетип-релевантность (что скрывать по вертикали)

- **Zusatzleistungen (Extra)** подключены на витрине только для stays → таб нерелевантен без
  stays/booking. Кандидат на `module_key` в `HUB_TABS` (`cabinet.py:71`, сейчас `None`=всегда).
- **Widerruf/AGB** (Rechtstexte) нужны при онлайн-продаже (товары/билеты/предоплата) — для витрины-
  салона/handwerker без корзины не обязательны.
- **service_area_plz/note** — только доставка/выезд (bakery/grocery/handwerker); бессмысленны для
  friseur/cafe/hotel/events.
- **quick_add / стиль карточек товара** — только каталожные архетипы; для friseur/handwerker/hotel — шум.
- **voucher_max_percent / auto_redeem_on_scan** — только при активных promotions/loyalty.
- ✓ Уже работает хорошо: тумблеры модулей («untypical»-бейдж + предупреждение), матрица
  уведомлений (гейт по модулю), S6b-скрытие хаба Sortiment по архетипу в Простом режиме.

---

## 8. Полнота архетипов и демо (проверено)

- **Kit-покрытие 8/14:** есть у grocery(AKTIONSMARKT), restaurant(RESTAURANT+PRANASY), retail(SHOP),
  hotel(HOTEL), friseur(FRISEUR), werkstatt(WERKSTATT), handwerker(HANDWERKER), events(RETREAT — ⚠ ключ
  кита `retreat`, не `events`). **Без кита:** bakery, butcher, clothing, cafe, tour_operator, other.
- **ДВЕ несвязанные системы демо:** богатые киты (`demo_kits.py`, только субдомены через
  `seed_demo_tenants`) ≠ тонкий онбординг-демо (`demo.py`, что реально получает новый пользователь).
- ⚠ **`demo.py` не обновлён под 4 новых архетипа** (нет `_SERVICES["friseur"/"werkstatt"]`,
  `_EVENTS["events"]`, нет jobs-сидера) → «Mit Beispielen» даёт им дженерик-товары/пустоту.
- ⚠ **handwerker: витрина ведёт с ПУСТОГО каталога** — `jobs` активен, но НЕ в
  `archetypes._PRIORITY`/`PRIMARY_SECTION` → `primary_module()` падает на catalog (core). Тест
  `test_archetypes_s6` проверяет только что модуль jobs включён, не что он primary. **Фикс:**
  добавить `jobs` в `PRIMARY_SECTION` + вставить в `_PRIORITY` выше catalog.
- ⚠ restaurant/cafe/tour_operator: primary = booking(services), т.к. booking > catalog в
  `_PRIORITY` — для ресторана «главная» ведёт с Termin, а не с меню.

**Регенерация демо:**
```
python manage.py seed_demo_tenants                        # все 9 китов
python manage.py seed_demo_tenants --kit friseur --recreate   # один, пересоздать
python manage.py seed_demo_tenants --delete               # удалить демо-тенантов
```
Субдомены: restaurant-demo/pranasy/hotel/aktionsmarkt/friseur/werkstatt/handwerker/retreat/shop
(.siteadaptor.de); hotel доп. поднимает портал hotels.siteadaptor.de. Логин демо: `demo-12345678`.
⚠ Кит архетипа **events** зовётся `--kit retreat`.

---

## 9. Рекомендуемый порядок исполнения (волны)

- **W0 — Багфикс формы настроек (🔴, XS).** Вывести/убрать 6 полей. Останавливает потерю НДС-статуса.
- **W1 — Редактор: стабилизировать левую панель (🟡, S).** Фикс «прыжка» + флаг «выключить, не
  удаляя». (Перенос тулбара в панель — отдельно, по решению.)
- **W2 — Форма товара (🟠, M).** Порядок → секции+аккордеон → Простой/Эксперт → визуал. Главная UX-победа.
- **W3 — Онбординг/демо новых архетипов (🟠, M).** jobs в `_PRIORITY` (handwerker); записи `demo.py`
  для friseur/handwerker/werkstatt/events + jobs-сидер; архетип-CTA шага 6; шаблоны стиля; карточки
  на регистрации; промо-пресеты.
- **W4 — Настройки: упрощение + гейтинг (🟡, M).** Аккордеоны settings; собрать Zahlung&Versand;
  дедуп часов/права/акцента; скрыть нерелевантные табы/поля по архетипу.
- **W5 — Kanban: настройки V1+V2 (🟡, S-M).** Переименование + порядок/скрытие колонок per-tenant.
- **W6 — Дизайн/тема: единый источник (🟢, S-M).** Убрать двойное задание акцента/шрифта.

Каждая волна = отдельный инкремент (ветка → CI → чекпоинт). W0 можно сделать сразу.
