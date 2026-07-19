# LS-1 «Video-Beratung по записи» — план (2026-07-19)

Этап A2 ТЗ `docs/next-gen-master-tz-2026-07-19.md §3`. v1 = **WhatsApp-видео**
(94 % DACH-проникновение, нулевой порог): услуга помечается «видео», бронится
ОБЫЧНЫМ booking-движком (слот держит таймслот), клиент получает в
подтверждении/напоминании ссылку `wa.me/<номер>` с pre-filled текстом.
**§201 StGB: никакой записи разговоров — мы только открываем чат.** Разведка —
фоновый Explore 2026-07-19 (все точки перепроверены им по коду).

## 1. Развилка «флаг is_video» — РЕШЕНИЕ: миграция BooleanField

ТЗ допускало «флаг в metadata, чтобы избежать миграции», но у `booking.Service`
НЕТ свободного dict-JSON: `attributes`/`faq` типизированы под показ карточки
(list[str] / list[{q,a}]) — магическая строка в них попала бы в UI. Вариант
site_config-списка `video_service_ids` НЕ бесплатен: ключ пришлось бы явно
проводить через `normalize()` + синхронизировать при удалении услуг. Булевы
флаги на Service добавлялись миграциями рутинно (counts_party_size,
require_manual_confirm…) → **`Service.is_video` (default False, аддитив)**.

Второе поле: **`Tenant.whatsapp_number` (SHARED, CharField blank)** — рядом с
contact_phone. site_config-обход (как telegram `notify`) отвергнут: номер должен
переживать normalize честно, и это обычный контакт бизнеса. Пусто = видео-CTA
нигде не показывается (явный opt-in владельца).

⚠️ Две миграции: `booking/00XX` (+is_video) и `tenants/0027` (+whatsapp_number)
— обе аддитивные, в общую очередь деплоя.

## 2. Хелпер

`apps/core/whatsapp.py::wa_link(number, text="") -> str` — нормализация в
digits (`+49 171…` → `49171…`), `https://wa.me/<digits>?text=<urlencode>`;
пустой номер → "". Единый строитель (сейчас wa.me один раз inline в
`promotion_detail.html:69`); LS-2 «Jetzt erreichbar» реюзает его следующим
инкрементом.

## 3. Точки врезки (все — из разведки)

- **Кабинет:** `whatsapp_number` в `BusinessSettingsForm` (fields/labels/
  help_text; форма настроек W4 — блок контактов). Чекбокс «📹 Video-Beratung
  möglich» в форме услуги (plain-POST create/update в `apps/booking/views.py`).
- **Витрина, деталь услуги:** НОВАЯ скрываемая секция `video` в
  `DETAIL_SECTIONS["booking"]` (`apps/core/detail_sections.py`) + шаблон
  `sections/detail/_service_video.html` (по образцу `_service_attributes`):
  «📹 Per Video zeigen lassen» — кнопка-ссылка wa.me с текстом «Video-Beratung:
  <услуга>» + строка «kein Termin nötig — oder Termin buchen» (CTA брони уже в
  buybox). Врезка в `_present`/`_section_template` (`booking/public_views.py`):
  present = `service.is_video and tenant.whatsapp_number`; скрытие — существующий
  механизм hidden-секций билдера (UA4-1).
- **Письма:** `enqueue_booking_email` — для `confirmed`/`reminder` при
  `booking.service.is_video` и номере: `ctx["whatsapp_url"] = wa_link(number,
  "Video-Termin <дата d.m. H:i> — <услуга>")` (зеркало pay_url/review_url);
  рендер-блок `{% if whatsapp_url %}` в `booking_confirmed.txt` +
  `booking_reminder.txt` (немецкие msgid, L4).
- **Листинг/меню:** фасет `?video=1` в `ServiceFacets` (selected/apply/present)
  — чип «📹 Video-Beratung» появляется на `/termin/` АВТОМАТИЧЕСКИ при ≥1
  видео-услуге (нулевая работа владельца; единый источник = is_video, без
  дублирования в Collection). Пункт меню — опционально узлом типа `url` →
  `/termin/?video=1` (механика menus уже умеет; не автовставляем).

## 4. Чего НЕ делаем (v1)

- Никакой записи/архивации звонков (§201) и никакого своего WebRTC/Jitsi —
  отложено (концепт §6.2); wa.me-линк не хранится, генерится на лету.
- Не трогаем движок брони/слотов/депозитов — видео-услуга ведёт себя как
  обычная (в т.ч. напоминания beat).
- Автопункт меню не вставляем (меню — владельца); чип на листинге даёт
  находимость из коробки.

## 5. Инкременты и замки

1. **Модель+кабинет:** обе миграции, wa_link (+тесты нормализации), поле в
   BusinessSettingsForm, чекбокс в форме услуги. Замки: default False/пусто;
   сохранение формы услуги не трогает прочие поля; настройки сохраняют номер.
2. **Витрина+письма+фасет:** секция video (present-гейт, скрытие через
   builder-hidden), wa.me в confirmed/reminder (ТОЛЬКО видео-услуга с номером —
   обычная бронь письмо байт-в-байт прежнее), фасет+чип. Замки: не-видео
   услуга/пустой номер → секции и ссылки нет нигде; `?video=1` фильтрует;
   письмо видео-брони содержит wa.me и дату.
3. **Финал:** i18n msgid → 4 .po, CSS при новых утилитах, build-log/CLAUDE.md/
   ТЗ-статус A2, CI → FF-merge.

Приёмка ТЗ A2: услуга-видео бронируется ✅, письмо содержит wa.me ✅, записи
нет ✅, секция детали скрываема ✅ (+ чип листинга бонусом).
