# Волна KAT — единая структура каталога (2026-08-18)

Решения владельца (обсуждение 2026-08-18): категория = страница (слияние лендинга
и фильтра) · комбо = товар-набор, карточками в категориях · SEO-слаги товаров ·
шаблоны страницы категории как опция админа · редиректы НЕ строим (не в проде) ·
посетителю — контрол плотности 2–6 · смена вида каталога без перезагрузки (вариант B).
Разведка: 3 Explore-агента (категории/ссылки · слаги · комбо/шаблоны) — карты в
отчётах, ключевые факты ниже по месту.

## Целевая структура URL

```
/sortiment/                         — весь ассортимент (фасеты = GET-параметры)
/sortiment/<slug>/                  — СТРАНИЦА КАТЕГОРИИ (шапка по шаблону + сетка)
/sortiment/<cat-slug>/<slug>/       — товар в категории (SEO-слаг)
/sortiment/p/<slug>/                — товар без категории
/sortiment/<uuid>/                  — старый товарный URL, живёт вторым резолвом
/kombi/                             — все наборы (+ ?kategorie=)
```
`/bereich/` умирает (вьюха+роут+тумблер category_landings); резервы слагов
категории: `p`. Порядок роутов: точный `sortiment/` → `<uuid:pk>`+подпути →
`p/<slug>` → `<slug>` (категория, name="storefront-category") → `<slug>/<slug>`
(товар). `<uuid:...>` строгий — товар по UUID выигрывает у slug-паттерна.

## Батч 1 — KAT-1 (категория=страница, шаблоны) + KAT-2 (комбо) + KAT-6 (демо-слаги)

**KAT-1.** `product_list(request, slug=None)`: категория из пути (unknown → 404)
или из `?kategorie=` (легаси, unknown → redirect как было); фильтр провайдера —
мердж `{**request.GET.dict(), "kategorie": slug}`; для path-варианта `kategorie`
ВЫЧИЩАЕТСЯ из carry (`_facets`/`filter_form_hidden`) — ссылки/формы бьют в
текущий путь. Выдача категории включает товары ПРЯМЫХ детей
(`Q(category__slug=..) | Q(category__parent__slug=..)` в CatalogFacets —
категория-контейнер больше не пустая; осознанная смена семантики, замок).
Шапка — партиал `_category_header.html` (разобранный category_landing.html:
hero-split, галерея, CTA заявки; CTA «Menu» умирает — сетка на этой же
странице). `landing_ready` → «есть контент шапки» (parent→False снимается —
подкатегория с фото/описанием тоже получает шапку). Тумблер
`category_landings` умирает (normalize ДРОПАЕТ ключ, прецедент classic_ui).
SEO: `_PAGE_MAP` += storefront-category; sitemap += страницы категорий.

**Шаблоны категории (опция админа).** `Category.page_style` (⚠️ миграция
`catalog/0027`, CharField blank default "" — образец `variant_style`/
`discount_style`), реестр `apps/catalog/category_styles.py`:
- `""` **Standard** — байт-в-байт прежний вид фильтра (замки целы);
- `kopfbild` **Mit Kopfbild** — hero-шапка (фото+описание+CTA) + подкатегории
  фото-плитками (`_category_tile`) → сетка;
- `sets` **Sets & Menüs zuerst** — полоса комбо-карточек НАД сеткой + шапка при
  контенте;
- `preisliste` **Preisliste** — прайс-вид для ЭТОЙ категории (реюз
  `_price_list`, глобальный catalog_layout не трогается).
Select в `CategoryForm` (generic-цикл шаблона подхватит сам) + help_text.
Демо: spec категорий китов += опц. `page_style` (catering: hochzeit=sets,
buffets=kopfbild …).

**KAT-2.** `_combo_card.html` — партиал из combos.html:12-24, реюз в /kombi/ +
категfrance+тизере каталога (сейчас три копии разметки). На странице категории —
полоса «Sets & Menüs» из `category.combos` (лимит 6, гейт `not cursor и не
активны фасеты` — на «Show more» не дублируется); при style=sets — над сеткой,
иначе после (listing_after). `/kombi/` += `?kategorie=`. Замок
`test_combos.py:113` («тизер скрыт в категории») переписывается осознанно.

**KAT-6.** `_make_category` без `demo-` + общий `unique_slug` util
(перенос `CategoryForm._unique_slug` в `apps/catalog/slugs.py`; сидер обязан
суффиксовать — иначе recreate на схеме с ручными категориями падает на
constraint). Правятся: привязка комбо (`demo_kits:10260`), nav-таргеты
(1079/1084/1130/1131/4217-19), hero-кнопки (1307/1314/1520 + БИТЫЕ уже сегодня
3002/3458 «torten/grill» — чинятся снятием префикса), тесты test_demo_kits
(:95/:98/:220/:352-3/:368/:390-1). Легаси demo.py не трогаем.

## Батч 2 — KAT-3 (SEO-слаги товаров, ⚠️ миграция catalog/0028)

`Product.slug` (SlugField 140, blank default "") + автогенерация в
`Product.save()` при пустом (единая точка — закрывает форму/импорт/демо/мастер/
фабрики; прецедент ProductVariant.label) + бэкфилл data-миграцией (fильтр
`deleted_at__isnull=True` ЯВНО — AliveManager не use_in_migrations) + partial
constraint `uniq_product_slug_alive` c `~Q(slug="")`. Слаг стабилен после
создания (переименование URL не меняет — прецедент Collection). URL:
`get_absolute_url()` на модели (категория есть → `<cat>/<slug>`, нет →
`p/<slug>`), все боевые колл-сайты через него: sellable.py:250 (JSON-LD+buybox
одной правкой), 6 шаблонных мест, sitemap (+slug в values), фид (callable),
письма waitlist/post-purchase (select_related), редиректы отзывов/anprobe/
waitlist/quick-add. UUID-роут живёт (демо-письма/QR). POST-подпути
(warteliste/bewerten/...) остаются на pk.

## Батч 3 — KAT-4 (плотность посетителю) + KAT-5 (без перезагрузки)

**KAT-4.** Контрол «− N +» (2..6, только десктоп, localStorage) в двух местах:
- Kacheln-вид прайса: меняет `data-plv-cols` (CSS-варианты 2..6 уже есть с MEN-25);
- карточная сетка каталога/категории: `data-density="N"` на `[data-grid]` +
  рукописные CSS-оверрайды колонок на lg (Tailwind-классы владельца — стартовое).
Настройка владельца остаётся стартовым значением; сброс = его значение.

**KAT-5.** Клик по `a[data-ansicht]` перехватывается: `fetch` полного HTML →
DOMParser → подмена контейнера листинга (тулбар+сетка/прайс+пагинация) +
`history.pushState` — ноль серверных правок, работает для ВСЕХ видов (karte/
buch), URL остаётся шарябельным; фолбэк — обычная навигация (сеть/ошибка).
Паттерн — двойная буферизация редактора/фрагменты `?box=1`.

## Гейты и порядок

Каждый батч: план→код→замки (характеризационные ДО сводов разметки)→ruff→
`npm run build:css` последним→стенд Playwright (демо catering+shop)→push→CI→
FF-merge. Миграции: `catalog/0027` (батч 1) + `catalog/0028` (батч 2) —
аддитивные; в очередь CLAUDE.md. ops после деплоя: `seed_demo_tenants
--recreate` (слаги без demo-, page_style демо). i18n: новые msgid ×5 .po
(шаблоны категории, «Alle Sets», плотность aria).
