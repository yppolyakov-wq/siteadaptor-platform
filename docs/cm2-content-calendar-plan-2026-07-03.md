# CM-2 — контент-календарь + отложенная публикация (план до кода, 2026-07-03)

Второй инкремент контент-хаба (`market-content-analysis-2026-07-02.md` §3).
Разведка агентом, факты сверены с кодом.

## 1. Ключевые факты разведки

- `Publication` — ДОСТАВКА в канал (FK promotion+channel, статусы queued/published/
  removed/failed через FSM, dedupe_key unique, external_ref, last_error), создаётся
  ТОЛЬКО side-effect'ом перехода `Promotion→active` (`publishing/services.py`).
  `scheduled_at` нет; «отложенность» существует только на уровне Promotion
  (beat `roll_promotion_statuses`, 300с). Ретраев нет (failed → ручная реактивация).
- Контент постов генерится из Promotion в адаптерах (`_promo_caption`/
  `_promo_image_url`/`_promo_public_url`); GBP/FB/IG/TG/Pinterest; конфиги в
  `Channel.config` (секреты шифруются), по одному каналу типа на тенант.
- Кабинет — только `channels.html` (тумблеры+конфиги+последние 20 публикаций).
  Составления поста/выбора времени НЕТ. `BlogPost.published_at` уже существует.
- Beat: статический `CELERY_BEAT_SCHEDULE` в base.py; паттерн — helper с чистой
  логикой + beat-обёртка, итерирующая схемы (`_iter_tenant_schemas`).

## 2. Дизайн

**Разделение:** `SocialPost` = ЧТО постим (свой контент: текст, фото-FileRef,
ссылка, `scheduled_at`); `Publication` = доставка в конкретный канал (существующая
механика реюзается целиком: FSM/dedupe/adapters). Publication обобщается:
`promotion` становится nullable + новый nullable FK `post` (CheckConstraint —
ровно один источник). Контент в адаптерах — через единый резолвер
`content_for(pub) → (caption, image_url, link_url)` (промо-ветка = прежние
хелперы 1:1). Шов CM-3: `SocialPost.source_kind/source_id` (blank) — авто-посты
из сущностей платформы лягут сюда без новой модели.

**Блог:** отложенная публикация БЕЗ новых полей — `blog_edit` получает
«Veröffentlichen am»: будущая дата → `is_published=False, published_at=<дата>`;
beat включает `is_published=True` при наступлении. (Семантика published_at
расширяется: у черновика с датой — «когда опубликовать»; у published — как было.)

**Beat:** один таск `send_due_content` (300с, по образцу roll_promotion_statuses):
(а) SocialPost `status=scheduled, scheduled_at<=now` → создать Publications по
включённым каналам (реюз паттерна `_publish_all`, dedupe `publish:post:{id}:{ch}`)
→ status=sent; (б) BlogPost `is_published=False, published_at<=now, published_at
не NULL` → опубликовать. Чистые helpers `send_due_posts(now)`/`publish_due_blog(now)`.

**Статусы SocialPost** (FSM, по конвенции): draft → scheduled → sent (+ failed
не нужен — доставка отслеживается на Publication per-канал; «Jetzt senden» =
scheduled_at=now).

## 3. Слайсы

- **A. Модель+миграция:** `SocialPost` (text, image JSONField-FileRef, link_url,
  scheduled_at, status, source_kind/source_id — шов CM-3) + Publication:
  promotion nullable, `post` FK, CheckConstraint XOR, UniqueConstraint
  (post, channel) при post NOT NULL; `content_for(pub)` в adapters (промо 1:1,
  снапшот-паритет текста промо-постов); миграция publishing/0005 (⚠️ гейт
  --create-db). SM: `SocialPostSM`.
- **B. Beat:** `send_due_content` + helpers + расписание в base.py + сервис
  `publish_post(post)` (реюз очереди Publications). Тесты helpers напрямую.
- **C. Кабинет «Beiträge»** (`/dashboard/posts/`): список постов по датам
  (Geplant/Gesendet/Entwurf), форма: текст, фото (upload через save_product_image),
  ссылка, datetime-local, «Planen»/«Jetzt senden»/löschen. NavItem — в модуль
  publishing (страница channels там же). Блог-форма += «Veröffentlichen am».
- v2 (НЕ сейчас): выбор каналов per-пост (v1 — все включённые, как у промо),
  календарь-грид, ретраи доставки.

## 4. Замки/тесты

Существующие publishing-тесты (пайплайн промо 1:1 — снапшот-паритет caption);
новые: XOR-constraint, content_for обеих веток, send_due_posts (due/будущее/
draft), publish_due_blog, кабинет CRUD+planen, blog_edit будущая дата.

## 5. Риски

- Обобщение Publication — горячая точка: существующие переходы промо-пайплайна
  не трогаем (services.on_promotion_transition без изменений).
- Adapters: IG/Pinterest требуют фото — пост без фото в эти каналы должен падать
  понятной ошибкой на Publication (как у промо без фото), не ронять beat.
- `_promo_public_url` для постов: link_url поста может быть пуст → пост без
  ссылки (адаптеры это уже умеют? промо-ссылка всегда есть — проверить ветки).
