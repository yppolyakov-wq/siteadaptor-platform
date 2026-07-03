# CM-1 — блог/новости first-class для всех архетипов (план до кода, 2026-07-03)

Первый инкремент контент-хаба (одобренный стек: U-C → CM-1..5;
`market-content-analysis-2026-07-02.md` §3). Разведка агентом, факты сверены.

## 1. Ключевые факты разведки

- `BlogPost` (apps/events/models.py:638) **полностью самостоятелен**: только
  TimestampedModel, ни одного FK на Event; миграция 0020 — чистый CreateModel.
  Привязка к events — организационная (файл/кабинетный URL/сидер), не по данным.
- Публичные `/blog/`-вьюхи **уже НЕ гейтятся** (нет `_require_events_active`;
  middleware матчит только `/dashboard/events/`); тесты это подтверждают.
- Кабинетный CRUD — под `/dashboard/events/blog/` → гейт модулем events через
  `ModuleGatingMiddleware`; отдельного пункта меню кабинета НЕТ (достижим только
  прямым URL). Сидер `_seed_blog_posts` гейтится `is_module_active("events")` —
  поэтому у friseur-кита блога нет (ровно боль CM-1).
- Модуля `"blog"` в `apps/core/modules.py::REGISTRY` нет. Меню витрины: блог —
  только ручной url-узел (`{"type":"url","target":"/blog/"}`, есть в retreat-ките).
- SEO-гэпы: постов нет в sitemap; нет BlogPosting JSON-LD.

## 2. Решение: модуль «blog» БЕЗ переноса модели (без миграций)

Модель физически остаётся в apps/events (перенос в новый apps/blog = миграция
данных ради эстетики — отложено до реальной нужды). First-class достигается
регистрацией модуля и развязкой кабинета/сидера:

1. **ModuleSpec `"blog"`** в REGISTRY: не-core, не-premium, `recommended_for` —
   ВСЕ типы бизнеса (= активен у всех по умолчанию, выключается на «Module»;
   у существующих тенантов появляется сразу — хранится «выключенное»).
   `url_prefixes=("/dashboard/blog/", "/blog/")` — витрина тоже гейтится
   тумблером (выключил модуль → /blog/ 404). NavItem кабинета → blog-list
   (закрывает разведанный пробел «нет пункта меню»).
2. **Кабинетные маршруты** переезжают `/dashboard/events/blog/` →
   `/dashboard/blog/` (имена `blog-list`/`blog-edit` в urls_tenant; ссылки в
   blog_list/blog_edit-шаблонах и тестах обновить). Вьюхи остаются в
   apps/events/views (алиасы не нужны — кабинетный URL внутренний).
3. **Сидер**: гейт `_seed_blog_posts` → `is_module_active("blog")`; friseur-кит
   получает 2-3 «Neuigkeiten»-поста + url-узел «News» в меню (демо «блог без
   событий»). Retreat не трогаем (blog у него активен по умолчанию).
4. **SEO (в объёме CM-1 — его ценность и есть локальное SEO):** посты в
   `sitemap_xml` (published) + `BlogPosting` JSON-LD в blog_detail.html
   (headline/datePublished/image/описание; хелпер в core.seo).
5. **НЕ делаем:** NAV_ITEMS-запись (нав-шум у тенантов без постов; ссылка —
   узлом меню, как сейчас в китах), i18n блога (кандидат L-волны), перенос
   модели, «Neuigkeiten»-алиас URL (оставляем /blog/).

## 3. Замки/тесты

Существующие: `apps/events/tests/test_blog.py` (7). Новые: реестр («blog»
не-premium, recommended-везде), гейт middleware `/blog/` + `/dashboard/blog/`
при выключенном модуле, сидер friseur (посты БЕЗ events-модуля), sitemap
включает published-посты, BlogPosting JSON-LD на детали.

## 4. Риски

- `default_disabled_for` у СУЩЕСТВУЮЩИХ тенантов не пересчитывается (хранится
  «выключенное») → blog активен у всех сразу — это и есть цель; шум невозможен
  (в nav сам не лезет).
- Гейт `/blog/` middleware'ом — новое поведение для выключивших модуль
  (раньше негейтился) — осознанно: тумблер должен работать.
