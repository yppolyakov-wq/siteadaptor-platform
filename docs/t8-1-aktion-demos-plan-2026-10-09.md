# T-8.1 «Nur Aktionen»: профиль витрины + 5 лёгких демо Solingen

**Статус:** ✅ сделано 2026-10-09 (8.1a–8.1d, БЕЗ миграций).
**Родитель:** `t8-aktion-start-lite-analysis-2026-10-09.md` §2.4, §7, §7.1; решения Р-1…Р-7,
О-1…О-4 по рекомендации (`t8-city-offers-portal-2026-10-09.md` §6).
**Разведка:** две (механика демо-китов; витрина без каталога + страница акции).

---

## 0. Что делаем

1. **Профиль витрины «Nur Aktionen»** — ключ `site_config["profile"] = "aktionen"`
   (presence-minimal: нет ключа = прежнее поведение, golden целы). Витрина = визитка + акции,
   каталог и корзина не видны ниоткуда.
2. **Карточка бизнеса на странице акции** «So finden Sie uns» — адрес + «Route planen»,
   часы и статус «geöffnet», телефон, WhatsApp. Для ВСЕХ тенантов с адресом/телефоном:
   для локального бизнеса это главное после цены, а сегодня на `/p/<uuid>/` этого нет вовсе.
3. **Пять лёгких демо в Solingen** (не копии полных демо — свои имена, иначе в городском
   каталоге было бы два «Backhaus Krume»). Город один — `Solingen` (дыра A6: свободный текст),
   координаты заданы → работают карта и «рядом со мной» портала.

## 1. Факты разведки (на что опираемся)

- Каталог — core-модуль (`modules.py:89-107`), выключить нельзя; `/sortiment/` отвечает 200
  всегда. Флага, скрывающего каталог, **нет**.
- При нуле товаров сами исчезают: кнопка «Menu» в hero, секции products/categories, дети меню.
  **Остаются:** пункт меню каталога (`menu._archetype_url` проверяет только модуль), «Menu» в
  автоматическом нижнем баре (`context.py:177`, безусловно), поиск шапки → `/sortiment/`
  (`context.py:470-483`), иконка корзины (если orders), hero-плитки без гейта.
- `storefront_root="promotions"` делает **редирект** `/` → `/aktionen/`, а там нет ни адреса, ни
  часов. Поэтому профиль НЕ использует редирект корня: главная = визитка (hero + акции + контакт).
- Свободная акция (без цели) валидна; цена = `new_price`, без `compare_at` — просто цена
  (так делается «Neu bei uns» без скидки).
- **Найден дефект (вне T-8.1, закрывает T-8.2):** кнопка акции создаёт обычный заказ без
  проверки модуля `orders`, а `/bestellung/<code>/` за этим модулем (`_require_orders_active`).
  У cafe/restaurant/friseur/events/catering/other модуль заказов по умолчанию ВЫКЛЮЧЕН →
  клиент «зарезервировал» и получил 404, а владелец заказа не видит (вкладки Verkäufe — по
  активным модулям). Лёгкие демо до T-8.2 включают `orders` явно (комментарий в ките).

## 2. Профиль «Nur Aktionen» — точки правки

| Где | Сейчас | При профиле |
|---|---|---|
| `siteconfig.normalize` | ключа нет | `profile` ∈ {"aktionen"}, иначе ключ дропается |
| хелпер | — | `apps/core/storefront_profile.py`: `is_aktionen(tenant_or_cfg)`, `CATALOG_PATHS` |
| каталог/корзина/наборы/лукбук/PDF-меню (вьюхи) | 200 | 302 на `/` (декоратор `redirect_if_aktionen`) |
| пункт меню `archetype:catalog`, `categories` | ссылка на `/sortiment/` | узел отбрасывается (None) |
| авто-нижний бар «Menu» | всегда | нет |
| поиск шапки | `/sortiment/?q=` | `/aktionen/?q=` |
| иконка корзины, quick-add | по модулю orders | скрыты |
| hero-плитки на `storefront-products` | без гейта | отбрасываются |
| секции главной products/categories/combos | авто по активному архетипу | не рендерятся |

`/bestellung/<code>/`, `/aktionen/`, `/p/…`, `/merkzettel/` (с SF-4a хранит и акции) — не трогаем.

## 3. Карточка «So finden Sie uns»

Партиал `storefront/_business_card.html` (контекст — только `request.tenant`):
- статус «geöffnet/geschlossen» (`_open_badge.html`) + сегодняшние часы, полный текст часов;
- адрес + «Route planen» (Google Maps directions: координаты, иначе адрес) — внешняя ссылка
  `target="_blank" rel="noopener"`;
- телефон `tel:`, WhatsApp (`core.whatsapp.wa_link`, гейт номера).
Гейт: есть адрес или телефон. Встаёт на странице акции после описания и шаринга.
Без Leaflet-карты (фикс. id карты — одна на страницу; ссылка «Route» полезнее на телефоне).

## 4. Демо (кит-поля)

Новые поля `DemoKit`: `profile: str = ""`, `lat/lng: str = ""` (→ `Tenant.latitude/longitude`).

| key / поддомен | Бизнес | Район | Тип | Акции (группы) |
|---|---|---|---|---|
| `klingenbrot` | Bäckerei Klingenbrot | Mitte 42651 | bakery | Feierabend-Tüte −50 % (heute), Sonntagsbrötchen, Kuchen der Woche · **Neu:** Dinkel-Vollkorn · **Auf Bestellung:** Wunschtorte |
| `ohligser-eck` | Café Ohligser Eck | Ohligs 42697 | cafe | Happy Hour Cappuccino, Frühstück zu zweit, Kuchen + Kaffee · **Neu:** Hafer-Latte · Mittagstisch |
| `walder-faden` | Modehaus Walder Faden | Wald 42719 | clothing | Wintermäntel −30 %, Strick-Sale, Schal gratis · **Neu:** Herbstkollektion |
| `wupperhof` | Hofladen Wupperhof | Aufderhöhe 42699 | grocery | Wochenkiste 15 € statt 19 €, MHD-Rettung, Eier 10er · **Neu:** Apfelsaft · **Auf Bestellung:** Spargel |
| `brueckenblick` | Pension Brückenblick | Burg 42659 | hotel | Last-Minute-Wochenende −25 %, Frühbucher, 3 = 2 Nächte · **Neu:** Wanderpaket |

Каждый: адрес, часы (текст + структура), телефон, WhatsApp-демо-номер (`+49 212 …` —
фиктивный, по образцу других китов), 1–2 hero-баннера, меню «Angebote · Neu · Kontakt»,
6 акций (полные ряды DL-11), фото из фонда (`static/demo/photos`, без `markt-*`/`ol-*`),
`primary_module="promotions"`, `profile="aktionen"`, без галереи/команды/отзывов
(минимальная визитка — ровно то, что получит владелец за 3 экрана). Переводы en/ru/uk/tr —
в словари `demo_i18n_<loc>.json` (без identity-записей).

`feature_demos`: + запись «Nur Aktionen — Visitenkarte & Angebote» → `klingenbrot` `/`.

## 5. Инкременты и замки

- **8.1a профиль** — замки: normalize (ключ сохраняется/мусор дропается/нет ключа → нет ключа),
  редирект каталога/корзины, меню без каталога, поиск → /aktionen/, нижний бар без «Menu»,
  без профиля всё прежнее.
- **8.1b карточка** — замки: есть адрес → карточка + Route-ссылка; WhatsApp по номеру; нет
  адреса и телефона → карточки нет.
- **8.1c демо** — все замки, обходящие KITS (меню/списки/фото/ряды/hero/часы), + свой
  `test_lite_demos.py`: у пяти китов профиль, город Solingen, координаты, ни одной ссылки на
  `/sortiment/` в главной, акции по группам.
- **8.1d переводы** — `scripts/demo_i18n_gap.py --kit <key>` по пяти китам.
- **Стенд** — главная/акция/`/sortiment/` → `/` на 1440 и 390, de+ru.

ops после деплоя: `seed_demo_tenants --kit klingenbrot` (и четыре других) — новых миграций нет.
