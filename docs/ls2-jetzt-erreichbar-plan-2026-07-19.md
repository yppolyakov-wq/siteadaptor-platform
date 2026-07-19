# LS-2 «Jetzt erreichbar» — план (2026-07-19)

Этап A3 ТЗ `docs/next-gen-master-tz-2026-07-19.md §3`: живой бейдж присутствия
на витрине «Jetzt erreichbar — Video-Anruf möglich» + кнопка мгновенного
wa.me-звонка (реюз `apps/core/whatsapp.wa_link` из LS-1); авто по часам работы
+ ручной override. Недоступен → фолбэки уже существуют: плавающий чат
«Nachricht schreiben» (inbox FAB в `_base.html`) и обычные CTA брони.

## 1. Решения

- **Хранение:** `site_config["presence"] = {"mode": "on"|"off"}`,
  **presence-minimal** в normalize (паттерн board/finder): ключ материализуется
  ТОЛЬКО при mode≠auto; отсутствие ключа = режим **auto**. Golden-эталоны НЕ
  меняются (по умолчанию ключа нет) — замок в тестах.
- **Режимы:** `auto` (дефолт) — открыт по `Tenant.opening_hours_structured`
  через существующий `apps/tenants/openinghours.open_status` (часов нет →
  недоступен); `on` — принудительно доступен (мелкий бизнес без часов);
  `off` — бейдж выключен.
- **Гейт номером:** весь бейдж — это CTA видео-звонка → без
  `Tenant.whatsapp_number` не показывается ни в одном режиме (тот же
  opt-in-принцип, что LS-1).
- **30-сек-фолбэк из концепта** технически не детектируем через wa.me (мы не
  знаем, ответили ли) — v1-фолбэк = «недоступен → бейджа нет, остаются чат
  (inbox) и Termin buchen», как и допускает ТЗ.

## 2. Точки врезки

- `apps/core/presence.py` — `mode(tenant)` / `available_now(tenant)`
  (off→False, on→True, auto→open_status; часы читаем с tenant, TZ —
  timezone.localtime).
- `apps/tenants/siteconfig.py` — `normalize_presence` + провод в `normalize`
  (после board/finder, presence-minimal).
- Витрина: inclusion-тег `presence_fab` (siteui) в `_base.html` НАД чат-FAB —
  зелёная пилюля «🟢 Jetzt erreichbar — Video-Anruf» → wa.me с текстом
  «Ich bin gerade auf Ihrer Website — können Sie mir kurz per Video helfen?».
- Кабинет: компактная карточка-переключатель Auto/An/Aus на главной кабинета
  (обе ветки — плитки AB7 и classic) + endpoint `set-presence`
  (targeted-write: правит ТОЛЬКО ключ presence, остальной конфиг цел —
  паттерн set-classic-ui/board_settings).

## 3. Замки

Normalize presence-minimal (пустое/auto → ключа нет; on/off живут; мусор
безопасен; golden цел); резолвер по режимам/часам; витрина: бейдж только при
(режим доступен И номер); targeted-write не трогает чужие ключи; i18n msgid →
en/tr/ru/uk. Без миграций.
