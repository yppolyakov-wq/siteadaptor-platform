# AIS-3 «Was haben Sie schon?» — вход мастера v4 (2026-11-06)

Решение владельца: «продолжай по рекомендации с ЕСС». Источник — `ais-ai-setup-simplification-
analysis-2026-11-05.md` (AIS-3, главный разрыв с рынком). План — агент planner.

## Решение
* **Новый шаг `quelle`** первым у v4 (до «Firma»), гейт `_gate_v4`; v3 не меняется. Шаг виден на
  рельсе ✓/⏭, дозаполняется `?step=quelle`, получает метку AIS-0.
* Выбор: Website · Google-Profil · Foto der Speisekarte/Preisliste · Nichts (Beispiele); можно
  несколько, «Nichts» снимает остальные, «Überspringen» всегда. Варианты без ключей не рисуются
  (`setup_google.enabled`, `offer_photo.enabled`).
* State: `onboarding["had"]` (подмножество) + `onboarding["import_run"]`, presence-minimal, в
  белом списке нормализатора onboarding. Экран НИЧЕГО не пишет в бизнес-данные — только маршрут.
* Передача: google → Firma `#google` (поиск предзаполнен, запускает владелец); photo → Angebot
  `#scan`; none → Angebot с образцами; website → тот же `imports.site.service.start_run`
  (SSRF внутри), мастер не ждёт, на Angebot — карточка статуса и «Prüfen & übernehmen» в экран
  импорта с безопасным `next` (верификация владения обязательна). Только владелец.

## Срезы
S1 каркас шага + замки → S2 Google/фото/образцы → S3 сайт (security) → S4 стенд + отчёт AIS-0.
Макет — до S1 (новый экран, утверждение владельца).

## ECC
Скиллы: django-patterns, django-tdd, django-security, accessibility, e2e-testing. Агенты:
django-reviewer каждый срез; security-reviewer + silent-failure-hunter на S3; a11y-architect на
макет и S1; Playwright-стенд S4 (390/1440, «без ключей»).
