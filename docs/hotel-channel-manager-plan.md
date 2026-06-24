# G11 — Channel Manager (Booking/Expedia/Airbnb) · план

Статус: 🧭 план (2026-06-23). Продолжение `docs/hotel-growth-plan.md` (G1–G10 закрыты).
Принцип прежний: **надстройка над `apps.stays`** (StayUnit/StayBooking/availability),
docs до кода, по подзадачам с CI-чекпоинтом.

## 0. Что уже есть (фундамент)
- **Импорт занятости (односторонне, A5b):** `stays.ICalSource` + `services.sync_ical_source`
  + beat `sync_ical_sources` — тянем iCal Booking.com/Airbnb/Google → `UnitBlock`
  (анти-двойная-бронь). Экспорт нашей занятости — `unterkunft_ical` (iCal-фид).
- **Экспорт цен/наличия (G8):** `/stays/feed.json` (наличие+цены) для метапоиска.
- **Анти-овербукинг по ночам:** `availability.range_available` (учёт `rooms`, G5).

То есть **исходящая занятость уже отдаётся** (iCal/feed), а **входящая занятость
уже импортируется** (iCal). Не хватает «настоящего 2-way»: приём **броней** из OTA
и **push цен/доступности (ARI)** в OTA по их API.

## 1. Реальность: что требует внешних договоров (НЕ код)
«2-way Channel Manager» с Booking.com/Expedia/Airbnb — это **партнёрская интеграция**,
а не просто код:
- **Booking.com Connectivity APIs** — нужен Connectivity Partner ID, сертификация
  (ARI / Reservations / Content APIs), договор. 
- **Expedia (EPS/EQC)** — партнёрское соглашение + сертификация.
- **Airbnb API** — закрытая программа (только одобренные Channel-Manager-партнёры).

Вывод (как Stripe live / Resend): **подключение к OTA — шаг владельца/бизнеса**
(аккаунты, договоры, ключи), а не то, что можно «дописать» в этой среде. Полный
G11 — отдельный долгий проект с партнёрским статусом.

## 2. Что МОЖНО сделать кодом сейчас (фундамент, vendor-agnostic)
Заложить швы, чтобы при появлении партнёрских ключей интеграция «вставлялась», а уже
сегодня улучшить ручной/iCal-сценарий:

| # | Подзадача | Суть | Зависит от OTA-API? |
|---|---|---|---|
| **G11a** | **Модель `Channel` + единая панель** | Абстракция канала (booking/airbnb/expedia/ical/manual) на тенанта/юнит: тип, статус, последняя синхронизация, лог. Перенос `ICalSource` под этот зонтик. Кабинет «Kanäle». | нет |
| **G11b** | **Нормализатор входящих броней** | Единый `import_external_booking(channel, payload)` → создаёт `StayBooking` (source_channel, внешний id, идемпотентно) + блок. Адаптер iCal уже даёт занятость; здесь — структура под reservation-API. | нет (iCal) / да (push-API) |
| **G11c** | **Outbound ARI-абстракция** | Интерфейс `push_availability(channel, unit, dates)` с реализацией-заглушкой (лог) + реальной, когда есть ключи. Триггерится при брони/блоке. | да (реальный push) |
| **G11d** | **Booking.com адаптер** | ARI + Reservations через Connectivity API. | **да — партнёрство** |
| **G11e** | **Expedia / Airbnb адаптеры** | аналогично. | **да — партнёрство** |

## 3. Рекомендация
- **Сейчас (код):** G11a + G11b(iCal-ветка) — реальный прирост: единая панель каналов,
  нормализованный импорт, швы под API. Это честно и полезно без партнёрств.
- **Позже (владелец + долгий проект):** G11c–e — когда будут партнёрские аккаунты/ключи
  Booking/Expedia/Airbnb. До тех пор односторонний iCal + feed (G8) закрывают базовый
  сценарий «не получить двойную бронь».

## ✅ Сделано (2026-06-23) — G11a + G11b
- **Модель `stays.Channel`** (kind Booking/Airbnb/Expedia/other, name, is_active,
  last_synced_at, last_status, notes) + `StayBooking.external_ref` (id брони в канале).
  Миграция `stays/0019`.
- **`services.import_external_booking(...)`** — идемпотентный по (kind, external_ref)
  занос брони из канала: успех → `StayBooking` (source_channel, auto_confirm);
  конфликт/невалид (овербукинг между каналами) → `UnitBlock` на даты + None.
- **Кабинет `/dashboard/stays/channels/`** — список каналов (добавить/вкл-выкл/удалить),
  форма ручного импорта брони (канал/номер/даты/гость/референс) и список
  импортированных. Ссылка «Channels» в шапке календаря.
- **Демо:** 2 канала (Booking.com, Airbnb) + импортированная бронь `BKG-DEMO-12345`.
- Тесты — `apps/stays/tests/test_channels.py` (импорт, идемпотентность, конфликт→блок).

**Отложено (G11c–e):** реальный ARI-push и приём броней по API Booking/Expedia/Airbnb —
требуют партнёрских аккаунтов/сертификации (шаг владельца). Швы (Channel + import-
нормализатор) готовы под подключение адаптеров.

## 4. Вне scope
Полная сертификация OTA, Rate-parity-движок, yield-management — enterprise, отдельно.
