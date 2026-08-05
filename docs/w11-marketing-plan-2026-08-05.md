# W11 — Marketing (Kunden влит) + Website-свод

Дата: 2026-08-05. Родитель: `cabinet-unification-plan-2026-08-05.md §2.5–2.6`
(решение Р-2: Marketing+Kunden слить; Р-5: Newsletter — вкладкой ✅ уже в W7b).
Все инкременты БЕЗ миграций БД.

## §1. Цель

Один Marketing-хаб вместо двух (marketing + kunden — «молчаливая подмена
таб-бара» умирает); лендинг marketing_home — только состояние; владелец видит и
отвечает на отзывы о бизнесе; акция на услугу/номер/комбо создаётся из UI
(движок PL готов с 2026-08-04, UI — нет).

## §2. Инкременты

- **W11-1 Свод хабов (Р-2).** ENTRIES: записи hub="kunden" переезжают в
  hub="marketing" (Kontakte/Nachrichten/Telegram уже там дублем в Erweitert —
  дубли схлопнуть); HUB_TABS["kunden"] умирает (HUBS, реестр, консумеры);
  страницы crm/inbox/telegram рендерят `hub_tabs "marketing"`. Порядок табов —
  3 смысловые группы §2.5 (в плоском таб-баре: прямые = Aktionen/Bewertungen/
  Kampagnen/Gutscheine/Kontakte/Nachrichten; Erweitert — остальное). Карта
  подсветки: kunden-якорь и так вёл на Marketing (hubs=("marketing","kunden")) —
  сверить и снять "kunden" из Anchor.hubs. Замки test_hub_tabs (kunden-секция —
  переписать осознанно) + W8-инварианты.
- **W11-2 Лендинг marketing_home слим.** Карточки-дубли (ведущие на то же, что
  табы) убрать; остаются обзор авто-касаний + панель результатов (правило §1.5).
  Замки test_marketing_home обновить.
- **W11-3 BusinessReview в кабинете.** Вкладка «Über den Betrieb» на
  reviews-экране: список BusinessReview (витрина уже рендерит) + ответ владельца
  (по образцу ответов на entity-отзывы; если модель ответа отсутствует —
  read-only список v1, ответ отдельным решением). Разведка ДО кода: модель/
  витринный рендер/наличие поля ответа.
- **W11-4 Акция на услугу/номер/комбо из UI.** PromotionForm += FK-цели
  service/stay_unit/combo (селекты гейтятся модулями; target_rules — v2 не
  трогаем) + кнопка «Aktion erstellen» со строки сущности в Angebote
  (`?service=<pk>`-префилл). Движок PL не трогается (P1–P7 закрыты).
- **W11-5 Website-свод (§2.6, малый).** site.html-лендинг слить в Studio
  (карточки → входы рейки; SEO — в рейку), «Website»-якорь ведёт в одно место;
  Медиатека из Erweitert-Settings в Website-зону. Разведка ДО кода (site.html
  консумеры, back-ссылки).

Каждый инкремент — свой батч (локальный гейт → push → CI → merge). Замки
переписываются осознанно с пометкой в build-log.

## §3. Статус

- **W11-1 ✅** (2026-08-05): Kunden влит в Marketing (Р-2). Хаб kunden удалён из
  реестра (HUBS/ENTRIES/Anchor.hubs); Kontakte/Nachrichten — прямые табы
  Marketing, Telegram в Erweitert (дубли схлопнуты); 4 шаблона (crm×2/inbox/
  telegram) рендерят marketing-хаб. Замки kunden-секции переписаны осознанно.
- **W11-2 ✅** (2026-08-05): marketing_home слим — карточки-дубли табов хаба
  (Gutscheine/Bewertungen/Aktionen/Kampagnen/Kanäle) убраны; остаются обзор
  авто-касаний + панель результатов + один кросс-вход «Erinnerungen &
  Care-Zyklus» (живёт в Einstellungen — правило §1.5). Замки обновлены.
- **W11-3 ✅** (2026-08-05): вкладка «Über den Betrieb» на экране Bewertungen
  (?typ=betrieb) — отзывы о бизнесе с портала /entdecken (SHARED BusinessReview,
  фильтр по схеме). Разведка: поля ответа в модели НЕТ → v1 read-only (как в
  плане); ОТВЕТ ВЛАДЕЛЬЦА требует миграции поля — отдельное решение владельца.
  Автор не раскрывается (паритет с порталом); hidden помечены. Замок:
  своя схема видна / чужая нет / автор скрыт / дефолтный список цел.
- Дальше: W11-4 (акция на услугу/номер/комбо из UI) → W11-5 (Website-свод).
