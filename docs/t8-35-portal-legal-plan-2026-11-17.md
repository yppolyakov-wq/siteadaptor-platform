# T-8.35 — «Rechtliches» городского портала (план, 2026-11-17)

Запрос владельца: у портала (пилот solingen.siteadaptor.de) должна быть своя страница
«Rechtliches» — Impressum, Datenschutz, AGB по правилам ЕС и стандартам отрасли. Сейчас подвал
портала ведёт на тексты платформы siteadaptor.de. Это B2B-тексты: AGB платформы прямо исключают
потребителей.

Не юридическая консультация: тексты — черновик по фактам кода. Публикация как
«rechtsverbindlich» возможна только после вычитки юристом.

## Решения владельца (2026-11-17)
- **Хаб + три страницы** на домене портала: `/rechtliches/` (оператор, контакт, контакт DSA,
  «Wie wir sortieren»), `/impressum/`, `/datenschutz/`, `/nutzungsbedingungen/`; `noindex`.
- **Оператор портала — другое лицо или фирма**, не оператор платформы. Его реквизиты хранятся у
  портала (поле `operator` у `AggregatorPortal`), а не в env платформы. Это и задел под порталы
  сторонних операторов (T-8.12).
- **До вычитки — черновик с плашкой** «Entwurf — nicht rechtsverbindlich» и пометкой
  недостающих реквизитов; плашка снимается, только когда реквизиты полные и стоит отметка
  «geprüft» (вычитано).
- **Отзывы — премодерация**: новый отзыв не виден, пока его не одобрят. Порядок жалоб описать
  по DSA: notice-and-action, Art. 16; решение с обоснованием, Art. 17.

## Что портал обрабатывает (основа Datenschutzerklärung, Art. 13 DSGVO)

| Процесс | Данные | Основание | Получатель |
|---|---|---|---|
| Серверные логи | IP, время, URL | lit. f | Hetzner (AVV) |
| Cookies | сессия жителя, язык; трекинга нет → баннера нет (§ 25 Abs. 2 Nr. 2 TDDDG) | — | — |
| Аккаунт жителя (`PortalUser`, magic-link) | e-mail, язык, избранное | lit. b | Resend (письма) |
| «Folgen» (подписки, DOI) | e-mail, выбор, частота, `confirmed_at`/`source_host` как доказательство | lit. a, Art. 7 | Resend |
| Отзывы (`BusinessReview`) | автор, оценка, текст, ответ бизнеса | lit. b/f | публично |
| Жалобы (`ListingReport`) | текст, хэш IP | lit. f / DSA Art. 16 | — |
| Telegram-бот портала | chat-id, выбор | lit. b | Telegram |
| Журнал поиска, `PortalStat` | агрегаты без ПД, сроки из settings | — | — |
| Карта | тайлы OpenFreeMap грузит браузер (IP уходит третьему лицу) | lit. f — **оценка юриста** | OpenFreeMap |
| «In der Nähe» | координаты в URL, не храним | — | — |

Плюс обязательные пункты: права по Art. 15–21, отзыв согласия (Art. 7 Abs. 3), жалоба в
надзорный орган (Art. 77) — по адресу оператора. Абзацы про ИИ-подсказку и MCP — условные,
показываются, только когда включены их флаги.

## Шаги (каждый — отдельный инкремент, CI → FF main)
1. **R1 Оператор.** Поле `AggregatorPortal.operator` (JSON: name, legal_form, street,
   zip_city, representative, email, phone, register, vat_id, responsible_mstv, dsa_email,
   supervisory_authority, reviewed_at). `apps/aggregator/portal_operator.py`: `info(portal)`,
   `missing(portal)` — что не хватает по § 5 DDG, `is_final(portal)`. Ввод в админке портала.
   Миграция `aggregator/0042` (аддитивная).
2. **R2 Страницы.** Маршруты в `config/urls_portal.py`, `apps/aggregator/legal_views.py`,
   шаблоны `aggregator/legal_*.html` на `portal_base`, плашка «Entwurf». Подвал портала,
   `platform_links.legal_links()`, `_base.html:51`, ссылки «Datenschutz» в формах «Folgen»
   переводятся на страницы портала. Платформенные страницы siteadaptor.de не трогаем — они для
   B2B.
3. **R3 Datenschutz.** Разделы по таблице выше, сроки — из settings. Замок «процесс → раздел»
   (у каждой модели ПД портала есть якорь), замок «хосты CSP `connect-src`/`img-src` названы в
   получателях».
4. **R4 Nutzungsbedingungen и DSA.** Бесплатный сервис для жителей; отзывы (правила,
   премодерация); жалобы (Art. 16/17 DSA); ответственность за данные бизнесов; блок «Wie wir
   sortieren» (UWG § 5b Abs. 2; «Anzeige» за оплату).
5. **R5 Премодерация отзывов.** `BusinessReview.STATUS_PENDING`, новый отзыв → pending; публичные
   выборки уже фильтруют `published`. Очередь — в админке платформы (действия «freigeben /
   ablehnen» с причиной для Art. 17); письмо автору о решении; старые отзывы остаются
   опубликованными. Миграция choices — без схемы (CharField).
6. **R6 Языки.** de обязывающая; en/tr/ru/uk через gettext с плашкой «Rechtlich verbindlich ist
   die deutsche Fassung» и ссылкой на de.

- **Реквизиты** владелец впишет сам в админке портала (в git их нет).
- **Модерация отзывов — оба**: одобряет оператор (админка платформы), бизнес видит очередь
  отзывов о себе в кабинете и может возразить (Einwand с причиной → оператору).

## Открыто у владельца
- Реквизиты оператора портала (вписать в админке после R1) и вычитка юристом.
- Применимость Art. 27 DSA (рекомендательная система) и исключения для малых предприятий
  (Art. 19) — решает юрист.

## Замки до кода
- Без реквизитов страница показывает «Entwurf», а не `[Platzhalter]`.
- Каждая модель ПД портала упомянута в Datenschutz.
- Подвал портала не ведёт на `siteadaptor.de/agb`.
- Новый отзыв не виден публично до одобрения; старые видны.
- Вывод реквизитов экранируется (XSS через админку).

## ECC-прогоны
- Скиллы до кода: django-patterns, django-tdd, django-security, database-migrations
  (R1/R5), accessibility, seo (noindex).
- `django-reviewer` — после каждого шага; `database-reviewer` — R1, R5; `security-reviewer` —
  R1 (ввод реквизитов, вывод), R5 (модерация, права); `silent-failure-hunter` — R1 (неполные
  реквизиты не уходят молча как готовые), R5 (письмо о решении); `a11y-architect` и Playwright
  1440/390 — R2.
- Финальный гейт: `ruff check`, `ruff format --check .`, `test_template_comments.py`,
  `scripts/i18n_quickcheck.py`, `npm run build:css` при новых классах.

## Ход работ
- **R1–R4 ✅** (2026-11-17): `PortalOperator` (+ FK `operator`, PROTECT), `portal_operator.info/missing`,
  страницы `legal_views` (хаб, Impressum, Datenschutz, Nutzungsbedingungen), подвал/формы/llms/фид.
  Ревью `django-reviewer`: тексты сверены с кодом — журнал поиска не «ohne Personenbezug»,
  раздел «KI-Hilfe bei der Suche» (только когда ИИ поиска включён, получатель — из
  `apps.ai.disclosure`), «Anzeige» сверху первой страницы (не отдельно), сроки бота и сводок
  из констант, удаление аккаунта — письмом за месяц (самообслуживания нет), хэш сети, не IP.
- **R5 ✅** (2026-11-17): премодерация — `review_moderation` (единственный писатель статуса
  отзыва): `submit` → pending (неизменённый опубликованный остаётся), `decide` (админка:
  действия «Freigeben»/«Ablehnen», обоснование, письмо автору `send_review_decision_email`),
  `object_to` (Einwand бизнеса из кабинета «Über den Betrieb»). Старые отзывы не трогаются.
  Миграция `aggregator/0042` (вместе с оператором).
- Открыто: R6 языки (тексты пока только de + плашка «verbindlich ist die deutsche Fassung»);
  версия текстов vs `reviewed_at` (после правки текстов дату проверки ставить заново — процесс
  владельца); удаление аккаунта жителем самостоятельно — кандидат в бэклог.

