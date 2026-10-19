# T-8.10b «Акция из сообщения в Telegram» — план (2026-10-19)

Родитель: `docs/t8-10-rest-plan-2026-10-19.md §4`. План — агент planner (сверено с кодом).
**Статус (2026-10-19): B-1 ✅ (+ правки ревью); дальше B-2, B-3.**
Решение владельца A-2: Telegram — равноправная опция наравне с веб-ассистентом T-8.4. **Миграций нет.**

## 0. Факты из кода, меняющие план

| Факт | Где | Следствие |
|---|---|---|
| Webhook подписан на `["message","my_chat_member"]` | `telegram/services.py::set_webhook` | `callback_query` не доходит → расширить `allowed_updates` + **перерегистрировать webhook у всех ботов** (команда `telegram_resync_webhooks`) |
| `handle_update` начинается с `update.get("message")` | `telegram/webhook.py` | маршрут callback — первым |
| `owner_chat_id` в `site_config["notify"]` строкой | `telegram/notify.py` | сравнивать `str()`; перепривязка бота убивает черновики — так и надо |
| `get_file_url()` нигде не вызывается | `services.py` | своё скачивание: лимит размера, поток, токен бота (в URL) не логировать |
| Webhook всегда 200 | `public_views.py` | тяжёлое — в Celery, дедуп по `update_id` |
| Конвейер `QuickPromotionForm` → `build()` → фото → `save()` → `limits.activate()` живёт во вьюхе | `promotions/quick.py`, `views.promotion_quick` | вынести в общий `publish_from_form` |
| Срок — чипы today/weekend/week/date, конкретного часа нет | `quick.term_end` | скрытое `until_time` (пусто = байт-в-байт прежнее) |
| `limits.activate` бросает `ActivationLimit` | `promotions/limits.py` | лимит 5 работает даром |
| `ai_draft.draft_from_photo` + `clean_draft` — только описательные поля | `promotions/ai_draft.py` | B-2 зовёт напрямую |
| `ptc.for_promotion` работает с несохранённой акцией | `promotions/text_check.py` | подсказки в превью |
| Read-only неоплаченной подписки — только middleware кабинета | `billing/middleware.py` | явный гейт `GATED_STATUSES` в ветке бота |
| `match_own_product(noun, title)` — только уникальное совпадение | `ai_draft.py` | правила привязывают свой товар без дублей |

## 1. Поток

```
POST /tg/<secret>/ → webhook.handle_update
  ├ callback_query            → telegram_promo.handle_callback (синхронно)
  ├ group/supergroup          → мост community (без изменений)
  ├ "/start…"                 → как раньше
  ├ private ∧ chat.id==from.id==owner_chat_id ∧ ¬is_bot → enqueue_owner_message → Celery
  └ иначе                     → прежний ответ «Tap below to open the shop.» (байт-в-байт)

Celery telegram_owner_message(schema, update) [idempotent, dedupe tgmsg:<schema>:<update_id>]
  гейты (модуль promotions, подписка, rate-limit) → message_parse.parse (B-1)
  → фото: file_ids (B-2: draft_from_photo только в пустые описательные поля)
  → match_own_product → черновик в кэше tgpromo:draft:<schema>:<chat>:<token> (24 ч)
  → превью sendPhoto/sendMessage + [✅ tp:ok][✏️ url /promotions/schnell/?entwurf=][❌ tp:no]

✅ → cache.add(tgpromo:done:<schema>:<token>) → publish_from_form (та же форма T-8.4 → лимит → Text-Check)
❌ → удалить черновик, снять клавиатуру; ✏️ → веб-форма с префиллом, POST ставит тот же done-замок
```
Брокер недоступен → синхронный ответ «Gerade nicht möglich — bitte später erneut senden».

## 2. Файлы
- `telegram/services.py`: `allowed_updates += callback_query`; `answer_callback_query`,
  `edit_message_reply_markup`, `send_photo` (caption ≤ 1024), `download_file(max 10 MB, stream, без URL в логах)`.
- `telegram/webhook.py`: callback первым; `_is_owner_private`; знания об акциях — не здесь.
- `telegram/management/commands/telegram_resync_webhooks.py`: dry-run / `--apply`.
- `promotions/message_parse.py` (чистые функции): `parse(text, tenant, now) -> Parsed`
  (title, description, new_price, old_price, percent, quantity, term, until, until_time, warnings, signals).
- `promotions/telegram_promo.py`: enqueue/handle, черновики (store/load/drop/load_for_web), превью,
  callback, confirm, `bot_locale` (`from.language_code` ∈ CABINET_LANGUAGES, иначе `tenant_locale()`),
  `owner_user`; B-3 repeat.
- `promotions/tasks.py`: `telegram_owner_message` (в брокер — только нужные поля апдейта).
- `promotions/quick.py` + `views.promotion_quick`: `publish_from_form(...)` (вынос, паритет T-8.4),
  поля `until_time` (Hidden TimeField; прошедшее сегодня → ошибка) и `entwurf` (GET префилл; POST
  скачивает фото из Telegram; done-замок).

## 3. Правила разбора (B-1), фрагменты «съедаются» по порядку
1. Дата `bis 31.10.[2026]`/`до 31.10` (только после маркеров или с точкой; прошедшая → след. год, `date_rolled`).
2. Время `bis 18 Uhr`/`18:30`/`до 19:00`/`until 6pm`/`saat 18:00'e kadar` (прошло → `time_past`).
3. Относительный срок: heute/bis Ladenschluss/сегодня/today/bugün · morgen · Wochenende ·
   bis <день недели> · N Tage (≤60) / eine Woche; нет → `quick.default_term`.
4. Процент 1…99 (`%`, `prozent`, `процент`, `off`, `indirim`, `%25`).
5. Цены с маркерами (statt/vorher/UVP/вместо/было/instead of/yerine → old; für/nur/jetzt/ab/за/только/
   for/only/sadece или с €/EUR → new); две суммы без маркеров: меньшая new, большая old.
6. Голая `\d+,\d{2}` → new.
7. Количество `N Stück/Stk/x/pcs/шт/adet`, `nur noch N`, `осталось N` (1…10 000).
8. `2 für 1`/`1+1`/`2. Stück −50 %` — не разбираем, предупреждение `price_condition`.
9. Заголовок = первая строка без съеденного и висячих связок (≤ 80), описание — остальное (≤ 280).
10. Согласование: цена+процент → цена (`price_and_percent`); old ≤ new → old отброшена;
    процент + свой товар → привязка товара.
11. Нет сигнала → подсказка с примером. 12. Пустой заголовок без ИИ → «Wie heißt das Angebot?».

Таблица-тест: Brötchen −30 % bis 18 Uhr, 20 Stück · Erdbeerkuchen 2,50 € statt 3,90 € heute ·
Herbstjacken 20% bis Sonntag · Haarschnitt nur 19 € am Wochenende · Tomaten 1 kg 1,99 ·
Pizza 4 Käse 8,50 € statt 10 € · Sale -50% bis 31.10. · Kaffee 2 für 1 · Croissants 30% off until 6pm, 15 pcs ·
Пирожки −20% до 19:00, 10 шт · Simit %25 indirim bugün · Ruf an: 0212 123456 · Kuchen 3,50 € −20 %.

## 4. Черновик, превью, callback
- Кэш, TTL 24 ч, token `secrets.token_urlsafe(12)`; только поля формы + `photo_file_ids`, без байтов.
- Альбом: индекс `media_group_id` (10 мин), превью один раз.
- Превью без `parse_mode`; черновик прогоняется через форму — невалидна → нет ✅, ошибка текстом;
  ≤ 3 подсказки Text-Check; «Limit 5/5 — ✅ speichert als Entwurf».
- Callback: сразу `answerCallbackQuery`; `from.id == message.chat.id == owner_chat_id` иначе «Nicht erlaubt.»;
  строгий regex `^tp:(ok|no|rp):…$`; гейты; `ok` — done-замок (pk / pending), повтор формы,
  фото через `reencode` (без EXIF), `atomic` publish, «✅ Live: <url>» + 📤/🔁; `ActivationLimit` → черновик.

## 5. Безопасность
Только владелец (частный чат, chat.id == from.id == owner_chat_id, повтор в callback); токен в ключе
(schema, chat); гейт подписки и модуля; rate-limit 30 черновиков/час + ИИ-лимиты AI-0; текст владельца
только в черновике 24 ч; URL файла не логируется; числа только из правил или БД; ответ ИИ — данные.

## 6. Замки ДО кода
`telegram/tests/test_owner_promo_routing.py` (клиентский чат байт-в-байт, /start, группа, dedupe,
чужой callback, allowed_updates, skip) · `promotions/tests/test_message_parse.py` (таблица + негатив) ·
`test_telegram_promo.py` (двойной ✅ = одна акция, лимит 5, ✏️ затем ✅, ❌, перепривязка, подписка/модуль,
Text-Check, percent+old, прошедшее время, фото, i18n, rate-limit, брокер) · `test_quick_entwurf.py`
(префилл, паритет T-8.4) · B-2 `test_telegram_promo_ai.py` · B-3 `test_telegram_promo_repeat.py`.

## 7. Инкременты
- **B-1** a транспорт → b парсер → c черновик/превью/✅❌✏️/фото без ИИ/Text-Check/лимит.
- **B-2** ИИ по фото: только пустые title/description/city_category/tags; фото без подписи — вопрос
  (ИИ выключен) или черновик без цены; `metadata["ai_draft"]`.
- **B-3** `/wiederholen` + «🔁 Nochmal»: 3 последние прошедшие акции, `initial_from`, `copy_images`.

## 8. Ops после деплоя
`./scripts/deploy.sh single` → `python manage.py telegram_resync_webhooks` → `--apply` → проверка на демо.

## 9. Вне v1
Голос (Р-10), WhatsApp, `edited_message`, условия цены, выбор отклика кнопками, `/heute`.

Решение по умолчанию (оспоримо): ветка владельца включена для любого привязанного владельца без тумблера.
