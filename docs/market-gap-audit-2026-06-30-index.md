# Серия «детальная проверка архетипов: рынок ↔ функционал» — индекс/хронология

> Запущена 2026-06-30 (после общего аудита `archetype-completeness-audit-2026-06-30.md`).
> Цель: пройти КАЖДЫЙ архетип детально, сравнить рынок DACH с нашим функционалом,
> зафиксировать структуру сайта + недостающий функционал. Порядок: **A1/A2 → по номерам**.
> Формат: на каждый архетип — отдельный датированный док `market-gap-<архетип>-<дата>.md`
> (новые доки, не перезапись; старые `market-analysis/*` 2026-06-25 = снапшот).
> Метод каждого шага: воркфлоу (код-инвентарь + бенчмарк рынка + сверка старого
> отчёта/демо) → синтез → **адверсариальная проверка каждого гэпа против кода**.

## Прогресс

| Шаг | Архетип | Кит(ы) | Документ | Статус |
|:--:|---|---|---|:--:|
| 1 | **A1/A2 Retail** (Online-Shop + C&C/Versand) | `shop`, `aktionsmarkt` | `market-gap-a1a2-retail-2026-06-30.md` | ✅ готов |
| 2 | **A3 Termin-Dienstleister** | `friseur` | `market-gap-a3-2026-06-30.md` | ✅ готов |
| 3 | **A4 Gastro** | `restaurant`, `pranasy` | `market-gap-a4-2026-06-30.md` | ✅ готов |
| 4 | **A5 Übernachtung/Hotel** | `hotel` | `market-gap-a5-2026-06-30.md` | ✅ готов |
| 5 | **A6 Event/Retreat** | `retreat`, `pranasy` | `market-gap-a6-2026-06-30.md` | ✅ готов |
| 6 | A7 Handwerker | `handwerker` | `market-gap-a7-2026-06-30.md` | ⏳ |
| 7 | A8 Aggregator/Portal | — (портал) | `market-gap-a8-2026-06-30.md` | ⏳ |
| 8 | A9 Kfz-Werkstatt | `werkstatt` | `market-gap-a9-2026-06-30.md` | ⏳ |

## Сквозные находки (накапливаются по мере прохождения)

- **A1/A2:** платёжный микс DACH (PayPal/Klarna Kauf auf Rechnung) — топ-гэп; три
  дешёвых правовых MUST (кнопка §312j, ноты PAngV «inkl. MwSt./Lieferzeit»,
  AGB/Versand&Zahlung); нет поиска по витрине; одноосевые варианты; нет carrier-API.
  Правовое/AGB и язык — сквозные (см. общий аудит D3–D7).
- **A3:** движок на уровне Fresha/Shore (дифференциатор — flat 39 €/0 % комиссии);
  отставание презентационное: нет **детали услуги** (общий гэп с A7/A9), нет
  **клиентского переноса**, нет **SMS-напоминаний**, нет **отзывов у CTA брони**,
  плоский список слотов вместо календаря, нет skill-matrix/buffer/waitlist/серий.
- **A4:** движок ~90 % (ближе всего к resmio); сознательно без фискального POS (TSE).
  Гэпы: платёжный микс (PayPal/Bar selector — общий с A1/A2), слот предзаказа
  (`pickup_slot` не дотянут), QR pay-at-table + Trinkgeld, Mittagstisch-расписание,
  **Zusatzstoffe/E-номера (юр.)**, live-статус гостю, gastro-виджет брони (Anlass/
  no-show fee), JSON-LD Restaurant, поиск по меню. Демо: pranasy(all-vegan)=0 diet-тегов.
- **A5:** самый достроенный архетип (H1–H9 + G1–G11a/b); для 1–20 номеров — почти
  паритет с Booking/Smoobu + правовой клин DACH (Kurtaxe/Meldeschein/0 % комиссии/
  cookieless/без dark-patterns). Гэпы — полировка: чипы отмены/рейтинг на КАРТОЧКАХ,
  верифиц. отзыв гостя per-stay, cross-type multi-room, богатые upsell (фото/qty),
  мультиязык контента (StayUnit без I18nMixin), отмена в ЛК, range-picker на поиске.
  Стратегич. отложено (partner-gated): real 2-way OTA + Google connectivity-фид.
  Adversarial: truthful «N frei» — НЕ гэп (уже есть).
- **A6:** один из самых полных архетипов (старые доки ~45–55 % сильно занижали);
  бэкенд на уровне Eventbrite/BookRetreats/Momence. Сильнейшая зона — retreat-landing
  + связка с проживанием (real anti-overbooking) + waiver/рассрочка. Гэпы: авто-early-bird
  (G4 у stays не подключён к events), верифиц. отзывы attendee, per-attendee roster
  (multi-seat=1 QR), Event/Course JSON-LD, embed-виджет событий (агрегатор-events уже
  есть), .ics-в-письме + grid-календарь, DSGVO-retention health-данных, replay/hybrid,
  memberships/class-pass для курсов, sellable gift-voucher (продажа привязана к stays).
- **Сквозное (накапливается):** «деталь услуги» (A3+A7+A9) · отзывы/обзоры на витрине
  бизнеса, верифиц. per-item (A3/A4/A5/A6/A7/A9) · **платёжный микс PayPal/Klarna/SEPA/Bar
  + `Order.payment_method` (A1/A2+A4+A5+A6)** · SMS/WhatsApp-канал · AGB · **язык/мультиязык
  контента моделей (catalog есть; stays/events landing нет → I18nMixin + L1–L6)** ·
  **JSON-LD по архетипу (Product/Restaurant/Event/Course — частично)** ·
  **переиспользование готовых движков между архетипами** (G4-авто-скидки stays→events;
  Pass booking→events; gift-voucher stays→events; embed-виджет stays→events; Meldeschein-
  retention stays→events).

_(дополняется на каждом шаге; в конце серии — сводка сквозных тем и единый бэклог.)_
