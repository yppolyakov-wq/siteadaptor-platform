# X4 — подпункты по смыслу, сироты и глоссарий (план + разведка)

Дата: 2026-08-19. Волна X4 программы `docs/cabinet-cleanup-plan-2026-08-19.md` §6.A4.
Ветка: `claude/personal-cabinet-research-byjuc4`. Без миграций.

## 1. Что нашла разведка (факты, на которых стоит план)

1. **`sidebar_children` = `advanced`-состав хабов** (`nav_registry.sidebar_children`).
   То есть «подпункт сайдбара» и «вкладка в ящике Erweitert» — сегодня ОДНО И ТО ЖЕ
   множество. Отсюда подпункты «Angebote» = Produkte · Kategorien · **Lager · Einkauf ·
   Kombi · Import** · Kollektionen: у парикмахера в подпунктах его «товаров» висит
   складская группа, а «Leistungen» нет вовсе (экран — сирота).
2. **`hub_tabs "board"` не рендерится ни одним шаблоном** (W10-3 снял огрызок).
   Записи board-хаба живут ради палитры/подсветки и подпунктов сайдбара — значит
   перекладывать записи между board и sellables безопасно для таб-баров.
3. **Все страницы booking эмитят `nav="booking"`, все stays — `nav="stays"`**, а
   `_EXTRA_NAV_ANCHORS` жёстко ведёт оба ключа на якорь «Verkäufe». Поэтому просто
   «положить Leistungen/Zimmer в Sortiment» мало: подсветка осталась бы на Verkäufe
   (ровно тот дефект «где я», который волна и чинит). Нужны свои `nav`-ключи у
   сущностных экранов (`services`/`units`/`passes`).
4. **KDS и Tisch-QR** выводятся кнопками в `core/_sales_body.html` при `kind=order`
   для ЛЮБОГО архетипа с модулем orders (парикмахер видит «Kitchen Display»).
   `FOOD_BUSINESS_TYPES` уже есть — `apps/catalog/views.py`.
5. **`finance:invoices`**: заголовок «Rechnungen» в шаблоне БЕЗ `{% trans %}` —
   попутный i18n-дефект, чиним здесь же (msgid всё равно нужен для записи реестра).

## 2. Механика: три новых поля `NavEntry`

| Поле | Смысл | Зачем |
|---|---|---|
| `sidebar: bool = True` | `advanced`-запись показывается подпунктом якоря | развязать «ящик Erweitert» и «подпункты сайдбара» (склад остаётся в ящике, из сайдбара уходит) |
| `palette_only: bool = False` | запись только в Ctrl+K (не в табах, не в подпунктах) | сироты получают вход, таб-бары не раздуваются (требование плана §6.A4.3) |
| `business_types: tuple = ()` | доп-гейт по типу бизнеса | KDS/Tisch-QR только гастро (§6.A4.5) |

Потребители: `legacy_hub_tabs()` (исключает `palette_only`), `sidebar_children()`
(`advanced and sidebar and not palette_only`), `hub_tabs`/`nav_palette`/`sidebar_nav`
(гейт `business_types`). Реестр остаётся статичным и lazy.

## 3. Целевой состав подпунктов

**Sortiment** (сущности архетипа): Produkte [catalog] · Leistungen [booking] ·
Zimmer & Preise [stays] · Veranstaltungen [events] · Reisen [events] · Kategorien
[catalog] · Kollektionen. Складская группа (Lager/Einkauf/Kombi/Import) —
`sidebar=False`: достижимость прежняя (ящик «Erweitert» таб-бара каталога), шума в
сайдбаре нет.

**Verkäufe** (рабочие входы, потом отчёты): Öffnungszeiten & Ressourcen [booking] ·
Tage blockieren [booking] · Check-ins [stays] · Kitchen Display [orders, гастро] ·
Abläufe · Auswertungen [analytics] · Finanzen [finance] · Berichte [stays].

`events:list`/`events:tour-list` ПЕРЕЕЗЖАЮТ из board-хаба в sellables (событие и тур
— продаваемая сущность; в Verkäufe остаётся вкладка сделок «Tickets»). Побочно
`nav="events"`/`"tours"` начинают подсвечивать «Sortiment» — это и есть целевое
поведение глоссария.

## 4. Классификация сирот (снимаются из `EXPECTED_UNLISTED` категории [X4])

| url_name | Решение |
|---|---|
| `booking:services` | подпункт Sortiment «Leistungen» + свой `nav="services"` |
| `stays:units` | подпункт Sortiment «Zimmer & Preise» + `nav="units"` |
| `booking:resources` | подпункт Verkäufe «Öffnungszeiten & Ressourcen» |
| `booking:availability` | подпункт Verkäufe «Tage blockieren» |
| `stays:checkins` | подпункт Verkäufe «Check-ins» |
| `orders:kitchen` | подпункт Verkäufe «Kitchen Display», гейт гастро |
| `orders:table-qr` | палитра «Tisch-QR», гейт гастро |
| `booking:passes` | палитра Sortiment «Karten & Abos» + `nav="passes"` |
| `events:teacher-list` | палитра Sortiment «Gastgeber» |
| `stays:channels` | палитра Verkäufe «Channel Manager» |
| `promotions:reservation-list` | палитра Verkäufe «Reservierungen» |
| `finance:invoices` | палитра Verkäufe «Rechnungen» |
| `jobs:anfrage-form-settings` | палитра Verkäufe «Anfrage-Formular» |
| `crm:company-list` | палитра Marketing «Firmen» |
| `billing-payments` | палитра Einstellungen «Zahlungen empfangen» (owner-only) |
| `billing-portal` | НЕ экран: редирект в Stripe-портал → категория [302] |
| `orders:kitchen-board` | НЕ экран: HTMX-партиал поллинга → [POST] |
| `promotions:shop-poster` | НЕ экран: генератор PDF → [DOC] |
| `stays:stay-new` | форма создания, вход — «＋» поверхности продаж → [＋] |

**Параметризованные** экраны плана (`status-manager/<kind>`, логистика/документы
заезда) в инвентаризацию X7.3 не попадают (reverse требует аргумент) и остаются
входами со своих родительских страниц — зафиксировано здесь, чтобы не искать заново.

## 5. Глоссарий (только подписи, URL целы)

- якорь и хаб «Angebote» → **«Sortiment»** (слово «Angebot» остаётся за офертой
  клиенту: Sofort-Angebot, смета Handwerker);
- `events:list` «Tickets» → **«Veranstaltungen»** (снимает коллизию с вкладкой сделок
  «Tickets» в Verkäufe);
- jobs: «Angebot PDF» → **«Kostenvoranschlag PDF»**;
- файл-словарь `docs/cabinet-glossary.md` — одно слово = одна сущность.

## 6. Замки

Осознанные переписки: `test_sidebar_children_composition` (состав подпунктов —
целевой), `test_x0_x7_locks.EXPECTED_UNLISTED` (категория [X4] пустеет).
Новые: подпункты по архетипу (парикмахер видит Leistungen и не видит склад;
отель — Zimmer & Preise/Check-ins), гейт гастро для KDS/Tisch-QR (парикмахер их не
видит ни в палитре, ни на поверхности продаж), палитра содержит бывших сирот.
