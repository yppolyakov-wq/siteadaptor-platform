# Волна SR — «Sortiment Redesign» (фидбэк + утверждённый канвас 2026-08-24)

Дата: 2026-08-24. Отмашка владельца: «ВСЕ ОК» по дизайн-канвасу «Sortiment Redesign»
(6 артбордов; исходники `docs/design/sortiment-redesign-2026-08-24/`), включая
подтверждение «визуальный редактор сохраняет форматирование — на витрине оно тоже
отображается». Родитель: программа редизайна B (`redesign-b-implementation-plan-2026-08-24.md`),
инварианты те же: рендер-слой, FSM/вьюхи-приёмники/движки целы; W0 (скрытие только CSS);
CSS-пересборка в том же коммите; новые msgid ×5 .po.

## 0. Решения владельца (зафиксированы)

1. `/dashboard/angebote/` остаётся ЕДИНСТВЕННОЙ страницей ассортимента,
   с переключением вида «Kacheln ↔ Liste»; `/catalog/products/` умирает → 302
   (прецедент W10-6/X2b). Liste наследует инструменты старой страницы товаров
   (Art.-Nr., фильтры категория/статус, «Als Varianten zusammenführen»).
2. Имя и фото сущности кликабельны → родная форма; текстовая ссылка
   «Bearbeiten» удаляется (и на категориях тоже).
3. Цена и наличие — главная информация карточки/строки (Bestand цветом:
   зелёный/жёлтый ⚠/красный Ausverkauft).
4. Карточка товара — на всю ширину: «Preis & Bestand» — постоянная карточка
   справа (виден на любом табе; таб «Preis & Lager» исчезает как отдельная
   панель), 🌐-пиктограмма языков ввода в углу вместо ряда пилюль,
   визуальный редактор описания, «＋ Anlegen» новой категории прямо в форме.
5. Категории: фото и имя кликабельны → форма категории.
6. R5c — ДЕЛАЕМ ОБА варианта на одном слое «живых подписей»:
   А) подписи в подменю сайдбара; Б) страница-обзор `/dashboard/einstellungen/`.

## 1. Инкременты (батчи; каждый — локальный гейт → push → CI → merge)

### SR-1 — Sortiment: Kacheln ↔ Liste + смерть /catalog/products/

- `sellable_manage.py`: `ManagedSellable` += `sku`, `category_label`, `stock`
  (product-ветка; прочие kind — None). Данные уже в модели, N+1 не плодить
  (select_related category, стоимость — по факту разведки).
- Вид: `?ansicht=kacheln|liste` + персист `site_config["sortiment_view"]`
  (паттерн `sales_views`: presence-minimal в normalize + targeted-write сеттер;
  golden целы — ключ появляется только при явном выборе). Дефолт: kacheln.
- Kacheln: карточка по канвасу — фото и имя = ссылки на edit_url, price bold +
  Bestand цветом, тумблер видимости, «% Aktion»; «Bearbeiten» удалён.
- Liste: product-секция = паритет старой страницы (чекбоксы + merge-форма,
  Art.-Nr., категория, Bestand); прочие kind — упрощённые строки
  (имя/цена/статус/видимость). Фильтры «Kategorie» и «Status» — GET,
  видны при активном catalog.
- Редирект: `catalog:product-list` → 302 на `sellable-manage` с переносом GET
  (q→q; kategorie/active → новые параметры), HTMX-ветка не переезжает
  (live-search старой страницы умирает вместе с ней — поиск Sortiment серверный).
- Навигация: запись подменю «Produkte» (catalog:product-list) удаляется —
  обзор Sortiment закрывает её; «＋»-цель create остаётся. Замки состава
  подменю переписываются осознанно.
- НЕ трогаем: booking:services / stays:units / events:list — это не дубли
  (несут формы создания и настройки ресурсов).

### SR-2 — Карточка товара: полная ширина + 🌐 + категория на месте

- `product_form.html`: раскладка = main + правая колонка 380px; в правой:
  «Preis & Bestand» (base_price/compare_at/stock/reorder_point/vat/EK-строка) —
  ВСЕГДА видна; «Kategorie» с инлайн-полем `new_category` («＋ Anlegen» —
  создание категории при Save, без JS); «Sichtbarkeit». Поля из бывшей панели
  «Preis & Lager» переезжают физически (не скрытие) — панель исчезает из табов.
  Инвариант W0 сохраняется для остальных табов (скрытие только CSS).
- `_i18n_switch.html`: компактный режим — 🌐-иконка + выпадающие пилюли локалей
  в углу заголовка формы; механика (radio-переключение, invalid-раскрытие в
  capture-фазе, data-field-error) НЕ меняется — меняется только рендер шапки.
  Партиал общий → выигрывают все формы; замки ревью 2026-08-19 держим зелёными.
- Форма: `new_category` обрабатывается во вьюхе сохранения товара
  (get_or_create по имени, привязка) — presence-guard не нужен (пустое = нет действия).

### SR-3 — Визуальный редактор описания + витринный рендер

- Хранение: `Product.description` (TextField) начинает принимать ОГРАНИЧЕННЫЙ
  HTML. Санитайзер — новая зависимость `nh3` (осознанный `uv lock` в коммите;
  CI ставит из лока — правило 5а). Allowlist: p, br, b/strong, i/em, u, ul, ol,
  li, a[href http(s)] — всё прочее вырезается.
- Слой: `apps/core/richtext.py` — `sanitize(html)` +템플-фильтр `rich_text`
  (санитайз на РЕНДЕРЕ тоже — fail-closed к легаси-данным и прямым записям).
- Кабинет: лёгкий тулбар (B/I/U/списки/ссылка) на contenteditable, синк в
  textarea (per-locale поля Ф1 тоже); без внешних библиотек; деградация без JS —
  обычная textarea.
- Витрина: точки рендера description → `|rich_text` (вместо plain);
  карточки/тизеры — striptags+truncate (без разметки в анонсах).
- Санитайз на save в форме товара (clean_description и *_i18n).

### SR-4 — Категории кликабельны

- `category_list.html`: плитка/строка — фото и имя = ссылка на
  `catalog:category-edit`; «Bearbeiten» удалён; пустое фото — плейсхолдер
  «📷 Foto hinzufügen» (тоже ссылка в форму).

### SR-5 — R5c A+B: слой живых подписей + обзор настроек

- НОВЫЙ `apps/core/settings_hints.py`: `hints_for(tenant, user)` →
  {url_name: str} — только дешёвые источники (поля тенанта, site_config,
  вычисления в памяти; ЕДИНСТВЕННЫЙ запрос — count Membership), каждый пункт
  `_safe` (падение → статичное описание). Integrationen — светофор из полей
  (stripe/telegram/google) без запросов.
- (А) `sidebar_nav`: children раздела settings получают `hint`;
  `_base_dashboard.html` рендерит второй строкой (11px, живое — indigo).
  Считается на каждый рендер — потому только поля + 1 count.
- (Б) вьюха `einstellungen_home` + `tenant/einstellungen_home.html`
  (по отменённому план-доку `r5c-einstellungen-overview-plan-2026-08-24.md`,
  реанимирован в объёме Б): группы Geschäft/Verkauf/System/Weitere из
  `nav_registry.legacy_hub_tabs("settings")` + те же hints; гейты owner/module
  как в подменю. Вход: ПЕРВЫЙ подпункт подменю «Einstellungen — Übersicht»
  (прецедент «Sortiment — Übersicht» R7-1); якорь settings перенацеливается
  `settings` → `einstellungen-home` (прецедент W11-5 site-home), nav_key цел.
- Замки: кортеж якоря в test_x0_x7_locks (осознанно), подсветка W8, состав
  подменю (обзор первым), «новый экран имеет вход» — X7.3 автоматически.

## 2. Гейты каждого батча

ruff check+format ЦЕЛИКОМ · pytest затронутых модулей `--reuse-db` ·
`npm run build:css` при новых классах (и при УДАЛЕНИИ — урок CI #2152) ·
test_template_comments · `scripts/i18n_quickcheck.py` + msgid ×5 .po ·
golden siteconfig целы (sortiment_view presence-minimal). Стенд Playwright
в конце волны: Sortiment (оба вида, оба клика), форма товара (редактор,
🌐, категория), витринная деталь с форматированием, категории, подменю с
подписями, обзор настроек.

## 3. Не делаем (границы v1)

- Единый CRUD всех kind — нет (родные формы остаются; Sortiment = обзор+вход).
- HTMX live-search в Sortiment — нет (серверный поиск, как сейчас).
- Визуальный редактор для услуг/номеров/событий — по спросу (слой richtext
  общий, подключение — один фильтр + тулбар).
- Светофоры Integrationen «глубокие» (запросы к Stripe API) — нет, только поля.
- Liste-паритет для не-product kind (SKU у услуг и т.п.) — нет: у них нет этих полей.

## 4. Замки, переписываемые осознанно (карта — дополняется по ходу)

- test_sidebar_st4b: состав подменю angebote (минус Produkte-запись) и
  settings (плюс обзор первым).
- test_x0_x7_locks: кортеж якоря settings (url_name → einstellungen-home).
- test_w8_nav_registry: подсветка/href якоря settings.
- Замки старой страницы товаров (test_*catalog*: product_list view) →
  переезжают на редирект (ассерт 302 + carry) и на Liste-вид Sortiment.
- Разведка дополнит точным списком.
