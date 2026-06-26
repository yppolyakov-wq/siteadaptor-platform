# Pranasy — полноценная двуязычная витрина (план)

> Запрос владельца (2026-06-26): сделать демо-тенант **pranasy** полноценным —
> ресторан (меню + «скоро открытие»), кетеринг (описание+галерея+10 блюд+форма),
> каталог ретритов (6 шт + мастера + отзывы), магазин (сосиски/колбасы ×3, кондитерка ×6
> как подкатегории; слайдер→подкатегории→товары), главная (слайдер + разделы блоками),
> страница лояльности/акций, «О нас» (цель + идеология веган/аюрведа). **Язык: DE + EN
> (полная двуязычность — решение владельца).**

«Полная двуязычность» = EN не только для товаров/категорий (модели уже умеют
`{"de","en"}`), но и для **текстов витрины** (hero/about/FAQ/CTA/подписи секций/меню) и
**заголовков/описаний событий** — это сейчас одноязычно. Поэтому сначала фундамент
i18n, затем наполнение. Идём инкрементами (ветка → ruff раздельно → build:css при
шаблонах → pytest → push → CI зелёный → FF-merge → отметка в build-log).

## Фундамент i18n (до наполнения)

### PR-A — Локализуемые тексты `site_config` [M, без миграций]
Тексты site_config становятся «строка ИЛИ `{"de":..,"en":..}`» (обратносовместимо —
старые строки работают). `siteconfig.localize(config, locale)` сворачивает все
текстовые поля к строке текущей локали ПЕРЕД рендером (вызывается в storefront-вьюхах
после `normalize`). Поля: `TEXT_FIELDS` (hero/about), `NESTED_TEXT_FIELDS` (cta),
`section_titles`, `heroes[].{title,text,button_label}`, `faq`, `testimonials`, `process`,
`team[].role`, `trust.marks`, `usp_bar`, `archetypes[].{label,blurb,intro}`, меню
(`menus`/`nav` labels). `normalize` сохраняет dict-значения как есть; локаль-фолбэк:
locale → de → en → первое значение. Тесты: смешанные строки/дикты, фолбэк, рендер EN/DE.

### PR-B — Двуязычные `Event.title`/`description` [M, миграция events]
Добавить `title_i18n`/`description_i18n` (JSONField, default `{}`); property `title_text`/
`description_text` — берёт i18n-дикт по локали, фолбэк на плоское поле. Шаблоны событий
(index/detail/карточки/teaser) → на property. Сидер событий принимает DE+EN. Без слома
существующих событий (плоские поля остаются источником, i18n — поверх).

## Наполнение pranasy (после фундамента)

### PR-C — Скелет кита + подкатегории в сидере [M]
`apply_kit`: поддержать parent/child категории (магазин→подкатегории). Переписать
скелет `PRANASY`: модули (catalog/orders/events/jobs/loyalty/promotions), меню (Restaurant
/ Shop / Catering / Retreats / Treue & Aktionen / Über uns), слайдер heroes, секции главной
(слайдер + «Unsere Bereiche» блоками), archetype-covers. Всё DE+EN.

### PR-D — Каталог: ресторан-меню + магазин [M]
- **Restaurant — Speisekarte** (баннер-слайдер + «Bald geöffnet»-плашка; покупка
  оставлена включённой — «купить сразу»): 8 блюд — Veganer Burger, Vegane Pizza, Vegane
  Pita, Hotdog, Alaputra, Kofta, Veganer Schaschlik, Nori-Pakora. DE+EN, фото, цены.
- **Shop** (родитель) с подкатегориями: Würstchen (3), Aufschnitt/Wurst (3), Süßes/Konditorei
  (6). Страница магазина: слайдер → подкатегории-блоками → товары. DE+EN.

### PR-E — Каталог ретритов (события) [M]
6 ретритов с богатой деталью (программа/мастера(teachers)/галерея/цена/цены-tiers),
общая обложка-интро + мастера + отзывы. DE+EN (title/description через PR-B).

### PR-F — Кетеринг (jobs cover) [S–M]
Лендинг кетеринга: описание + галерея + витрина 10 веган-блюд + «как мы работаем» +
форма-заявка `/anfrage/`. DE+EN.

### PR-G — Лояльность/акции + «О нас» [S–M]
Стемпель-карта + витрина акций (страница). «О нас»: цель + идеология веган/аюрведа. DE+EN.

### PR-H — Тесты кита + доки [S]
`test_demo_kits` (структура pranasy: подкатегории, 6 ретритов, EN-ключи, меню), доки,
прогон `seed_demo_tenants --kit pranasy --recreate` — на владельце (нет SSH).

## Деплой
После каждого мержа с миграцией (PR-B) — на владельце: `git pull origin main &&
./scripts/deploy.sh single`. Пере-сид pranasy: `python manage.py seed_demo_tenants
--kit pranasy --recreate` (после всех PR — финальный пере-сид).
