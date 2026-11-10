# M21.1 + M21.2 — переезд магазина с CS-Cart (haanerteeladen.de) — план

Дата: 2026-10-31. Семейство — модуль M21 «импорт из других магазинов» (`master-plan.md`).
Запрос владельца: перенести https://haanerteeladen.de/ на платформу, «всё импортировать,
создать страницы и настройки, переадресации, чтоб не потерять индексацию».

## 0. Разведка (факты)

- Сайт — **CS-Cart** (адреса `index.php?dispatch=…`, хром `ty-*`). DE + объявленная, но
  непереведённая RU-версия (`?sl=ru`). Русский владелец НЕ переносит.
- **~137 товаров**, у каждого фасовки 100 g / 250 g / 500 g / 1 kg (артикулы HT105,
  HT105.1…3). Дерево категорий 3 уровня (`/schwarzertee/klassisch-schwarzertee/assam/`),
  ~35 категорий. Карта сайта — HTML `/sitemap/` (XML-карты нет).
- Страница товара несёт JSON-LD `Product` с `AggregateOffer.offers[]` (sku, price, url
  `?variation_id=N`, availability); подписи фасовок — радио `feature_39` с
  `data-ca-product-url`, совпадающим с url оффера. Описание — `div.content-description`.
  `product_id` — в форме отзыва (`product_id=800`).
- Выгрузки CS-Cart от владельца пустые (только ключевые столбцы) — каталог берём с сайта.
- Мусор CS-Cart: блог (демо-статьи), `/contacts/` (Москва), `/compare/` — не переносим, 410.

## 1. Чего нет на платформе

1. Встроенный импорт сайта (T-8.27): 20 страниц, без фасовок, лимит 50 — не подходит.
2. **Переадресаций со старых адресов нет вовсе** — без них Google теряет ~180 адресов.

## 2. M21.1 — таблица переадресаций (⚠️ миграция `core/0014`, новая таблица)

- Модель `core.LegacyRedirect` (TENANT): `source_path` (без хвостового «/», кроме корня,
  percent-decoded), `source_query` (канон. строка выбранных параметров, «» = любой query),
  `target` (локальный путь; «» при 410), `status` 301|410, `hits`, `last_hit_at`,
  `origin` manual|import, unique (source_path, source_query).
- Сервис `apps/core/legacy_redirects.py`: нормализация, `match(path, query)` — из правил
  пути выбирается самое специфичное, чьи параметры ⊆ параметров запроса (CS-Cart:
  `index.php?dispatch=products.view&product_id=800&sl=de` ловится правилом
  `dispatch=products.view&product_id=800`); `clean_target` = правило `safe_next`
  (только локальный путь, без `//`, `\`, управляющих символов); `upsert`, CSV-импорт/экспорт.
- `LegacyRedirectMiddleware` (после `PrimaryDomainRedirectMiddleware`): ТОЛЬКО на ответ 404,
  GET/HEAD, не public-схема → одно индексированное чтение → 301 на target или та же
  страница 404 со статусом 410; счётчик хитов `F()+1`. Fail-open: ошибка БД → исходный 404.
  Нормальные страницы не платят ни одного запроса.
- Экран кабинета «Weiterleitungen» (`/dashboard/site/weiterleitungen/`): подпункт Website,
  право Website (W/WE), список с поиском и пагинацией, хиты, добавление, удаление, CSV
  импорт/экспорт. Замки DoD (nav_registry, view_perms, i18n ×5).

## 3. M21.2 — импорт CS-Cart (без миграций)

Команда `import_cscart --schema <s> --url https://… [--dry-run] [--no-images] [--vat 7]`,
логика — `apps/imports/cscart.py` (парсеры — чистые функции, тесты на фикстурах HTML).

- Категории: дерево из `/sitemap/` (служебные пути отсеяны), слаг — последний сегмент,
  при коллизии `<родитель>-<сегмент>` через `catalog.slugs.unique_slug`.
- Товары: обход категорий (`?items_per_page=96&page=N`), страница товара → JSON-LD +
  подписи фасовок. Product: name, description (HTML описания, санитайз на рендере SR-3),
  sku базы, base_price = цена базового оффера, `unit="g"` + `content_amount` (Grundpreis
  PAngV), vat 7 % (чай = продукт питания), категория = путь товара, metadata
  `cscart{product_id,url}`. Варианты: все офферы, label из радио («100g» → «100 g»),
  content_amount в граммах, OutOfStock → stock 0. Идемпотентно по `metadata.cscart.url`
  (повторный прогон обновляет, не плодит).
- Фото: `safe_fetch` полного размера → webp (тот же путь, что T-8.27 `fetch_images`).
- Переадресации (origin=import): путь товара → `get_absolute_url()`; путь категории →
  `/sortiment/<slug>/`; `index.php?dispatch=products.view&product_id=N` → товар;
  `dispatch=categories.view&category_id` — если найден; статические CS-Cart-маршруты
  (`/allgemeine-geschaftsbedienungen/` → `/agb/`, `/privacy-policy/` → `/datenschutz/`,
  `/cart/`,`/checkout/` → `/warenkorb/`, `/our-team/` → `/ueber-uns/`, `/contact-us/` →
  `/nachricht/`, `/gift-certificates/` → `/gutschein/`, `/wishlist/` → `/merkzettel/`,
  `/sitemap/` → `/sortiment/`, `/login/` → `/konto/`); блог/`/contacts/`/`/compare/` → 410.
- AGB/Datenschutz НЕ импортируем автоматически: Datenschutz CS-Cart описывает чужих
  обработчиков — платформа генерирует свой; AGB/Versand — владелец вычитывает вручную.

## 4. Вне кода (владелец)

Создать тенант (тип Online-Shop), подключить Stripe (Connect), Search Console (DNS-TXT),
адрес Haan/Wuppertal, домен → `/dashboard/domains/`, затем переключение A-записи.

## 5. ECC-прогоны

- До кода: `.claude/rules` + `docs/pitfalls.md` §2–§3 (UUID-pk, `next=`, декоратор-сирота).
- После кода: `django-reviewer` (миграция, middleware, команда) + `security-reviewer`
  (open-redirect target, CSV-ввод, SSRF при обходе — только `safe_fetch`).
- Стенд: прогон импорта на локальной схеме против живого сайта + проверка 301/410 клиентом.

## 6. Факты прогона на живом сайте (2026-10-31)

- Обход: 33 категории, 144 товара, 0 ошибок; 130 чаёв × 4 фасовки, 523 фото фасовок.
- Базовая фасовка CS-Cart в JSON-LD несёт `?variation_id=<product_id>`, а её радио —
  адрес без параметра → сопоставление через `product_id` (исправлено, замок в фикстуре).
- 13 фасованных травяных чаёв — «Kontaktieren Sie uns für den Preis» (цена 0). Импорт
  создаёт их **скрытыми** с «Nur auf Anfrage» и пишет в отчёт: показ «0,00 €» нарушил бы
  PAngV, а «Preis auf Anfrage» витрина пока не рисует (заметка в roadmap §Отложено).
  Вес фасовки берётся из названия («Kamillenblüten ganz, 100g» → Grundpreis).
- 5 слагов повторяются в разных категориях (`chai`, `vanille-bio`…) → второй получает
  суффикс категории (`chai-schwarzertee`), а не `-2`.

## 7. Runbook переезда (сервер)

1. Деплой ветки (миграция `core/0014`): `git pull origin main && ./scripts/deploy.sh single`.
2. Зарегистрировать бизнес на платформе (тип «Online-Shop») → схема, напр. `haanerteeladen`.
3. Пробный обход без записи:
   `docker compose -f docker-compose.prod.yml exec web python manage.py import_cscart --schema <схема> --url https://haanerteeladen.de`
4. Запись (≈5–10 мин: 144 страницы + ~670 фото + главная):
   `… import_cscart --schema <схема> --url https://haanerteeladen.de --apply
   --hero-title "Die wunderbare Welt des Tees" --hero-button "Lass mich verzaubern"
   --skip-banner 2 --skip-banner 3 --banner-crop 0.30:0.72`
5. Проверить витрину на поддомене; назначить цены 13 скрытым травам; вычитать AGB
   (импортирована в «Recht»), Impressum (оба адреса), Versand-текст перенести вручную.
6. Кабинет → Website → **Weiterleitungen**: проверить список (≈460 правил), при желании
   выгрузить CSV.
7. Подключить Stripe (Zahlung & Lieferung), домен (`/dashboard/domains/`),
   Search Console (DNS-TXT, ресурс «Домен»).
8. Перед переключением DNS — повторить шаг 4 (цены/фасовки синхронизируются, дублей нет).
9. Переключить A-запись; в Search Console отправить `https://haanerteeladen.de/sitemap.xml`;
   2–4 недели смотреть «Страницы → Не найдено» и счётчик «Aufrufe» в Weiterleitungen;
   недостающие адреса добавлять вручную или CSV.

## 8. M21.3 — главная, меню, логотип, цвет, контакты, Versand (2026-10-31)

Решение владельца: «главную как на старом сайте, Versand тоже, по рекомендации».
`apply_design` (вызывается командой, `--no-design` отключает):
- **Слайдер.** Баннеры CS-Cart — мобильные (900×1250) с НАРИСОВАННЫМ текстом и кнопкой.
  Как есть они дают двойной текст на телефоне → `--banner-crop верх:низ` вырезает чистую
  полосу фото; заголовок и кнопка — нашими слоями (`--hero-title/--hero-button`). Баннер 2
  (кнопка нарисована посередине) и баннер 3 (сплошной текст) пропускаются `--skip-banner`.
- **Плитки направлений** → фото категорий (6 шт., «wide», 3 в ряд — два полных ряда).
- **Порядок главной** как у старого сайта: слайдер → направления → товары → «О нас»;
  пустой блок акций выключен (на старом сайте «Im Angebot» пуст).
- **Меню**: 6 направлений (с подменю, если есть подкатегории; пункт, ведущий в подкатегорию,
  поднимается до раздела) + «Neu» (`?sort=newest`); Bestsellers/Sales — без аналога/пусты.
- **Логотип** и **фирменный цвет из логотипа** (тёмно-синий `#3c458e`; зелёный из CSS —
  стандартная тема CS-Cart, не бренд).
- **Контакты/часы** из подвала (адрес, телефон, Mo–Fr 10–18, Sa 10–14) — только пустые поля.
- **Versand + Zahlungsarten** — текстовыми блоками на «Über uns»; висящая фраза «Die
  Versandkosten berechnen sich wie folgt:» (таблицы на старом сайте нет) убирается.
  ⚠️ Текст Zahlungsarten говорит о PayPal/Vorkasse/Barzahlung — сверить с настройками оплаты.
- Статьи демо-блога CS-Cart → 410.
Повторный прогон не трогает правки владельца: слайдер/секции/цвет — только пока слайдер пуст,
меню — пока владелец его не собирал, остальное — только пустые поля. Стенд (локальный сервер,
1366 и 390 px) — главная, меню, «Über uns» проверены глазами.

## 9. Одной командой: создать магазин + перенести всё (2026-10-31)

Запрос владельца «создай сам и внеси все данные». Доступа к серверу у сессии нет, поэтому
команда умеет создать бизнес сама (`--create`, синхронно, как регистрация; пароль случайный —
владелец входит ссылкой на почту `/anmelden/link/`; мастер помечен пройденным) и переносит
Impressum: текст старого сайта → LegalDoc (юридический адрес Wuppertal), USt-IdNr, e-mail,
правовая форма, ответственный (§ 18 MStV) — только пустые поля; адрес лавки (Haan) остаётся
в контактах. Ссылка на EU-ODR (платформа закрыта 20.07.2025) — заметкой «убрать строку».

После деплоя (миграция `core/0014`):

```
docker compose -f docker-compose.prod.yml exec web python manage.py import_cscart \
  --schema haanerteeladen --url https://haanerteeladen.de --apply \
  --create --name "Haaner Teeladen" --owner-email shop@haanerteeladen.de --city Haan \
  --hero-title "Die wunderbare Welt des Tees" --hero-button "Lass mich verzaubern" \
  --skip-banner 2 --skip-banner 3 --banner-crop 0.30:0.72
```
Без `--apply` — пробный прогон (пишет «would create …» и что найдено).

## 10. M21.4 — сверка с оригиналом: каталог и меню (2026-11-10)

Фидбэк владельца: «проверь каталог и принадлежность категорий, что-то неправильно; меню —
такое же, как в оригинале». Сверка (скрипт по живому сайту: 33 категории × листинг):
- **Принадлежность товаров** совпадает у 143/144 (не хватает «Stilltee» — 504 старого сайта,
  повторный прогон добирает); «Oolong Sahne Karamell» в оригинале в ДВУХ категориях
  (у нас одна — `Product.category` FK, ограничение модели, пишется в отчёт).
- **Дефект платформы (главный):** страница категории включала товары только ПРЯМЫХ
  подкатегорий (KAT-1) — у трёхуровневого дерева «Schwarzertee» показывал 20 из 48,
  «Grünertee» 14 из 35. Фикс: `catalog.facets.branch_ids` — все живые потомки
  (запрос на уровень, предохранитель глубины 6, выключенная ветка обрывает спуск).
- **Меню оригинала** собрано вручную, 3 уровня (SCHWARZER → Klassisch → Assam…), с ссылками
  и на категории, и на отдельные товары (Pu-erh, Lapaco, Mate), плюс Newest/Bestsellers/Sales.
  Наше меню держало 2 уровня и строилось авто-подменю. Фикс: `_MENU_MAX_DEPTH = 3`
  (третий уровень — отступом в текстовой панели, «Mehr» и мобильном; плитки фото —
  только второй уровень; редактор меню внуков не показывает, но и не теряет), разбор
  меню CS-Cart ДЕРЕВОМ, подписи дословно, каждая ссылка — через таблицу переадресаций
  (категория → узел category, товар → url на новый адрес, Newest → `?sort=newest`,
  Bestsellers → каталог, Sales → архетип promotions — гаснет без модуля); порядок разделов
  каталога = порядок меню. Флаг `--replace-menu` — перезаписать уже импортированное меню.

### ECC-прогоны
- Скиллы до кода: `django-tdd` (замки до правок: 3 уровня в выдаче категории, глубина меню,
  дерево меню CS-Cart на фикстуре).
- `django-reviewer` — после кода (facets/siteconfig/шаблоны/cscart); `security-reviewer` —
  ссылки меню из чужого HTML (только локальные цели через `legacy_redirects.clean_target`).
- Стенд Playwright: меню 3 уровня на 1366/390 + страница раздела с сортами 3-го уровня.
