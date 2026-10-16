# T-8.26 п.2 — noindex демо · плашка на /entdecken/ · флаг тестовых регистраций (2026-10-16)

План агента planner по пункту 2 `docs/t8-26-audit-fixes-plan-2026-10-16.md`; факты сверены с
`main`. Цикл: замки ДО кода → django-reviewer + security-reviewer → зелёный CI → FF в `main`.

## Факты
- `Tenant.is_demo` → снимок `AggregatorListing.is_demo`; `AggregatorPortal.show_demo`
  (миграция `aggregator/0019` выставила True ВСЕМ существующим порталам → сегодня каждый
  прод-портал = превью). `listings_for(include_demo=…)`: `/entdecken/` зовёт с демо.
- `noindex` нет нигде (`templates/aggregator/_base.html`, `portal_base.html`,
  `templates/storefront/_base.html`). Бейдж «Demo» на карточках есть везде; плашка
  «Vorschau…» (`data-demo-notice`) — только `portal_home`/`portal_discover`.
- На превью-портале демо уходит в sitemap (страницы демо-бизнесов), фид (`demo: true`) и
  llms.txt (разделы/районы по демо). На основном домене машинные поверхности уже без демо.
- `pagecache._pack` хранит тело + Content-Type + Vary: заголовок из вьюхи кэш теряет,
  `<meta>` — переживает. `AggregatorPortalMiddleware` снаружи кэша (декоратор вьюхи).
- «rest» (тестовый недемо-тенант на проде): обычная регистрация даёт `in_city_catalog=True`;
  маркера «внутренний» на Tenant нет; в админке Tenant нет полей видимости.

## Решения
- **Р-1** превью-портал (`show_demo=True`) целиком `noindex,follow`: `<meta>` в `portal_base`
  + `X-Robots-Tag` из middleware (переживает кэш, покрывает фид/llms). robots.txt — `Allow`
  (иначе робот не увидит noindex), без строки `Sitemap:`; sitemap превью = пустой `urlset`.
  ⚠️ Следствие: все прод-порталы выпадают из индекса до снятия `show_demo` в админке —
  это и есть «превью до запуска»; снятие `show_demo` в день запуска включит индексацию.
- **Р-2** `/entdecken/` — постранично через `<meta>`: предложение/бизнес демо → noindex;
  лента/поиск/Finder — noindex, когда НИ ОДНОЙ недемо-карточки; смешанные индексируются.
  Расширение: витрины демо-тенантов (`storefront/_base.html` по `request.tenant.is_demo`)
  → noindex + `Disallow: /` в их robots.txt.
- **Р-3** фид и llms — демо исключаем ВСЕГДА (ассистенты флаг `demo` игнорируют); мета
  `preview: true` остаётся честным признаком.
- **Р-4** плашка на `/entdecken/` — тот же msgid; партиал `_demo_notice.html`, условие
  `shows_demo = any(card.is_demo)` во вьюхе.
- **Р-5** тестовые регистрации — `Tenant.is_internal` (⚠️ миграция `tenants/0037`, SHARED,
  аддитивная): только админка, учитывается в `listable`/`withheld_schemas` (одна точка
  истины, действует сразу). `in_city_catalog` не годится (владелец вернёт галочку сам;
  смысл поля — согласие), `is_demo` — покажет тест на превью с бейджем «Demo».
- **Р-6** автопометка по домену почты — нет (roadmap §Отложено).

## Инкременты
- **2a** noindex + машинные поверхности (без миграций): шаблоны head ×2, middleware,
  `robots_noindex` в 4 вьюхах `/entdecken/` + страница бизнеса, sitemap/robots/feed/llms
  портала, `open_feed.render_feed(preview=…)`, витрина демо-тенанта.
- **2b** плашка: партиал + include в search/listing/index/finder/offer/portal_business
  (portal_home/portal_discover — на партиал байт-в-байт), `shows_demo` в контекстах.
- **2c** `is_internal`: модель+миграция, `visibility`, админка (поля видимости, фильтр,
  `save_model` → `apply_visibility`, action «Als intern markieren»).

## Замки ДО кода — `apps/aggregator/tests/test_demo_hygiene.py`
превью: meta+header noindex, настоящий — нет · sitemap пустой + robots без Sitemap · фид без
демо с preview:true · llms без демо-разделов · `/entdecken/`: демо-предложение/бизнес noindex,
недемо — нет; город только-демо noindex, смешанный — индексируется + плашка · плашка на всех
поверхностях `/entdecken/` при демо-карточках, без них — нет · витрина демо: noindex + robots
Disallow · `is_internal`: listable False, `public()` исключает, страница бизнеса 404, формы
владельца поля не знают, админ-save снимает снимки.
**Переписываются осознанно:** `test_preview_portal_marks_demo` (превью без demo-элементов),
`test_each_condition_withholds` (+is_internal).

## Ops
2a/2b — без миграций и пересева. 2c — `./scripts/deploy.sh single`; в админке пометить
«rest» как intern (до деплоя — shell: `in_city_catalog=False` + `apply_visibility`).
Снять `show_demo` с `solingen.<base>` в день запуска.
