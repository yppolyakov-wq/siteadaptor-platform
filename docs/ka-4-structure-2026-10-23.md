# KA-4 · Общая структура кабинета: целевая карта (2026-10-23)

> Часть программы `ka-cabinet-audit-program-2026-10-22.md`. Только анализ и целевая карта; кода нет,
> реализация — волнами после сводки KA-11. Основа: `ka-0-inventory` (§3 дубли D1–D12, §4 сироты,
> §6 сайдбар по типам), `ka-2-market §3(c)`, `ka-3-packages` (решения В-1…В-6), две разведки по коду
> 2026-10-23 (факты ниже — с адресами). Касается пакетов **Website** и **Laden** (полный кабинет);
> лёгкие Aktionen/Eintrag описаны в KA-3 §3.1–3.2.

## 1. Диагноз в одной таблице

| # | Проблема | Факт | Следствие |
|---|---|---|---|
| P1 | Подменю не учитывают направление | у всех 13 пунктов Einstellungen `module_key=None`, нет `business_types` (`nav_registry.py:691-808`); Lager/Einkauf/Kombi/Import/Kategorien/Kollektionen видны отелю и ремеслу — `catalog` core, гейт только по модулю (`modules.py:554`, `nav_registry.py:649-656`) | 38–46 подпунктов на тип (KA-0 §6); у отеля «Einkauf» и «Kombi» |
| P2 | Настройки живут в «Verkäufe» | «Öffnungszeiten & Ressourcen», «Tage blockieren», «Abläufe & Status» — в Verkäufe (`nav_registry.py:261,270,309`) | владелец ищет часы работы в продажах |
| P3 | Финансы и отчёты в «Verkäufe», ERP-экраны без меню | Auswertungen/Finanzen/Berichte в Verkäufe; Ausgaben/Ergebnis/Offene Posten/Bank/Rechnungen — только Ctrl+K (`:384-467`) | 5 рабочих экранов недостижимы на телефоне (палитры там нет) |
| P4 | Marketing — 13–18 пунктов вперемешку | порядок `:469-598`: акции, клиенты, коммуникация, видимость перемешаны без подписей | самый длинный и самый непонятный раздел |
| P5 | Один и тот же объект — разные имена | Sortiment/Angebot, Kunden/Kontakte, Übersicht/Start/Dashboard, Zahlungen ×3, 30 пар «пункт меню ≠ заголовок страницы» (разведка, §5) | нарушение глоссария; владелец не узнаёт страницу, на которую нажал |
| P6 | Страницы-посредники без своей функции | `marketing-home` (всё — ссылки и копия матрицы уведомлений, `marketing_home.py:22-164`), `integrations-home` (карточки-ссылки, `views.py:5928-6000`) | лишний клик |
| P7 | Мобильный таб-бар — первые 4 якоря без подписей | `nav_primary=_compact[:4]` (`context.py:460-471`), подписи только в aria-label; «Mehr» = весь сайдбар (`_base_dashboard.html:190-260`); Einstellungen в таб-бар не попадает | на телефоне нет «＋» и «Nachrichten», иконки без слов |
| P8 | Главная не отвечает на «что делать сейчас» | виджеты без пустых состояний (нули), полоса «Heute» убрана в X3, «Mehr verkaufen» отсутствует (`dashboard.html`, `dashboard.py:105-215`) | — |
| P9 | Мёртвые/скрытые входы | блок «More tools» в Studio скрыт навсегда — `showArea("library")` никто не вызывает (`site_home.html:1384,1451`) → `site-preview` только со второго уровня; `onboarding.py:129 tile_url` не используется; комментарий-сирота `nav_registry.py:806` | — |

## 2. Принципы целевой структуры

1. **Якоря те же шесть** (мораторий X7 сохраняем): Übersicht · Verkäufe · Sortiment · Marketing ·
   Website · Einstellungen. Меняется только состав и порядок подпунктов.
2. **Подпункт виден, только если он нужен направлению** — у каждой записи реестра обязателен гейт:
   модуль, направление (`directions`) или пакет/область (KA-3 §2.1). Запись «для всех» допустима
   только для действительно общих экранов (бизнес, право, оплата, уведомления, команда).
3. **Работа — в Verkäufe, настройка — в Einstellungen.** Экран, который меняют раз в месяц
   (часы, ресурсы, статусы, блокировки дат), — в Einstellungen, в группу своего направления.
4. **Один объект — одно имя — один вход.** Подпись в меню = `<h1>` страницы = термин глоссария.
5. **Не больше 7 подпунктов без группы.** Длиннее — подзаголовки групп внутри подменю (как в
   обзоре `einstellungen-home`, `settings_home.py:19-28`).
6. **Страница-посредник живёт, только если у неё есть своя работа** (сводка с действиями), иначе
   якорь ведёт сразу на первый рабочий экран.

## 3. Целевая карта (Laden; Website — то же без продаж/оплаты, KA-3 §3.3)

`[мод]` — гейт модулем, `[напр]` — направлением, `[own]` — только владельцу, `[Profi]` — дополнение.

### 3.1 Übersicht
Одна страница (§6). Подпунктов нет.

### 3.2 Verkäufe — только ежедневная работа
| Подпункт | Сейчас | Решение |
|---|---|---|
| Verkäufe (виды Kalender/Board/Liste + вкладки направлений) | есть | оставить, первый |
| Heute (`verkaeufe?view=heute`) | есть, без пункта | **вернуть пунктом** для Zimmer/Termine/Waren-с-выдачей |
| Lieferungen `[мод orders]` | есть | оставить |
| Check-ins `[мод stays]` | есть | оставить |
| Küche (KDS) `[напр gastro]` | «Kitchen Display» | переименовать «Küche» |
| Reservierungen | только палитра | вкладкой Verkäufe по общему правилу (D8, уже так) — запись палитры убрать |
| Kunden `?tab=kunden` | есть | **убрать** из Verkäufe → единый «Kunden» в Marketing (D2) |
| Zahlungen (журнал оплат) | есть | → якорь **Finanzen-группа** (см. 3.6) |
| Abläufe & Status | есть | **убрать** (D3) → Einstellungen › Verkauf |
| Öffnungszeiten & Ressourcen, Tage blockieren | есть | → Einstellungen › Termine (P2) |
| Auswertungen, Finanzen, Berichte | есть | → группа «Zahlen & Finanzen» (3.6) |

Итог: 2–5 подпунктов вместо 5–8.

### 3.3 Sortiment — сущности направления
| Подпункт | Гейт (новый) |
|---|---|
| Sortiment (все позиции, Kacheln/Liste) | всегда |
| Produkte → Kategorien | `[напр Waren]` |
| Leistungen · Karten & Abos | `[мод booking]` |
| Zimmer & Preise | `[мод stays]` |
| Veranstaltungen · Reisen · Gastgeber | `[мод events]` |
| Kombi | `[напр Waren, Gastro]` |
| Kollektionen | `[напр Waren]` (сейчас без гейта) |
| Zusatzleistungen (Extras) | `[мод booking/stays/events]` — **переезд из Einstellungen** (это продаваемые позиции) |
| Import | `[напр Waren]` |
| Lager · Einkauf | `[Profi Lager]` |

У отеля: Sortiment · Zimmer & Preise · Zusatzleistungen (было 8–9). У ремесла (только jobs):
Sortiment (позиции для сметы).

### 3.4 Marketing → «Marketing & Kunden» (название — вопрос В-2)
Подменю с тремя подзаголовками:

| Группа | Подпункты |
|---|---|
| **Kunden** | Nachrichten `[мод inbox]` · Kunden (CRM, единственный список, D2) `[мод crm]` · Bewertungen `[мод reviews]` |
| **Aktionen** | Aktionen · Aktionstypen · Einlösen (одна касса, D7) `[мод promotions]` · Gutscheine · Treuepunkte `[мод loyalty]` |
| **Reichweite** | Kampagnen · Newsletter · Beiträge · Kanäle (публикации) · Blog `[мод blog, выкл по умолчанию — В-3]` · Stadtportal `[own, только при участии в каталоге города]` |

- `marketing-home` → убрать как отдельный пункт; якорь ведёт на «Nachrichten» (если inbox) или
  «Aktionen». Метрики (просмотры, кампании, отзывы) → на главную (§6) и на свои экраны (P6).
- «Telegram» (бот бизнеса) → Einstellungen › Kanäle & Benachrichtigungen (это настройка, D5).
- Firmen (палитра) — вкладкой внутри «Kunden».

### 3.5 Website
Studio · Design · SEO · Domains · Medien — без изменений по составу. Починить: блок «More tools»
(или убрать `site-preview` как экран — он дублирует превью Studio), подписи = заголовки (§5).

### 3.6 Einstellungen — «базовые» + «по направлению» + «Zahlen & Finanzen»
Подменю с подзаголовками (обзор `einstellungen-home` остаётся первым пунктом):

| Группа | Подпункты | Класс |
|---|---|---|
| **Geschäft** | Mein Geschäft · Recht & Steuern `[own]` · Sprachen · Team & Zugriff `[own]` | база |
| **Verkauf** | Zahlarten & Lieferung (D4) · Abläufe & Status (D3, единственный вход) | база, если есть продажа |
| **Termine** `[мод booking]` | Öffnungszeiten & Ressourcen · Tage blockieren | направление |
| **Zimmer** `[мод stays]` | Verkaufsregeln · Channel Manager (из палитры) | направление |
| **Kanäle & Benachrichtigungen** | одна страница (D5): уведомления владельца и клиентов, Telegram, публикации, Google-профиль/Merchant/Bewertungen карточками | база |
| **Zahlen & Finanzen** | Zahlungen (журнал) · Rechnungen · Auswertungen `[мод analytics]` · Berichte `[мод stays]` · Finanzen-ERP: Journal/Ausgaben/Ergebnis/Offene Posten/Bank `[Profi Finanzen]` | **В-1**: здесь или отдельным 7-м якорем |
| **System** | Funktionen · Abo & Rechnung `[own]` · Finder `[опция витрины]` · Hilfe | редко |

- `integrations-home` → слить с «Kanäle & Benachrichtigungen» (P6, D5).
- `billing-payments` («Zahlungen empfangen», только палитра) → секция Stripe внутри «Zahlarten» (D4).
- «Hilfe» — также иконкой в шапке (к настройкам по смыслу не относится).
- «Recht & Steuern»: подпись обещает «USt-Sätze» (`settings_home.py:33`), на экране их нет → исправить подпись.

## 4. Решения по дублям D1–D12 (KA-0 §3)

| # | Решение | Причина |
|---|---|---|
| D1 9 легаси-редиректов | оставить редиректы, вынести в отдельный реестр `legacy`, не считать экранами | дёшево, сохраняет закладки |
| D2 Kunden ↔ Kontakte | **слить**: один «Kunden» в Marketing & Kunden; вкладку `?tab=kunden` убрать | один и тот же партиал/контекст |
| D3 Abläufe ×2 + status-manager | один вход в Einstellungen › Verkauf; `status-manager/<kind>/` → редирект на секцию | редактор уже встроен в Abläufe (`views.py:5462`) |
| D4 Zahlungen ×3 | «Zahlungen» (журнал) → Zahlen & Finanzen; «Zahlarten & Lieferung» — настройки; `billing-payments` слить в «Zahlarten» | три похожих имени |
| D5 подключения ×5 | одна страница «Kanäle & Benachrichtigungen» | KA-0 §3 |
| D6 исходящий контент ×4 | группа «Reichweite»; блог выключен по умолчанию (В-3) | решение владельца «блоги убрать» |
| D7 Einlösen ×2 | один экран с автоопределением кода (резерв/купон/ваучер) | два сканера |
| D8 Reservierungen | только вкладка Verkäufe (полный кабинет), экран — в лёгком | уже так по W10-2 |
| D9 site-menu/sections/preview | menu, sections — входы есть; preview — убрать как экран или вернуть «More tools» | P9 |
| D10 Geschäft ↔ Mein Geschäft | один источник полей (форма-подмножество) | KA-3 |
| D11 статистика видимости | на главной блок «Sichtbarkeit»; `portal-stats` — экран деталей | три места |
| D12 хаб `catalog` | удалить хаб, записи — только в `sellables` | технический дубль |

## 5. Названия (глоссарий → меню → `<h1>`)

Правило: **одна строка на объект**; подпись меню и заголовок страницы берутся из одной записи
реестра (`Entry.label` → `dash_title` через тег), а не пишутся дважды. Ключевые правки:

| Объект | Сейчас (меню / заголовок) | Целевое |
|---|---|---|
| ассортимент | Sortiment / «Angebot» (лёгкий) | **Sortiment** везде; «Angebot» = только оферта клиенту |
| клиенты | Kunden / Kontakte / Customers | **Kunden** |
| главная | Übersicht / Start / Dashboard | **Übersicht** (полный), **Start** (лёгкий) — оставить осознанно |
| заявки | Aufträge / Neue Anfrage | **Anfragen** (входящее) и **Aufträge** (принятое) — по статусу, как в глоссарии |
| оплата | Zahlungen / Zahlung und Versand / Kundenzahlungen | **Zahlungen** (журнал), **Zahlarten & Lieferung** (настройки) |
| отзывы | Bewertungen / Rezensionen | **Bewertungen** |
| сообщения | Nachrichten / Posteingang | **Nachrichten** |
| услуги | Leistungen / Dienstleistungen | **Leistungen** |
| номера | Zimmer & Preise / Einheiten | **Zimmer & Preise** |
| ведущие | Gastgeber / Lehrer | **Gastgeber** |
| подборки | Kollektionen / Sammlungen | **Kollektionen** |
| модули | Funktionen / Module | **Funktionen** |
| допы | Zusatzleistungen / Extras | **Zusatzleistungen** |
| кампании | Kampagnen / Gutscheinaktionen | **Kampagnen** (термин «Aktion» не трогаем) |
| английское в DE | Board, Dashboard, Kitchen Display, Channel Manager, Blog & News | Tafel? (В-4) · Übersicht · Küche · Kanal-Manager · Blog |

Полный список 30 расхождений — в разведке (приложение A ниже). Глоссарий пополняется этими строками.

## 6. Главная (Übersicht) — что делать сейчас

Порядок блоков (рынок: Shopify Home, Smoobu, Shore — «дела, потом цифры»):

1. **Zu erledigen** — карточки-действия с числом и кнопкой: новые сообщения, заявки без ответа,
   отложено к выдаче, заказы к отправке, заезды сегодня, отзывы без ответа. Пусто → «Alles erledigt ✓».
2. **Heute** — петля направления (как сейчас, `_sales_body.html`), но компактно, с «Alle anzeigen».
3. **Zahlen der Woche** — оборот, просмотры, акции; **нули не показываем** — вместо нуля подсказка
   первого шага («Erste Aktion starten»).
4. **Nächster Schritt** — чек-лист готовности (KA-3 §5) / «Laden eröffnen» / «Mehr verkaufen».
5. Присутствие «Jetzt erreichbar» и «Was heute starten?» — внутри блоков 1/3, не отдельно.

Пустые состояния — у каждого виджета (P8).

## 7. Мобильный кабинет (Laden)

- Таб-бар **с подписями**: Übersicht · Verkäufe · **＋** (создать по направлению: заказ/запись/
  бронь/заявку/акцию) · Nachrichten (или Sortiment, если inbox выключен) · Mehr.
- «Mehr» — лист с остальными якорями и подзаголовками групп, а не весь сайдбар.
- Палитра Ctrl+K на телефоне — поле поиска вверху листа «Mehr» (сейчас недоступна).
- Детально — KA-6.

## 8. Как держать структуру (замки, при реализации)

- Каждая запись `nav_registry` обязана иметь гейт или явный флаг `universal=True` с причиной.
- Число подпунктов якоря ≤ 7 без групп; с группами — каждая группа ≤ 7.
- Подпись меню = `<h1>` страницы (тест сверяет по реестру).
- Ни одна запись не `palette_only`, если это рабочий экран (мобильный не видит палитру).
- Матрица «тип × подменю» снимком (16 типов) — изменение только осознанно.

## 9. Вопросы владельцу

| № | Вопрос | Рекомендация |
|---|---|---|
| **В-1** | «Zahlen & Finanzen» (журнал оплат, счета, отчёты, ERP) — группа в Einstellungen или **седьмой якорь «Finanzen»**? | Седьмой якорь **только при Profi Finanzen или включённой аналитике**; иначе группа в Einstellungen. Требует снять мораторий X7 для одного якоря |
| **В-2** | Переименовать «Marketing» → **«Marketing & Kunden»**? | Да — клиенты и сообщения живут здесь |
| **В-3** | Блог: выключить по умолчанию у всех типов (сейчас рекомендован всем 16)? | Да; включается в «Funktionen» |
| **В-4** | «Board» (вид продаж): оставить англ. или «Tafel»/«Spalten»? | «Spalten» — понятнее, чем Kanban/Tafel |
| **В-5** | Часы/ресурсы/блокировки дат — переносим из Verkäufe в Einstellungen? | Да (P2) |
| **В-6** | `marketing-home` и `integrations-home` — убрать как страницы? | Да, их содержимое — на главной и в «Kanäle & Benachrichtigungen» |

## Приложение A. Расхождения «пункт меню ≠ заголовок»

Bewertungen/Rezensionen · Nachrichten/Posteingang · Beiträge/Content-Kalender · Kanäle/Veröffentlichungskanäle ·
Leistungen/Dienstleistungen · Zimmer & Preise/Einheiten · Karten & Abos/Mehrfachkarten · Gastgeber/Lehrer ·
Kollektionen/Sammlungen · Import/Produktimport · Öffnungszeiten & Ressourcen/Ressourcen & Öffnungszeiten ·
Tage blockieren/Verfügbarkeit · Check-ins/Online-Check-ins (Meldescheine) · Berichte/Auslastung und Umsatz ·
Auswertungen/Aktions-Auswertung · Finanzen/Umsatzjournal · Mein Geschäft/Geschäftseinstellungen ·
Recht & Steuern/Rechtliches · Benachrichtigungen & Kanäle/Benachrichtigungen · Abläufe & Status/Abläufe ·
Abo & Rechnung/Rechnungsstellung · Funktionen/Module · Zusatzleistungen/Extras · Website/Homepage·Studio ·
Medien/Medienbibliothek · Website & Domains/Domains · Hilfe/Hilfe & Support · Stadtportal/Besuche aus dem Stadtportal ·
Kampagnen/Gutscheinaktionen · Treuepunkte/Treueprogramm(e). Плюс: Verkäufe с одним видом сделок показывает
`<h1>` вкладки («Aufträge») вместо «Verkäufe» (`core/verkaeufe.html:32,46`) — оставить осознанно.
Пустые msgstr: «Zahlungen empfangen» (po:18939), «Channel Manager».

**Решения владельца 2026-10-23: В-1…В-6 — по рекомендации.** Седьмой якорь «Finanzen» —
только при Profi Finanzen или включённой аналитике (мораторий X7 снимается ровно для него) ·
«Marketing & Kunden» · блог выключен по умолчанию · «Board» → «Spalten» · часы/ресурсы/блокировки →
Einstellungen · `marketing-home` и `integrations-home` убираются.
