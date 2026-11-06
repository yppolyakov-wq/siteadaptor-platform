# AIS W4-5 «Verkauf öffnen» + «Nächster Schritt» — план (2026-11-06)

План — агент ECC `planner` (принят ведущим). Спека — `ais-wizard-v4-structure-2026-11-05.md`
§4.1/§4.2/§3a. **Без миграций.** Гейт продажи (`READINESS_SELL_GATE`) остаётся выключен:
`readiness.sell_allowed` нигде не вызывается — подключение к чекаутам отдельным W4-5d после W4-6.

## Факты кода, задающие план
- Полноформенные писатели теряют данные при частичном POST (класс W0): `orders/views.py`
  `save_delivery` пересобирает весь блок доставки (зоны/сборы/точки), `save_vorkasse` без полей
  банка пишет пустые; `stays/settings_actions.kurtaxe` сбрасывает метку. Вопросы пишут УЗКИМИ
  писателями, экраны зовут те же (один писатель на настройку).
- Правила отмены: услуги — инлайн во вьюхе `booking/views.py` (+ `_can_edit_policy`), номера — на
  тарифе (`RatePlan`), события — на событии.
- Состояние мастера пересобирается из известных ключей (`onboarding.get_state`) и защищено
  `_LOCKED_STATE_KEYS` — новые ключи добавить в оба.
- На главной один механизм прогресса (`setup_checklist`, X2a) — карточки v4 его заменяют, не дублируют.
- Помощник берёт `?q=` (правила, без ИИ) — карточка может вести в него с готовой фразой.

## Хранение
`site_config["onboarding"]["verkauf"] = {направление: {"answered": [...], "opened_at": iso}}`,
`site_config["onboarding"]["cards"] = {"hidden": {key: iso}}` («Später» — 14 дней). Закрытое
направление → `directions.set_state(..., mode="verkaufen")`.

## Инкременты
- **W4-5a** движок `apps/core/sell_questions.py` (Question: key/direction/label/choices/applies/
  current/write/perm/readiness_key; `questions_for`, `answer`, `mark_answered`) + Waren: доставка
  вкл/выкл, Vorkasse вкл (без IBAN — ссылка), карта, НДС позиций (превью + ≤ 50, «gemischt» —
  ссылка), AGB/Widerruf (`waren.widerruf` MUST при доставке), аллергены/Grundpreis — ссылки +
  помощник. Экран `/dashboard/verkauf-oeffnen/?r=<направление>`: по форме на вопрос (чипы), PRG,
  без JS; nav_registry/view_perms/пакет.
- **W4-5b** Termine/Tisch (`booking/cancel_policy.apply`, смешанные правила — ссылка), Zimmer
  (тариф «Standard» / один тариф / ≥2 — ссылка; `set_kurtaxe` с сохранением метки), Tickets
  (`set_refund_policy` для будущих; шаги сборов не трогаем), Anfragen (`jobs/anfrage_settings.save`).
- **W4-5c** карточки `apps/core/next_steps.py` (≤ 3, по данным, через `assistant.link`, fail-closed,
  «✨ Assistent fragen» → `assistant?q=…`, «Später»); на главной v4 вместо чек-листа.
- **W4-5d** (позже) гейт продажи в чекаутах.

## Замки до кода
Потеря данных (зоны/сборы/точки при ответе о доставке; банк при Vorkasse; метка Kurtaxe; смешанные
правила отмены; тариф со шагами сборов) · паритет извлечённых писателей · состояние переживает
Save Studio и устаревший тенант · права (`preise.edit`, банк — владелец) · карточки (≤ 3, модуль
выкл — нет карточки, «Später» 14 дней, v3-главная байт-в-байт) · X7 (вход в навигации).

## ECC-прогоны
До кода: скиллы django-patterns/django-tdd/django-security; `architect` — подход узких писателей.
W4-5a/b: `django-reviewer`, `security-reviewer` (деньги, банк, правовые тексты, права),
`silent-failure-hunter` (писатели, fail-closed карточки). W4-5c: `a11y-architect`, Playwright
(Waren/Zimmer, 390/1440). Перед мержем — `doc-updater`-конвенция (build-log, task-catalog, CLAUDE §3).
