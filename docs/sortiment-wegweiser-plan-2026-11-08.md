# План: корень каталога «Wegweiser» (`/sortiment/`) — 2026-11-08

Запрос владельца (08.11): «делай /sortiment/ по Wegweiser с ЕСС». Эталон —
`docs/design/portal-home-2026-11-07/S1_Sortiment.dc.html`. Дефекты прода —
`docs/portal-home-variants-analysis-2026-11-07.md` §1 «Онлайн-магазин». План составлен агентом
`planner` (ECC), ссылки file:line сверены на момент написания.

## 0. Коротко

Wegweiser — **новая композиция корня каталога** (`catalog_page_style="wegweiser"`), а не правка
дефолта. Сверху вниз: направления (плитки с числами) → «Schnell finden» (чипы) → «Im Fokus»
(одна лента с вкладками Neu · Reduziert · Beliebt) → «Weitere Artikel» (тулбар + сетка без
дублей). Тенанты без ключа — байт-в-байт. Демо `online_shop` («Weitwerk») переходит на
Wegweiser, пресет `neu_sale` у него снимается. Плавающие кнопки и эмодзи «йога» у Isomatte —
отдельные инкременты. Миграций нет.

## 1. Почему так выглядит прод

- **Карусели над направлениями.** Демо `ONLINE_SHOP` (`apps/tenants/demo_kits.py`, `page_presets`
  с `("catalog", "neu_sale")`) кладёт два блока «Liste» с `above=True` перед маркером `main`
  (`apps/core/page_presets.py`). Они рендерятся в слоте `listing_before` каркаса
  `templates/storefront/listing.html`, а плитки направлений живут в `listing_facets` — ниже.
  Тот же порядок у CLOTHING, SHOP, OUTLET.
- **Сетка дублирует «Neu».** Блок «Neu» сортирован по `newest`; сетка берёт
  `GET.sort or catalog_sort or "newest"` (`apps/promotions/public_views.py` `product_list`).
- **Плавающие кнопки** «🎨 Design testen» и чат-FAB (`templates/storefront/_base.html`) не
  резервируют места снизу; фокус может уйти под них (WCAG 2.2 SC 2.4.11).
- **Isomatte с эмодзи «йога».** `apps/tenants/demo_images.py::_emoji_for` берёт первое
  совпадение подстроки; пара `("matte", "🧘")` стоит раньше `("isomatte", "🛌")`.

| Элемент S1 | Сейчас | Разрыв |
|---|---|---|
| H1 + сводка «N Artikel in M Bereichen · K reduziert · J neu» | H1 есть, сводки нет | новая строка |
| Плитки направлений: фото, имя + число, подкатегории, «neu: N» | `_category_tile.html` без чисел, под каруселями | новый партиал, один агрегат |
| «Schnell finden» — чипы со счётчиками | нет | новый блок |
| «Im Fokus» — лента с вкладками, «Alle N →» | две отдельные ленты пресета | новый блок, ARIA tabs |
| Сетка + тулбар + «weitere laden» | есть, но дублирует | исключить товары Fokus |

## 2. Решение

Код `"wegweiser"` в `apps/core/compositions.py` (`applies_to={"catalog"}`, `recommended_grid="cols5"`).
Плитка появляется в кабинете «Website › Seitenvorlagen» (STU-19) и в превью `?tpl=` без новых осей.

- Дефолт закреплён замками (`test_listing_parity`, `test_dl21_root_layouts`, golden normalize) —
  его не трогаем.
- **Фильтр = результат** (прецедент O-7): при фасете/поиске/курсоре плитки, чипы и Fokus не
  рисуются, остаётся обычная сетка с заголовком «Alle Artikel».
- **Дубль:** в режиме Wegweiser сетка исключает pk панелей Fokus (≤ 15) на всех страницах без
  фасетов, включая курсорные, иначе keyset-пагинация «прыгает».
- Меньше 2 направлений → плиток нет, страница живёт.

## 3. Инкременты

| # | Что | Замки до кода |
|---|---|---|
| **W-0** | Эмодзи заглушек: короткая игла не затеняет длинную | `test_no_needle_shadows_a_longer_one`, Isomatte ≠ 🧘 |
| **W-1** | Реестр + плитки направлений + сводка | код в реестре только для catalog; порядок блоков; число запросов не растёт с направлениями; 0/1 направление → 200; при `?q=` плиток нет; Standard байт-в-байт |
| **W-2** | «Im Fokus» + дедуп сетки | ≤ 5 на вкладку, < 3 — вкладки нет; «Alle N →» только при остатке; 0 общих pk с сеткой на 1-й и курсорной странице; ARIA tabs; без JS — первая панель; запросы постоянны |
| **W-3** | «Schnell finden» | чипы только с N > 0, каждая ссылка → 200 и ровно N; < 2 чипов — блока нет |
| **W-4** | Плавающие кнопки | «Design testen» в баннере демо, а не `fixed`; резерв снизу + `scroll-padding-bottom`; чат на телефоне — иконка с доступным именем |
| **W-5** | Демо `online_shop` → Wegweiser | ключ стиля, нет блоков `neu_sale`, у кита ≥ 3 neu и ≥ 3 beliebt; `test_demo_lists` зелёный |

i18n: каждый msgid — во все 5 `locale/*/django.po`, `scripts/i18n_quickcheck.py`; Tailwind —
`npm run build:css`; шаблоны — `test_template_comments`.

## 4. Решения владельца (по рекомендации, пока владелец не сказал иначе)

| Вопрос | Решение |
|---|---|
| **Р-1** «Beliebt» по чему | `is_featured` или бейдж `beliebt`; продажи — v2 |
| **Р-2** «Schnell finden» | авто-набор v1: подборки · «Unter X €» · Neu · Sets; ручные гиды — через подборки |
| **Р-3** «Neu» | бейдж `neu`, а не дата создания (у демо и импорта даты одинаковые) |
| **Р-4** Порядок у Standard | не трогаем; Wegweiser предлагается в Seitenvorlagen |
| **Р-5** Другие киты | в v1 только `online_shop` |
| **Р-6** «weitere laden» без перезагрузки | вне v1 |
| **Р-7** Wegweiser на страницах направлений | v1 только корень |
| **Р-8** Плавающие кнопки | чиним для всех витрин |

## 5. ECC-прогоны

- **Скиллы до кода:** `django-patterns`, `django-tdd`, `postgres-patterns`, `accessibility`, `seo`,
  `e2e-testing`.
- **Агенты:** `django-reviewer` — каждый инкремент; `database-reviewer` — W-1/W-2 (агрегат по
  корням, `exclude(pk__in)` + keyset); `a11y-architect` — W-2/W-3/W-4; `silent-failure-hunter` —
  W-2 (пустые панели не дают молча дубль); `security-reviewer` — не нужен (нового ввода нет).
- **Стенд Playwright** на `online_shop`, 1440 и 390, de и ru: порядок блоков; 0 общих товаров
  Fokus/сетка; вкладки мышью и клавиатурой; `scrollWidth == 390`; FAB не перекрывает последний
  ряд; после fetch-свопа вида (KAT-5) вкладки живы; 0 JS-ошибок.
