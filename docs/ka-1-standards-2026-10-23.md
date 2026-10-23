# KA-1 · Стандарты и законы для кабинета продавца (срез на 2026-10-23)

Формат строки: **правило → источник → как проверяем в кабинете → экраны → приоритет**.
Приоритет: **З** = закон (санкция/Abmahnung), **З?** = закон, применимость спорна/зависит от клиента,
**Р** = рекомендация/стандарт. ⚠️ = точка неуверенности (проверить юристом/первоисточником).
Это не юридическая консультация; первоисточники указаны.

## 0. Карта применимости (кто кому должен)

| Поверхность | Кто обязан | Ключевые режимы |
|---|---|---|
| Кабинет продавца (web/mobile/Mini App) | мы (B2B-сервис бизнесу) | DSGVO (мы — Auftragsverarbeiter для данных клиентов бизнеса, Verantwortlicher для данных владельца), TDDDG §25, DSA (хостинг), AI Act Art. 50. **BFSG — нет** (чистый B2B, см. §1.2). WCAG 2.2 AA — как стандарт качества (Р). |
| Витрина бизнеса (B2C) | бизнес (мы — техн. исполнитель, де-факто отвечаем за шаблоны) | BFSG (кроме микро-исключения), PAngV, UWG, BGB §312j/Widerruf, DDG §5, LMIV, TDDDG. |
| Каталог города (портал) | мы | DSA (hosting + online platform), UWG §5a (Anzeige), BFSG ⚠️ (если через портал заключаются B2C-сделки), DSGVO. |
| Документы, генерируемые кабинетом (счета, Kassen-, DATEV) | бизнес; мы — «Aufzeichnungssystem» ⚠️ | UStG §14, GoBD, E-Rechnung, KassenSichV ⚠️. |

## 1. Доступность

### 1.1 WCAG 2.2 AA — ключевые критерии для веб-приложения
Источник: W3C WCAG 2.2 (Rec. 05.10.2023, обновл. 12.12.2024) — https://www.w3.org/TR/WCAG22/ ; Understanding — https://www.w3.org/WAI/WCAG22/Understanding/

| Критерий | Как проверяем в кабинете | Экраны | Пр. |
|---|---|---|---|
| **2.5.8 Target Size (Minimum)** — цель ≥24×24 CSS px или достаточный отступ | Playwright: bbox всех `a,button,input[type=checkbox|radio],[role=button]` < 24px без spacing 24px → список; особо: пилюли статуса, «✕» чипов, иконки 📷/🗑, «⋯», чекбоксы списков | Verkäufe (доска/список), Sortiment Liste, Studio-плашки, таб-бар, фильтры | Р (З для витрин под BFSG — через EN 301 549 v4) |
| **2.4.11 Focus Not Obscured (Minimum)** — фокус не закрыт sticky-элементами | Tab-обход: элемент в фокусе не под sticky-Save, плавающим таб-баром, FAB «＋», bottom-sheet, тостом | Mein Geschäft (sticky Save), мобильный кабинет, Studio | Р |
| **2.4.7 Focus Visible** + видимое кольцо | CSS-аудит `outline:none` без замены | все | Р |
| **2.5.7 Dragging Movements** — у каждого drag есть альтернатива одним указателем | Канбан (drag карт) → есть меню статуса? Колонки «как в Trello» → кнопки ↑↓? Studio drag блоков, сортировка фото, Belegungsplan drop | Verkäufe Board, Abläufe, Studio, галерея товара, Belegungsplan | Р |
| **3.3.8 Accessible Authentication (Minimum)** — без когнитивного теста; paste/менеджер паролей разрешены | Поля логина/пароля/2FA/кодов: нет `onpaste` блокировки, `autocomplete=current-password/one-time-code`; magic-link/Telegram-вход как альтернатива | вход, регистрация, team-invite, Mini App | Р |
| **3.2.6 Consistent Help** — помощь в одном и том же месте | «Hilfe»/чат поддержки — одинаковое положение на всех экранах | шапка/сайдбар | Р |
| **3.3.7 Redundant Entry** — не просить повторно введённое | Повторный ввод адреса/реквизитов (Zahlung vs Rechnung), мастер ↔ настройки, Vorkasse-IBAN | мастер, Zahlung & Lieferung, Recht & Steuern, карточка сделки | Р |
| 1.4.3/1.4.11 Контраст 4.5:1 / 3:1 (UI) | axe-core на светлой и тёмной теме; пастельные чипы статусов, серые подписи 11px | все, особенно чипы статусов | Р |
| 1.4.10 Reflow (320 CSS px) / 1.4.4 zoom 200% | Скриншоты 320px и zoom 200%: нет горизонтального скролла кроме таблиц/доски | все | Р |
| 3.3.1/3.3.3 Ошибки ввода текстом + подсказка | Ошибка у поля, `aria-describedby`, не только цвет; скрытые вкладки с invalid (урок SR-2d) | формы товара/акции/настроек | Р |
| 4.1.2/4.1.3 Name-Role-Value, Status Messages | Иконочные кнопки с `aria-label`; тосты/«Gespeichert» в `role=status` | все | Р |
| 2.1.1/2.1.2 Клавиатура, нет ловушек | `<dialog>`/bottom-sheet/поповеры: Esc, возврат фокуса | модалки статусов, Studio | Р |

### 1.2 BFSG (Barrierefreiheitsstärkungsgesetz) — в силе с 28.06.2025
Источники: BFSG — https://www.gesetze-im-internet.de/bfsg/ ; BFSGV — https://www.gesetze-im-internet.de/bfsgv/ ; Leitlinien BMAS — https://www.bmas.de (Leitlinien für die Anwendung des BFSG); IHK-обзор — https://www.ihk.de/gera/recht-und-steuern/fokus-onlinehandel/barrierefreiheit-im-onlinehandel-6545152

| Вопрос | Вывод | Пр. |
|---|---|---|
| Кабинет продавца (B2B) | Не «Dienstleistung im elektronischen Geschäftsverkehr» для **Verbraucher** → BFSG не применяется. Условие: кабинет явно только для предпринимателей (регистрация «für Unternehmen», AGB B2B). | — (Р: всё равно WCAG 2.2 AA) |
| Витрины бизнесов (B2C-онлайн-продажа/бронь) | Применяется к бизнесу как поставщику услуги ЭК, **если** он не Kleinstunternehmen. Kleinstunternehmen (§2 Nr. 17: <10 сотрудников **и** ≤2 млн € оборота/баланса) — исключение для **услуг** (§3 Abs. 3). Большинство наших пекарен/салонов — исключены; отели, сети, Handwerker >10 чел. — нет. Чистая визитка без онлайн-заключения договора ⚠️ — вероятно вне скоупа. | З? (по клиенту) |
| Каталог города | Если через портал потребитель заключает договор (резерв/купон/бронь/заказ) — наша услуга ЭК; исключение микро — только если мы <10 чел. и ≤2 млн €. ⚠️ проверить статус компании. | З? |
| Что требуется | Anlage 1/BFSGV: воспринимаемость/управляемость/понятность/робастность (≈ WCAG AA через EN 301 549) + **Erklärung zur Barrierefreiheit** (информация о соответствии в AGB/на сайте, BFSGV §§ 14 ff./Anlage 3) + механизм обратной связи. | З? |
| Как проверяем | Генерирует ли платформа на витрине страницу «Barrierefreiheit» (шаблон-заявление), есть ли в кабинете переключатель/статус; axe-прогон шаблонов витрины (все Look'и/сборки). | — |

### 1.3 EN 301 549
Источник: ETSI EN 301 549 — https://www.etsi.org/standards ; обзор v4.1.1 — https://www.deque.com/blog/en-301-549-v4-1-1-is-final-what-changed-what-it-means-and-what-you-should-do/
- Гармонизированный сейчас — **V3.2.1** (ссылается на WCAG **2.1** AA). **V4.1.1** опубликована 09.2026 и переходит на **WCAG 2.2** AA; цитирование в OJ EU ожидается ~16.12.2026 ⚠️ (дата целевая). Вывод: мерить по WCAG 2.2 AA уже сейчас (покрывает обе версии). Для нативных частей (Telegram Mini App = веб) — те же web-критерии (гл. 9) + гл. 11 «software» неприменима к веб.

## 2. Защита данных

Источники: DSGVO — https://eur-lex.europa.eu/eli/reg/2016/679/oj ; TDDDG — https://www.gesetze-im-internet.de/ttdsg/ ; DSK Orientierungshilfe Telemedien 2024 — https://www.datenschutzkonferenz-online.de/orientierungshilfen.html ; EDPB Guidelines 4/2019 (Art. 25) — https://www.edpb.europa.eu

| Правило | Как проверяем в кабинете | Экраны | Пр. |
|---|---|---|---|
| **Art. 5(1)(c) минимизация** | Инвентарь полей форм: обязательные поля клиента (телефон+e-mail+адрес?) при резерве/купоне/заявке; не собирать дату рождения/пол без цели; поля «на будущее» убрать | формы витрины, CRM-карточка, мастер регистрации | З |
| **Art. 5(1)(e) ограничение хранения / сроки** | Есть ли сроки: неподтверждённые подписки, логи, Meldeschein (1 год BMG §30), документы MT-2 (90 дн.), бот-данные (30/180), заказы/счета (10 лет AO §147 / HGB §257 — 8 лет для Buchungsbelege с 2025 ⚠️ Bürokratieentlastungsgesetz IV) — и видно ли это владельцу | Kunden/CRM, Dokumente, Einstellungen | З |
| **Art. 12–15 Auskunft** | Может ли владелец бизнеса выгрузить всё по клиенту (заказы, брони, переписка, согласия) одним действием в разумный срок (1 мес.) | Kunden → карточка 360° | З |
| **Art. 16 Berichtigung / 17 Löschung / 18 Einschränkung** | Редактирование клиента; «Kunde löschen» с учётом удержания налоговых документов (блок/анонимизация вместо удаления); флаг ограничения | Kunden, Verkäufe | З |
| **Art. 20 Datenübertragbarkeit** | CSV/JSON-экспорт клиента | Kunden | З |
| **Art. 21 Widerspruch** (маркетинг) | Отписка в один клик, статус согласия видим в CRM, кампании исключают отписавшихся | Marketing/Kampagnen, Newsletter | З |
| **Art. 25 Privacy by design/default** | Дефолты: маркетинг-чекбоксы НЕ отмечены, видимость в каталоге города — осознанное согласие, публичные профили без лишних данных, сотрудник по умолчанию с минимальной ролью | Mein Geschäft, Team, Marketing | З |
| **Art. 28 AVV** | Мы — обработчик данных клиентов бизнеса → AVV-договор принимается при регистрации, доступен в кабинете (скачать/дата принятия), список субобработчиков (Hetzner, Resend, Stripe, Telegram, ИИ-провайдеры ЕС) с уведомлением об изменениях | Abo & Rechnung / Recht | З |
| **Art. 30 Verzeichnis** | Шаблон VVT для бизнеса (помощь, не обязанность платформы) | Recht & Steuern | Р |
| **Art. 32 безопасность** | 2FA для владельца, сессии/выход со всех устройств, журнал входов, шифрование секретов (P0-3), ролевой доступ | Team & Zugriff, профиль | З |
| **Роли/least privilege** | Матрица ролей owner/admin/staff: staff не видит финансы, экспорт клиентов, IBAN, Abo (сейчас admin=staff — пробел); проверка на сервере, не только скрытие меню | Team, все owner-only разделы | З (Art. 32) |
| **Art. 33/34 утечки** | Процесс (не экран) — Р; уведомление бизнесам | — | З |
| **Art. 13 информирование** | Генерируемая Datenschutzerklärung витрины отражает реально включённые модули (Telegram, ИИ, карты, Stripe) | Recht / LegalDoc | З |
| **TDDDG §25** cookies/localStorage | Аудит хранилищ кабинета и витрины: сессия/CSRF/язык/вид списка = «unbedingt erforderlich» (§25 Abs. 2 Nr. 2) — без баннера; любые аналитика/трекинг/внешние шрифты-CDN/карты-тайлы до клика — нужно согласие или замена; Telegram-WebApp-скрипт только в Mini App ⚠️ | витрина, кабинет | З |
| **Art. 44 ff. третьи страны** | ИИ (AI_REQUIRE_EU), Telegram (вне ЕС ⚠️ — информировать), Google GBP/Merchant | Integrationen | З |

## 3. Торговое право — что кабинет показывает/производит

| Правило | Источник | Как проверяем в кабинете | Экраны | Пр. |
|---|---|---|---|---|
| **Impressum §5 DDG** (с 14.05.2024 вместо §5 TMG) | https://www.gesetze-im-internet.de/ddg/__5.html | Мастер/Mein Geschäft требует: имя/фирма, юр. форма, представитель, адрес (не PO-Box), e-mail + 2-й быстрый канал, Handelsregister+№, USt-IdNr/W-IdNr, Kammer/Berufsrecht для Handwerk/Friseur ⚠️; публикация витрины блокируется без минимума («Gate готовности») | Recht & Steuern, мастер | З |
| **ODR-ссылка** | VO (EU) 2024/3228 — https://eur-lex.europa.eu/eli/reg/2024/3228/oj | Платформа ОДР закрыта с **20.07.2025** — ссылку УБРАТЬ из Impressum/AGB-шаблонов. **Остаётся** §36 VSBG (информация об участии в Verbraucherschlichtung) для бизнесов >10 сотрудников с AGB/сайтом | Recht, шаблоны правовых страниц | З |
| **PAngV §3/§4 Gesamtpreis + Grundpreis** | https://www.gesetze-im-internet.de/pangv_2022/ | Форма товара: при весовых/объёмных — поле Menge+Einheit обязательно, витрина показывает €/kg, €/l рядом с ценой (не мельче/не в hover) | форма товара/акции, витрина | З |
| **PAngV §11 (30-дневная низшая цена)** | там же; EuGH C-330/23 (26.09.2024) | При «statt/−%» сравнение ТОЛЬКО с низшей ценой 30 дней (кабинет считает и показывает владельцу); исключение §11 Abs. 4 скоропортящееся | акции, Preis-Historie | З |
| **UWG §5a Abs. 4 (кенн. рекламы)** | https://www.gesetze-im-internet.de/uwg_2004/__5a.html | «★ Anzeige» у платных размещений в каталоге; отзывы — §5b Abs. 3 (сообщить, проверяются ли отзывы и как) | Marketing/★ Feature, Bewertungen | З |
| **UWG §7 рассылки** | https://www.gesetze-im-internet.de/uwg_2004/__7.html | Double-Opt-In e-mail/Telegram/WhatsApp; исключение §7 Abs. 3 (существующий клиент, похожие товары, указание на отказ при каждом письме) — кабинет различает базы и показывает основание согласия + журнал DOI | Kampagnen, Newsletter, CRM | З |
| **BGB §312j Abs. 3 «Button-Lösung»** | https://www.gesetze-im-internet.de/bgb/__312j.html | Платная кнопка витрины «zahlungspflichtig bestellen/buchen»; кабинет не даёт переименовать её в нейтральное | Studio (тексты кнопок), чекаут | З |
| **BGB §312j Abs. 1–2 / Art. 246a EGBGB** | там же | Перед заказом: способы оплаты, ограничения доставки, сущ. признаки | чекаут | З |
| **Widerrufsbelehrung + Muster-Widerrufsformular (§355/§356 BGB, Anl. 1/2 EGBGB)** | https://www.gesetze-im-internet.de/bgbeg/ | LegalDoc генерирует; учёт исключений §312g Abs. 2 (скоропортящееся, по мерке, услуги досуга с датой — отели/события/рестораны **без** права отзыва) — мастер подставляет по архетипу | Recht | З |
| **Widerrufsbutton (§356a BGB, с 19.06.2026)** ⚠️ | RL (EU) 2023/2673; https://eur-lex.europa.eu/eli/dir/2023/2673/oj | Для договоров, заключённых онлайн — электронная «Vertrag widerrufen»-функция. Проверить вступление в силу немецкой имплементации и есть ли она у витрины | витрина, кабинет (входящие отзывы) | З (⚠️ дата/текст проверить) |
| **GoBD** | BMF 28.11.2019 + изменения BMF 14.07.2025 (E-Rechnung) ⚠️ — https://www.bundesfinanzministerium.de | Счета: непрерывная нумерация, неизменяемость после выставления (сторно вместо правки), Verfahrensdokumentation-шаблон, экспорт для проверки (DATEV/GDPdU-«Z3»), хранение 8/10 лет | Finanzen, Rechnungen, Offene Posten | З |
| **UStG §14/§14a + E-Rechnung** | Wachstumschancengesetz; BMF 15.10.2024 | Приём e-инвойса с 01.01.2025 (входящие счета ERP-3 должны принимать XRechnung/ZUGFeRD); **выставление** B2B e-инвойса обязательно с 01.01.2027 (оборот >800 тыс.) / 01.01.2028 (все); Kleinbetrag ≤250 € и Kleinunternehmer — исключения. Проверить: формат счёта фирме (CO-2) — PDF сейчас → нужен ZUGFeRD/XRechnung | Rechnungen, Eingangsrechnungen | З (с 2027) |
| **KassenSichV / §146a AO / TSE** ⚠️ | https://www.gesetze-im-internet.de/kassensichv/ | Если кабинет используется как «elektronisches Aufzeichnungssystem mit Kassenfunktion» для **наличных** (касса Mini App, «Als bezahlt markieren» при оплате на месте, выдача у прилавка) → нужна TSE, Belegausgabe, Meldung (§146a Abs. 4, с 01.01.2025 через ELSTER). Оценка: сейчас платформа — учёт заказов, не касса; **не позиционировать как Kasse** и показывать «Barzahlung bitte in Ihrer Kasse erfassen» | касса Mini App, Zahlungen | З? (⚠️ ключевой риск — юрист) |
| **LMIV (VO 1169/2011) + LMIDV** | https://eur-lex.europa.eu/eli/reg/2011/1169/oj | Art. 14: при дистанционной продаже обязательная информация ДО заказа (аллергены Art. 9/21 выделены, состав, Nettofüllmenge, Hersteller); для loser Ware — аллергены (LMIDV §4); кабинет: поля аллергенов/состава для FOOD-архетипов, нельзя опубликовать пищевой товар без отметки аллергенов («keine» — явно) | форма товара (Kennzeichnung), Speisekarte-PDF | З |
| **AI Act Art. 50** | VO (EU) 2024/1689 — https://eur-lex.europa.eu/eli/reg/2024/1689/oj ; AI-Omnibus | С **02.08.2026** действуют 50(1) (уведомление о взаимодействии с ИИ — чат/ответы клиентам) и 50(4) (дипфейки/ИИ-текст для общественной информации). 50(2) машиночитаемая маркировка — для систем на рынке до 08.2026 до 02.12.2026. Мы — deployer чужих моделей: метка «✨ KI-Vorschlag» на черновиках, ИИ-ответ клиенту отправляет человек (тогда 50(4) обычно не триггерится — редакционный контроль); если когда-либо авто-ответ ботом — явное «Sie chatten mit einem KI-Assistenten» | Nachrichten (Antwort vorschlagen), ассистент акции, Text-Check, импорт сайта, MCP | З |
| **DSA — все хостинг-провайдеры** | VO (EU) 2022/2065 — https://eur-lex.europa.eu/eli/reg/2022/2065/oj ; DDG §§ (BNetzA) | Art. 11/12 контакт-точки, Art. 14 AGB (модерация), **Art. 16 Notice & Action** (форма «Melden» с обоснованием, подтверждение получения), **Art. 17 Statement of reasons** бизнесу при скрытии его листинга/акции (в кабинете: уведомление «скрыто, потому что…» + обжалование) — микро-исключения для §16/17 НЕТ | каталог города, кабинет (уведомления о модерации) | З |
| **DSA — online platform / marketplace** | Art. 19/29 | Art. 20 внутреннее обжалование, Art. 26 реклама (кто платит), Art. 30 **trader traceability** (имя, адрес, контакт, ID, регистр, самосертификация) — **не применяются**, если мы micro/small (<50 чел., ≤10 млн €) ⚠️ проверить статус и «12-месячный» хвост. Хорошая практика: Art. 30-набор уже совпадает с Impressum-полями — собирать и проверять до показа в каталоге | каталог города, онбординг | З? |
| **P2B-VO (EU) 2019/1150** ⚠️ | https://eur-lex.europa.eu/eli/reg/2019/1150/oj | Каталог города = посредник для бизнес-пользователей: прозрачные AGB, параметры ранжирования (Art. 5) — описать «как сортируется выдача» и роль ★ Feature; уведомление об изменении условий за 15 дней; микро-исключение только для внутреннего жалобного механизма | каталог, AGB платформы | З |

## 4. UX/мобильные гайдлайны для админ-приложений

Источники: Apple HIG — https://developer.apple.com/design/human-interface-guidelines/ (Layout, Buttons, Tab bars); Material 3 — https://m3.material.io/ (Accessibility/Touch targets, Navigation bar); web.dev Core Web Vitals — https://web.dev/articles/vitals ; INP — https://web.dev/articles/inp

| Правило | Значение | Как проверяем | Экраны | Пр. |
|---|---|---|---|---|
| Touch target | iOS **44×44 pt**, Android **48×48 dp** (видимая иконка может быть меньше, зона — нет); WCAG 2.5.8 24px — минимум, 44/48 — цель для мобильного | Playwright 390px: доля целей <44px | мобильный кабинет, Mini App | Р |
| Нижняя навигация | M3 Navigation bar **3–5** пунктов; iOS tab bar ≤5 (иначе «Mehr»); пункты = разделы, не действия; подписи всегда | таб-бар: число пунктов, подписи, активное состояние | мобильный | Р |
| Главное действие | один FAB/primary на экран; деструктивные — подтверждение/Undo | FAB «＋», статусы | Verkäufe, Sortiment | Р |
| Формы | одна колонка на мобиле, лейбл над полем, правильный `inputmode`/`type`/`autocomplete` (tel, email, decimal, postal-code), видимые обязательные поля, без placeholder-вместо-label, сохранение черновика | форма товара/акции/настроек на 390px | формы | Р |
| Сообщения об ошибках | у поля, причина + как исправить, на языке пользователя, без кодов; сводка вверху для длинных форм; не терять введённое | серверная валидация, скрытые вкладки | формы | Р (WCAG 3.3.1/3.3.3) |
| Safe areas / клавиатура | контент не под вырезом/home-indicator; sticky-кнопки над экранной клавиатурой | iOS Safari, Telegram WebView | мобильный, Mini App | Р |
| Telegram Mini App | тема `themeParams`, BackButton/MainButton, viewport `expand`, без своих «назад» в шапке | Mini App экраны | Mini App | Р |
| **Core Web Vitals** (p75, «good») | **LCP ≤2,5 с**, **INP ≤200 мс**, **CLS ≤0,1** (FID заменён INP с 12.03.2024) | Lighthouse/CrUX + web-vitals JS на мобильном 4G-throttle: главная кабинета, Verkäufe-доска, Sortiment (200+ товаров), Studio | все | Р (SEO-фактор для витрины) |
| Немецкие конвенции | обращение **Sie** последовательно (или du — но одно); даты `TT.MM.JJJJ`, время 24 ч; `12,50 €` (запятая, пробел, € после); тысячи точкой; `lang="de"` + `hyphens:auto` для длинных слов (расширение текста +30–35 % vs EN — кнопки не обрезать); глаголы на кнопках («Speichern», «Aktion veröffentlichen»), без англицизмов где есть устоявшееся немецкое; гендер-нейтральность — нейтральные формы («Kundschaft», «Team») ⚠️ стилистический выбор | ревью строк de.po, скриншоты 390px с de | все | Р |

## 5. Что дальше в KA (как использовать таблицу)
- Колонку «как проверяем» превратить в стенды: axe-core + Playwright (target-size, focus, reflow, CWV) по всем экранам KA-0-инвентаря × 390/1440 × de/ru.
- Юр-пункты с ⚠️ — отдельным вопросом юристу: KassenSichV для кассы Mini App; BFSG/DSA-статус компании (micro/small); Widerrufsbutton §356a (дата); сроки хранения после BEG IV; Kammer-данные в Impressum по архетипам.
- Закон-пункты, уже частично закрытые в коде (по CLAUDE.md §3): §312j-кнопка, ★ Anzeige, DOI, §11 PAngV, LMIV-поля, DSA Melden, AI_REQUIRE_EU, P0-безопасность — в KA-3+ проверить фактом, а не по памяти.
