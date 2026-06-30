# A9 Kfz-Werkstatt (автосервис/мастерская) — рынок ↔ функционал — 2026-06-30

> **Шаг 8 (финальный)** серии (индекс: `docs/market-gap-audit-2026-06-30-index.md`).
> Метод: воркфлоу 34 агента → синтез → **усиленная адверсариальная проверка**:
> 10 ключевых гэпов × **3 линзы** (исчерпывающий код · переиспользование у соседних
> архетипов · сверка с доками/демо), вердикт **по большинству**.
> Итог: **8 CONFIRMED_MISSING, 2 PARTIAL** (+ нюанс по AutoRepair JSON-LD).
> Бенчмарк: ATU, Bosch Car Service, pitstop, Vergölst, Euromaster, FairGarage, Caroobi,
> Werkstars, Tjekvik/AutoFlow, DAT/GT-Motive/Eurotax. Кит: `werkstatt`. Снапшот — `market-analysis/a9-werkstatt.md`.

## 0. Вывод одной фразой

A9 берёт **клиентские ожидания** сетей (ATU/Bosch CS) на сайт одного бизнеса за
39 €/мес и **держит паритет по дневному циклу** (онлайн-Termin на Hebebühne, Festpreis,
структурные Kennzeichen/HSN/TSN, итемизированный Kostenvoranschlag с депозитом, отзывы,
Meister-блок, AutoRepair-разметка). Отстаёт ровно на **авто-специфичном retention/
transparency-слое** (не на движке брони): HU/AU-напоминание, Reifeneinlagerung,
Ersatzwagen, repair-статус, + сквозные A7-гэпы (деталь услуги, E-Rechnung, AGB).

## 1. Структура сайта (карта страниц)

| Страница | Статус | Заметка |
|---|:--:|---|
| Главная | ✅ | но **AutoRepair JSON-LD только на `/anfrage/`** (главная — generic LocalBusiness) |
| **Каталог Leistungen + деталь услуги** | ❌ | как A7: только home-тизер + воронка `/termin/`; деталь = слот-пикер |
| Anfrage с Kennzeichen/HSN/TSN | ✅ | jobs_vehicle-флаг + AutoRepair-разметка |
| Публичный Angebot/Kostenvoranschlag | ✅ | line items + accept/decline + депозит; **без e-подписи** (как A7) |
| Termin на Hebebühne | ✅ | 2 ресурса, anti-double-book, депозит |
| Auftrag→Rechnung | ✅ | finance.Invoice + PDF; **нет E-Rechnung, нет онлайн-оплаты счёта** |
| Teile из каталога + списание склада | ✅ | G11 идемпотентно |
| **Repair-статус клиенту** | ❌ | FSM есть, но done/invoiced — без письма/публичной страницы статуса |
| **Serviced-vehicle / HU-AU напоминание** | ❌ | vehicle — плоские поля Job, нет next-HU/сущности авто/reminder-движка |
| **Reifeneinlagerung** | ❌ | нет модели хранения шин/сезонного цикла |
| ЛК клиента | ✅ | но **не vehicle-aware** (нет истории по авто) |
| Trust/Meister | 🟡 | free-text marks; нет верифиц. бейдж-ассетов (Kfz-Innung/Bosch/Eurogarant) |
| Правовое (Impressum/Datenschutz/Widerruf) | ✅ | **AGB нет** (сквозной) |

## 2. Что уже есть (паритет с шоп-страницей сети по первому контакту)

Онлайн-Termin на Hebebühne · **Festpreis** · **структурные Kennzeichen/HSN/TSN** ·
**AutoRepair schema.org** (на `/anfrage/`) · итемизированный **Kostenvoranschlag** +
accept/decline + **депозит онлайн** · **Teile из каталога + списание склада** (G11) ·
Auftrag→Rechnung + PDF · отзывы на витрине · Meister-trust-блок · часы/гео · mobile
sticky-CTA · связка Termin↔Job.

## 3. Матрица «рынок ↔ наш статус»

| Фича рынка | Важн. | Статус | Заметка |
|---|:--:|:--:|---|
| Онлайн-Termin (по услуге, ресурс) | must | ✅ | Hebebühne |
| Vehicle capture (Kennzeichen/HSN/TSN) | must | ✅ | структурно |
| **KBA-lookup по HSN/TSN** | should | ❌ | поля есть, lookup-движка нет |
| Festpreis-услуги | must | ✅ | + badge |
| **Каталог Leistungen + деталь услуги** | must | ❌ | как A7 (D1/D8) |
| Kostenvoranschlag + accept online | must | ✅ | |
| Депозит онлайн | should | ✅ | |
| **E-Rechnung (ZUGFeRD/XRechnung)** | must (B2B 2025) | ❌ | только PDF; нет XML-библиотек |
| **Онлайн-оплата счёта** | should | 🟡 | только депозит на Angebot |
| Teile + списание склада | should | ✅ | G11 |
| **HU/AU (TÜV) reminder по авто** | must (retention) | ❌ | только per-Termin reminder; нет next-HU |
| **Inspektion nach Herstellervorgabe** | should | ❌ | только статичная услуга «Inspektion» |
| **Reifenwechsel + Reifeneinlagerung** | should | ❌ | Reifenwechsel как услуга; storage нет |
| **Ersatzwagen / Hol-und-Bringservice** | should | 🟡 | движок core.Extra есть, не засеяно для werkstatt |
| Zusatzleistungen (Klima/Achsvermessung) | should | ❌ | core.Extra не засеян для werkstatt; нет «ab»-цены |
| **Repair-статус клиенту + «fertig»-письмо** | should | ❌ | FSM есть, уведомления стоп на accepted/declined |
| **Digitale Serviceannahme/Serviceheft** | should | ❌ | нет протокола приёмки/цифр. сервис-книжки |
| **Vehicle history в ЛК** | should | ❌ | ЛК не vehicle-aware |
| **DAT/GT-Motive estimation** | nice (SMB) | ❌ | ручная смета — честный SMB-субститут |
| **AutoRepair JSON-LD на всех страницах** | should (local-SEO) | 🟡 | только `/anfrage/`; главная — generic |
| Отзывы | must | 🟡 | бизнес-уровень; нет per-Auftrag верифиц. (как A7) |
| **Верифиц. trust-бейджи** (Kfz-Innung/Bosch/Eurogarant) | must | ❌ | free-text marks |
| **AGB** | must | ❌ | сквозной гэп |

## 4. Недостающий функционал — приоритизировано (вердикт по 3 линзам)

### 4a. Дешёвые победы (S) — данные/движки уже есть
| # | Что | Вердикт (counts) | Размер |
|---|---|:--:|:--:|
| K1 | **Деталь услуги** (route+template поверх готовых `Service.description/image`) — общий с A3/A7 (D1) | CONFIRMED_MISSING (2/1) | S |
| K2 | **AutoRepair JSON-LD на главной/услугах** ('other'→AutoRepair или schema_type sitewide для jobs_vehicle) | PARTIAL (2 PARTIAL/1 EXISTS)¹ | S |
| K3 | **Zusatzleistungen** (Klima/Achsvermessung/Wäsche) через core.Extra + «ab»/Richtpreis-цена | CONFIRMED_MISSING (2/1) | S |
| K4 | **Ersatzwagen / Hol-und-Bringservice** как core.Extra (движок есть, не засеяно) | PARTIAL (3) | S |
| K5 | **AGB** (route+template+tenant-text) — сквозной | CONFIRMED_MISSING (3) | S |

### 4b. Retention-сущности (M/L) — net-new, главный рычаг автосервиса
| # | Что | Вердикт (counts) | Размер |
|---|---|:--:|:--:|
| K6 | **Repair-статус клиенту** (этапы angenommen→in Arbeit→fertig→abgeholt) + авто-письмо «fertig zur Abholung» на done (FSM уже есть) | CONFIRMED_MISSING (3) | M |
| K7 | **Serviced-vehicle сущность** (next-HU/next-service) + **HU/AU + Inspektion reminder-движок** (opt-in UWG §7) — сильнейший retention-рычаг | CONFIRMED_MISSING (3) | L |
| K8 | **Reifeneinlagerung** (учёт комплекта/Kennzeichen/размер/место + сезонный цикл + season-reminder) — повторяющийся доход | CONFIRMED_MISSING (3) | L |
| K9 | **Vehicle history в ЛК** (vehicle-aware Kundenkonto; зависит от K7) | (не верифиц., 11-й) | M |

### 4c. Комплаенс / доверие (сквозное с A7)
| # | Что | Вердикт (counts) | Размер |
|---|---|:--:|:--:|
| K10 | **E-Rechnung (ZUGFeRD/XRechnung)** + онлайн-оплата финального счёта | CONFIRMED_MISSING (2/1) | M |
| K11 | **Верифиц. trust-бейдж-ассеты** (Kfz-Innung/Bosch-Partner/Meisterbetrieb/Eurogarant) вместо free-text | CONFIRMED_MISSING (2/1) | M |
| K12 | **DAT SilverDAT 3 / GT-Motive** импорт в смету (partner-gated; ручная смета — SMB-субститут) | (не верифиц., 12-й) | L |

¹ **Нюанс K2:** AutoRepair JSON-LD **уже эмитится на `/anfrage/`** (которая и есть каноническая публичная посадочная A9 — отдельного каталога услуг нет). Одна линза дала ACTUALLY_EXISTS. Гэп — только распространение типа на главную/прочие страницы (smena `_SCHEMA_TYPES['other']` или sitewide schema_type). Дешевле, чем кажется.

## 5. Сравнение с лидерами

Правильный бенчмарк: ATU/Bosch CS — сети, FairGarage — агрегатор прозрачности,
Caroobi — комиссионный маркетплейс (закрылся ~2020). Мы берём их **клиентские
ожидания** на сайт одного бизнеса.
- **Паритет по первому контакту** с шоп-страницей Bosch CS: Termin/Festpreis/vehicle-
  capture/Kostenvoranschlag-с-депозитом (которого сети walk-in'ам даже не показывают)/
  отзывы/Meister/часы/mobile-CTA — всё есть.
- **Сети ведут в авто-специфичном слое:** (1) HU/AU+service-reminder по next-due авто
  (T2 — крупнейший retention-гэп); (2) Zusatzleistungen + Ersatzwagen в одном флоу +
  Reifeneinlagerung как recurring доход (pitstop/Vergölst); (3) богатые страницы услуг;
  (4) верифиц. Innung/Bosch-бейджи (питч FairGarage); (5) DAT/GT-Motive + Tjekvik-grade
  digitale Serviceannahme (chain/Autohaus-grade, разумно вне SMB-тира); (6) **E-Rechnung**
  (юр. 2025), которую Werkstattsoftware сетей уже умеет.
- **Caroobi-закрытие — стратегический сигнал:** чистый lead-gen недомонетизирует →
  валидирует модель «сайт одного бизнеса». Цель — паритет ожиданий, достижимый S-победами
  (деталь услуги/AutoRepair-SEO/Extras) + M/L retention-сущностями (repair-статус →
  HU/AU-reminder → Reifeneinlagerung), а не гонка за B2B-интеграциями сетей.

## 6. Что устарело / подтверждено

Build-log «С этим A9 закрыт» относился к **vehicle DATA (T1: Kennzeichen/HSN/TSN +
AutoRepair)** — это сделано. **Подтверждено как открытые гэпы:** деталь услуги, repair-
статус, HU/AU-reminder (T2), Reifeneinlagerung (T3), Zusatzleistungen/Ersatzwagen (T6),
E-Rechnung, верифиц. trust-бейджи, AGB. AutoRepair-разметка — частично закрыта (есть на
`/anfrage/`, нужно распространить).

## 7. Связанные
`docs/archetype-completeness-audit-2026-06-30.md` (D1/D6) · `docs/market-gap-a7-2026-06-30.md`
(общий jobs/finance движок: деталь услуги, E-Rechnung, trust, AGB) ·
`docs/market-analysis/a9-werkstatt.md` (снапшот) · `apps/jobs`, `apps/booking`,
`apps/catalog`, `apps/finance`, `apps/core` (extras/seo).
