# SEO-модуль v2 — план (2026-07-08)

Трек #1 владельца (после закрытия склад-леджера/редактора). Идея —
`roadmap-next-sprints.md §SEO-модуль v2`. **Требует согласования объёма перед
стартом** (примечание идеи). Ниже — фазовая разбивка SEO-1…SEO-4 для выбора.

## 0. Что уже есть (не дублируем)
- `_base.html`: блоки `title`/`meta_description`/`og`/`structured_data`;
  per-шаблон override; дефолт = `tenant.name` (бедный).
- `apps/core/seo.py`: JSON-LD билдеры (LocalBusiness/Offer/entity=Product/Service/
  Event/Lodging + AggregateRating, ItemList, BreadcrumbList, BlogPosting,
  CollectionPage). Per-entity JSON-LD уже на детальных (UA4-4b/UC4-2).
- sitemap/robots — есть (urls_public/portal/tenant), aggregator sitemap.
- **Гэп:** владелец НЕ управляет title/description/OG; нет плейсхолдеров, нет
  per-тип шаблонов, нет live-превью, нет llms.txt, нет FAQPage/AI-краулер-контроля.

## 1. SEO-1 — движок мета-заготовок (бэкенд + резолвер) [ядро]
- Плейсхолдер-рендер `{name}`/`{price}`/`{city}`/`{category}`/`{tenant}`/`{count}`.
- Per-тип шаблоны (home/listing/detail/category) title+description+OG в `site_config`
  (БЕЗ миграции; ключ `seo.templates`). Per-сущность override (на детальных — из
  контракта SellableEntity/полей).
- Резолвер `apps/core/seo_meta.py::resolve(page_type, ctx)` → {title, description,
  og_title, og_description, og_image}; фолбэк: override → шаблон тип-а → архетип-дефолт
  → tenant.name. Архетип-дефолты (ничего не настроил → уже хорошо).
- Провод в `_base.html` через контекст (context processor `seo_meta` или per-view);
  клампы длины (title ~60, description ~155), экранирование.
- Замки: резолвер (плейсхолдеры/фолбэки/клампы), рендер тега на 3-4 страницах.

## 2. SEO-2 — кабинет + live-превью сниппета [UI]
- Вкладка «SEO» (в билдере или настройках): редактор шаблонов per-тип, помощник
  плейсхолдеров, **live-превью Google-сниппета** (title/URL/description) + OG-карточка.
- Прогрессивно: Простой (один переключатель «хорошие дефолты») / Эксперт (шаблоны).

## 3. SEO-3 — AI-SEO / GEO [дифференциатор]
- `llms.txt` на витрине тенанта (роут + генерация из бизнес-данных/каталога).
- Расширение JSON-LD: **FAQPage** из FAQ-секций (UA4-3), Offer/PriceSpecification
  (частично есть — довести на листингах/деталях).
- **Контроль AI-краулеров** (GPTBot/ClaudeBot/PerplexityBot/Google-Extended) в
  per-tenant robots.txt — тумблер «разрешить/запретить ИИ» в кабинете.

## 4. SEO-4 — прогрессивные дефолты + полировка [хвост]
- Архетип-специфичные дефолты мета (пекарня/отель/…); Open Graph картинка-фолбэк
  (лого/hero); канонические URL; hreflang для мультиязычных (L-волна) — при спросе.

## 5. Порядок/оценка
SEO-1 (ядро, средний) → SEO-2 (UI, средний) → SEO-3 (AI, средний, дифференциатор) →
SEO-4 (хвост, малый). Всё БЕЗ миграций (site_config). Каждая фаза — свой батч/CI/merge.
**Первый кандидат** (из идеи): мета-title листингов услуг/номеров.

## 6. Развилки на согласование
- **Объём v1:** SEO-1+SEO-2 (управляемые мета + превью) — минимально ценно; или
  сразу +SEO-3 (AI-SEO — рыночный дифференциатор DACH).
- **Где вкладка SEO:** в билдере (⚙️ Шаблон) или в `/dashboard/settings/`.
- **Хранение:** site_config (без миграции) — предлагаю так; модель — только если
  понадобится per-entity SEO с историей (пока не нужно).
