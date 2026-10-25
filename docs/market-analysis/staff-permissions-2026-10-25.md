# Права сотрудников в SaaS для малого бизнеса — короткое исследование (2026-10-25)

Задача: понять, как близкие продукты делают настраиваемые права сотрудников, и что из этого
брать в наш кабинет (сегодня у нас роли owner / admin / staff, admin и staff по сути
одинаковы; гейты — `apps/core/roles.py`: `OWNER_ONLY_PREFIXES`, `ROLE_FINANCE`).

**Метод и оговорка.** Источники — официальные справки (Shopify, Square, Lightspeed, Mews,
Bitrix24, Timely, Timify) и форумы поставщиков; маркетинг поставщиков — заявление, не факт.
**Не удалось найти публичную документацию** по ролям TravelLine, Apaleo (только OAuth-скоупы),
Shore, Planity, Treatwell (только «доступ к календарю настраивается по сотруднику») и деталям
ролей SumUp POS (только «роль выбирается при создании пользователя»). По ним выводов не делаю;
вместо салонов-DACH взят Timely как задокументированный аналог.

## 1. Сводная таблица

| Продукт | Модель | Кто выдаёт / эскалация | Финансы, отчёты, ПДн | Деньги на кассе | Журнал |
|---|---|---|---|---|---|
| **Shopify** | Роли из поштучных прав, по уровням: магазин / организация / POS; отдельная группа «Sensitive permissions» | Управление пользователями и ролями — **не обычное право**, у владельца/админ-ролей; системные роли с чувствительными правами нельзя менять | Отдельно: выплаты, налоговые документы, споры, платёжные настройки (2026); экспорт клиентов — отдельное право, но запрещать экспорт исторически мог только Plus | POS: каждое право (скидка, возврат, обмен, налог, касса, своя позиция) может быть «Approval required» — подтверждение **PIN менеджера** | Публично не описан |
| **Square** | 3 готовых набора Standard / Enhanced / Full + «Customize» поштучно; свои наборы — платный план | Наборы правит владелец или сотрудник с правом «team management»; Full даёт всё, **кроме банковских счетов** | Отчёты ступенями: «ограниченные» (агрегаты за 90 дней) ↔ «детальные» (любой период); отдельно Close of Day, споры | Отдельные права «Issue refunds», скидки по локации, скидки под 4-значный код | Activity Log: возвраты, скидки, void, правки склада; гранулярность ругают |
| **Lightspeed Retail** | Встроенные роли (Associate / Manager / Admin / Owner) + до 21 своей роли; правка роли меняет всех её носителей | Роли — в настройках бэк-офиса | — | «Sales – Refund» отдельно; режим кассы «только простые продажи» запрещает возвраты/скидки/кассовый ящик; в X-Series — лимит скидки «кто и на сколько» | — |
| **Mews (PMS)** | Роли по отделам отеля, у пользователя может быть несколько; права по доменам (брони, операции, биллинг, аналитика) × действия view/create/edit/delete/**export**; зависимости прав | **Не-админ выдаёт только права ≤ своих и не правит свои**; Admin — «как можно меньше людей»; без роли — ничего нельзя | Billing/аналитика — отдельные домены; export — отдельное действие | Через домен биллинга | В найденных статьях не описан |
| **Bitrix24** | Роли + **область данных**: свои / отдела / отдела и подотделов / все / нет доступа; правила на стадии сделки | Только админ или право «настройки CRM»; несколько ролей → **берётся максимум** (частый источник конфликтов) | Через область «свои/отдел» | — | — |
| **Timely (салоны)** | Admin / Manager / Employee (+ Team lead); доступ к клиентам 3 ступенями: только имя → контакты и заметки → полная база с подправами | Экран «Staff access» по умолчанию у владельца аккаунта, можно передать | **Можно скрыть телефон/e-mail клиента**, оставив записи, фото, бонусы | — | Видно последнюю активность и способ входа (e-mail/PIN) |
| **Timify** | Права задаются каждому сотруднику при приглашении | Чужие календари видят/правят только админы | — | — | — |

## 2. Выводы по вопросам

1. **Шаблоны vs поштучно.** Общепринято: *готовые роли/наборы + «настроить»* (Square, Lightspeed,
   Shopify, Mews). Чистые поштучные галочки без шаблонов почти не встречаются; несколько ролей на
   человека — у PMS (Mews) и Bitrix24, у POS — одна.
2. **Группировка.** По областям работы (продажи/касса, каталог, клиенты, отчёты, финансы,
   настройки, команда) и внутри — по действию (смотреть / менять / удалять / **экспорт**).
   Уровень действия «export» как отдельное право — у Mews и Shopify.
3. **Эскалация.** Явно задокументировано «выдаёшь только ≤ своих, свои не правишь» у Mews.
   У Shopify/Square управление командой — отдельная привилегированная способность; у Square даже
   Full не включает банковские реквизиты, у Shopify — «Sensitive» и owner-only. Bitrix24 —
   анти-пример: «максимум из ролей» без явного контроля.
4. **Финансы и ПДн.** Финансы (выплаты, банк, налоговые документы) почти везде — отдельная и
   «чувствительная» группа. Отчёты делят по глубине (Square: агрегаты за 90 дней ↔ детально).
   ПДн: самый зрелый пример — Timely (скрыть контакты клиента, оставив работу с записью);
   экспорт клиентской базы — отдельное право (Shopify). Это прямо ложится на принцип
   минимизации DSGVO (Art. 5(1)(c), Art. 25, Art. 32).
5. **Деньги.** Общепринято: возврат, скидка, отмена/void, своя цена/позиция, кассовый ящик —
   **отдельные права**. Редкость, но очень ценно: «разрешено с подтверждением» (PIN менеджера,
   Shopify POS) и **лимит** скидки (Lightspeed X-Series).
6. **Журнал.** Журнал *действий с деньгами* есть (Square Activity Log); журнал *изменений прав*
   в найденных справках не описан ни у кого — значит, у малого SaaS это **редкость** и наше
   преимущество.
7. **UX.** Пресеты сверху + группы с чекбоксами/переключателями, иногда ступени вместо галочек
   (Square Standard/Enhanced/Full, Timely 3 ступени доступа к клиентам). Наборы платные у Square
   — то есть рынок считает это функцией роста, а не базовой.

## 3. Рекомендации для нас (8–10)

1. **Шаблоны ролей по архетипу + «настроить» поштучно** (общепринято). Шаблоны: Inhaber,
   Leitung (Manager), Mitarbeiter, Buchhaltung, Aushilfe/Kasse; для отеля — Rezeption,
   Housekeeping; для салона — «Mitarbeiter: nur eigene Termine». Хранить как набор прав-кодов,
   шаблон = пресет, а не отдельная сущность с наследованием (проще аудит).
2. **Права = область × действие** (view / edit / delete / export) по разделам нашего реестра
   навигации (Verkäufe, Sortiment, Marketing & Kunden, Finanzen, Einstellungen, Team). Экран
   права ↔ `nav_registry` — одна точка истины, как гейты сайдбара (общепринято по смыслу,
   у нас дёшево благодаря реестру).
3. **Строгий запрет эскалации** (как Mews; у малых SaaS явно — редкость): выдать можно только
   права ≤ своих; свои права не правишь; «Team & Zugriff», банковские реквизиты/IBAN, удаление
   бизнеса, смена владельца — owner-only всегда (продолжение `OWNER_ONLY_PREFIXES`). Проверку
   делать на сервере при сохранении, а не только скрывать галочки.
4. **Отдельная группа «Geld» с явными правами** (общепринято): возврат денег, отмена с
   возвратом, скидка вручную, изменение цены в сделке/на кассе, «als bezahlt markieren»,
   погашение ваучера/купона, Kassenbuch. Это уже совпадает с решением владельца «возврат
   отменой — только владелец или бухгалтер» — расширить до права, назначаемого ролям.
5. **Лимиты и «с подтверждением»** (редкость, сильное отличие): «скидка до N %», «возврат до
   X €», выше — нужен второй человек (PIN/подтверждение владельца в Mini App). Делать во второй
   итерации; первая — простые да/нет.
6. **ПДн по ступеням (DSGVO-минимизация):** «Kunden: nur Name» / «Kontaktdaten» / «volle
   Kartei»; **экспорт клиентов и выгрузка DSGVO — отдельное право**, по умолчанию только
   владельцу. Сотрудник без ступени «Kontaktdaten» видит на сделке имя и код, но не телефон/
   e-mail (по образцу Timely — редкость среди POS, норма среди салонных систем).
7. **Финансы и отчёты ступенями**: «Umsatz heute/агрегаты» ↔ «Berichte детально» ↔
   «Finanzen/Rechnungen/DATEV/Bank». Ступень по умолчанию для Mitarbeiter — ничего, для
   Leitung — агрегаты (как Square limited reporting).
8. **Область данных «nur eigene»** для сотрудников салона/мастерской/гидов: свои записи,
   свои заявки, свой календарь (Bitrix24 / Timify); правило конфликта ролей — **минимум, а не
   максимум** не нужен, если у человека одна роль: держим **одну роль на человека** (как POS),
   это убирает класс конфликтов Bitrix24.
9. **Журнал изменений прав и денежных действий** (журнал прав — редкость): кто, кому, что
   было → что стало, когда; плюс письмо владельцу при выдаче «Geld»/«Finanzen»/«Team»
   (как мы уже делаем при смене IBAN). Писать в существующий `apps/core/audit.py`; хранение
   ограничить сроком (DSGVO) и без копий ПДн в записи.
10. **UX-экран:** сверху карточки-пресеты ролей с одной строкой «что может», ниже группы
    с переключателями и ступенями (не 60 плоских галочек), значок 🔒 у чувствительных прав,
    предпросмотр «так видит кабинет этот сотрудник». Права не продавать отдельно в лёгком
    пакете — достаточно двух шаблонов (Inhaber / Mitarbeiter), полный редактор — в пакете
    «Laden»/Profi (Square тоже держит свои наборы за платным планом).

## 4. Риски и оговорки
- Данные по Shopify-экспорту клиентов частично из форума и changelog 2019 г. — могли устареть.
- Отсутствие журнала прав в найденных справках ≠ отсутствие функции; это вывод по публичной
  документации.
- Слишком гибкая матрица прав — риск «Bitrix-каши» для малого бизнеса; поэтому пресеты первыми,
  ступени вместо галочек, одна роль на человека.

## 5. Источники
- Shopify: [Setting staff permissions](https://help.shopify.com/manual/your-account/staff-accounts/staff-permissions) ·
  [Descriptions of permissions](https://help.shopify.com/manual/your-account/staff-accounts/staff-permissions/staff-permissions-description?locale=en) ·
  [Sensitive permissions](https://help.shopify.com/en/manual/your-account/staff-accounts/staff-permissions/staff-permissions-sensitive) ·
  [POS roles, Approval required](https://help.shopify.com/en/manual/sell-in-person/shopify-pos/staff-management/pos-roles) ·
  [Changelog: payments/payouts/tax permissions](https://changelog.shopify.com/posts/new-and-updated-staff-permissions-for-payments-payouts-disputes-and-tax-documents) ·
  [Changelog: restrict data export (Plus)](https://changelog.shopify.com/posts/restrict-your-staff-members-from-downloading-shop-data) ·
  [Community: export customers](https://community.shopify.com/t/preventing-staff-from-exporting-customer-data/58192) ·
  [StaffMemberPermission (API)](https://shopify.dev/docs/api/admin-graphql/latest/enums/StaffMemberPermission.md)
- Square: [Customize team member permissions](https://squareup.com/help/us/en/article/5822) ·
  [Team management](https://squareup.com/ie/en/point-of-sale/features/team-management) ·
  [Community: audit trail / Activity Log](https://community.squareup.com/t5/Square-for-Retail/audit-trail-for-any-changes-made-by-internal-users/m-p/662004) ·
  [Feature request: precise activity logs](https://community.squareup.com/t5/Feature-Requests/Better-more-precise-activity-logs/idi-p/702798)
- Lightspeed: [Employee roles](https://retail-support.lightspeedhq.com/hc/articles/229129608) ·
  [Keeping Retail secure](https://retail-support.lightspeedhq.com/hc/en-us/articles/229128788-Keeping-Lightspeed-Retail-secure) ·
  [X-Series updates (discount permissions)](https://x-series-support.lightspeedhq.com/hc/en-us/articles/25533675307675-October-product-updates)
- SumUp: [Create user and role](https://help.sumup.com/en-GB/pos/articles/75000029074-users-how-to-create-a-new-user-and-give-it-the-permission-to-access-the-back-office-)
- Mews: [Role-based permissions FAQ](https://help.mews.com/s/article/Role-based-permissions-FAQ) ·
  [Set up and customize user roles](https://help.mews.com/s/article/Set-up-and-customize-user-roles) ·
  [Add or remove a user](https://help.mews.com/s/article/create-or-delete-an-employee-profile)
- Apaleo: [OAuth scopes (apis.io)](https://apis.io/scopes/apaleo/apaleo-scopes/) — ролей в публичной справке не найдено.
- Bitrix24: [CRM access permissions](https://helpdesk.bitrix24.com/open/10770366/) · [roles and conflicts](https://helpdesk.bitrix24.com/open/25841971/)
- Timely: [Staff permissions / client access](https://help.gettimely.com/hc/en-gb/articles/1500002146341) ·
  [Give staff account access](https://help.gettimely.com/hc/en-gb/articles/1500002195142-How-to-give-staff-account-access)
- Timify: [See calendars of team members](https://timify.com/it/support/3046629-how-can-i-see-the-calendar-of-my-team-members)
- Treatwell: [Partner page (ES)](https://www.treatwell.es/partners) — детали прав не опубликованы.
