# ST-6 «Marketing-центр» — план (2026-07-19)

ТЗ (`next-gen-master-tz-2026-07-19.md` §3 D2): собрать маркетинг в один центр по
ROI-порядку — напоминания → лояльность → отзывы → «акция во все каналы одной
кнопкой» → кампании; панель результатов (показы/клики/погашения — источники
готовы). Без миграций. Разведка (Explore, 2026-07-19) — факты сверены с кодом.

## §1 Факты разведки

- Все инструменты уже маршрутизированы и живут в HUB_TABS["marketing"]
  (Aktionen/Bewertungen/Kampagnen/Gutscheine + Erweitert: Reservierungen/
  Einlösen/Treuepunkte/Care-Zyklus/Kanäle/Beiträge/Finder); замки
  test_hub_tabs:143-170 фиксируют состав — HUB_TABS НЕ трогаем.
- Хаб-плитка «Marketing» главной ведёт на promotion-list (dashboard.py:257) —
  «центра» нет. Образец центра-лендинга ГОТОВ: `integrations_home`
  (views.py:3339 + integrations_home.html; новая страница — classic-гейт не
  нужен, ничего не заменяет; прецедент ST-4a).
- Напоминания: 12+ beat-тасков (B2 неоплата ×4, reminder ×4, post_* ×4,
  win-back) — вкл/выкл только чекбоксами матрицы UD4-2 (prefs.customer_matrix)
  + win-back отдельно на CouponCampaign(kind=auto_winback). ЕДИНОГО ОБЗОРА НЕТ
  — главная дыра ROI №1.
- «Во все каналы»: органик-веер УЖЕ есть, но жёстко на FSM-переходе active
  (state_machine.py:42 → publishing.services._publish_all по
  Channel(is_enabled=True), dedupe + UniqueConstraint(promotion, channel));
  явной кнопки/статуса «где опубликовано» на акции нет; email-кампании и
  ★ Feature — отдельные механизмы.
- Панель результатов: 4 готовых источника — Promotion.views (+analytics_overview),
  AggregatorListing.featured_impressions/clicks (F-инкременты; читать ТОЛЬКО
  на чтение), Voucher.used_count по campaign, reviews.owner_overview;
  `_puls()` в dashboard.py:181 уже сводит views+redemptions (прототип).
- Care-Zyklus вкладка marketing-хаба ведёт на notifications-settings, который
  рендерит hub_tabs "settings" — подсветка вкладки ломается (известная
  несогласованность; лендинг-карточка её обходит, HUB_TABS не правим).

## §2 ST-6a — лендинг «Marketing» + обзор напоминаний + панель результатов

- НОВЫЙ `apps/core/marketing_home.py` + вьюха `marketing_home`
  (url `dashboard/marketing/`, name `marketing-home`) + шаблон
  `tenant/marketing_home.html` (паттерн integrations_home: карточки-входы,
  гейт по модулям, `{% hub_tabs "marketing" %}` сверху).
- **Карточки в ROI-порядке ТЗ:** 1) Erinnerungen (→ Care-Zyklus/notifications-
  settings) · 2) Treue & Gutscheine (→ voucher-list; гейт loyalty) ·
  3) Bewertungen (→ reviews:list; гейт reviews) · 4) Aktion überall teilen
  (→ promotion-list, подсказка «Teilen на каждой акции», §3) · 5) Kampagnen
  (→ coupon-campaigns; гейт crm) · + Aktionen/Kanäle как вспомогательные.
- **Обзор напоминаний (ROI №1, read-only):** блок «Aktive Erinnerungen» —
  строки из prefs.customer_matrix() ТОЛЬКО reminder-событий (payment_reminder/
  reminder/post_*/service_reminder; per-домен гейт модулей) с индикатором
  email/telegram вкл/выкл + строка Win-back (CouponCampaign kind=auto_winback:
  active/paused/нет) со ссылками «настроить». Новых моделей нет.
- **Панель результатов:** «Aufrufe aktiver Aktionen» (Sum Promotion.views
  active) · «★ Anzeige: Impressionen/Klicks» (Sum featured_impressions/clicks
  по AggregatorListing тенант-схемы; read-only) · «Kampagnen: ausgegeben/
  eingelöst» (issued/redeemed как в coupon_campaigns) · «Bewertungen: ⌀/N»
  (owner_overview). Каждый блок _safe-паттерном (как home_widgets) и ссылкой
  на детальный экран (analytics/кампании/reviews).
- Хаб-плитка «Marketing» главной → `marketing-home` (замок test_st4_home
  проверяет только reverse-ability url_name — обновится без боли).

## §3 ST-6b — «Aktion überall teilen» (одной кнопкой)

v1 — экран «Teilen» per-акция (кнопка на строке promotion-list рядом с
«★ Feature»), БЕЗ изменения FSM-веера:
- Статус «где опубликовано»: Publications этой акции по каналам
  (channel/status/external_ref) + список включённых каналов без публикации.
- Кнопка «Jetzt überall veröffentlichen» (POST) → реюз
  `publishing.services._publish_all(promotion)` — идемпотентно (dedupe_key +
  UniqueConstraint), для уже опубликованных = re-queue обновления; гейт: акция
  active + модуль publishing.
- Входы «остальных каналов одной страницей»: ссылка «Per E-Mail an Kunden»
  (→ coupon-campaigns с prefill акции; ТОЛЬКО consented_customers — UWG §7,
  сам механизм кампаний не меняем) + «★ In der Umgebung bewerben»
  (→ promotion-feature, если billing.featured.is_enabled()).
- Ничего не постим автоматически за пределами существующих механик; email
  НЕ отправляется с этого экрана (только переход в кампании) — v1 честный.

## §4 Риски / инварианты

- HUB_TABS не менять (замки test_hub_tabs); URL-имена из §8 разведки не
  переименовывать; featured-счётчики читать без записи (test_featured).
- Веер публикаций: не дублировать Publication (dedupe/UniqueConstraint) —
  использовать существующий сервис, не создавать записи вручную.
- classic_ui: лендинг и «Teilen» — НОВЫЕ страницы (ничего не заменяют) →
  гейт не требуется (прецедент integrations_home); хаб-плитки в classic и так
  не рендерятся. Сайдбар-якорь «Marketing» (promotion-list) не трогаем.
- UWG §7: никакой автоматической email-рассылки; только переход в кампании.
- i18n: новые строки кабинета — msgid по конвенции соседних шаблонов
  (integrations_home — {% trans %} английские msgid) + переводы en/tr/ru/uk.

## §5 Инкременты (батч-конвенция)

1. **ST-6a** marketing_home (карточки + обзор напоминаний + панель результатов)
   + плитка главной → marketing-home + тесты (лендинг рендерит/гейтит блоки;
   панель read-only; плитка резолвится).
2. **ST-6b** экран «Teilen» + POST-веер + входы email/featured + тесты
   (идемпотентность повторной публикации, гейты, кнопка в списке акций).
3. Докблок (build-log, CLAUDE.md, task-catalog, ✅-маркер D2) + i18n.
