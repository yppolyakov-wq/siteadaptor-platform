# KA-12 Волна 1.1 — лёгкий кабинет: правовые данные, заявки, Mini App без тупиков (2026-10-23)

План — агент planner (полный отчёт в истории сессии). Источник — `ka-12-master-plan` E7.1, E7.2,
E8.9, E8.10, E7.10; решения владельца: правовые тексты — юристу одним пакетом, в лёгком
кабинете — настройки правовой информации.

## Находки разведки
- Есть на `Tenant`: city, district, logo_url, contact_email, vat_id, tax_number, small_business,
  register_entry (свободный текст), legal_responsible, impressum (свободный текст).
- `legal_responsible` печатается как «Verantwortlich i.S.d. § 18 Abs. 2 MStV» — это НЕ
  представитель по § 5 DDG; нужен отдельный `legal_representative`.
- `public_email` = `contact_email or owner_email` → в Impressum сегодня уходит почта входа.
- «Geschäft» уже owner-only; `legal-docs` открыт пакетом, но ссылки на него в лёгком кабинете нет.
- Списка заявок в лёгком кабинете нет (`jobs:list` — 302 на закрытый `verkaeufe`).
- «Teilen» дублируется: пункт меню и ссылка со страницы «Sichtbar».
- Ни один демо-кит не заполняет правовые поля; общего гейта готовности (T-8.32c) ещё нет.

## Решение
1. Миграция `tenants/0038` (аддитивная): `legal_form` (choices), `legal_representative`,
   `register_court`, `register_number`, `chamber`, `profession`. `register_entry` — легаси-фолбэк.
2. `impressum_text()` печатает форму лица, «Vertreten durch», суд+номер; `impressum_missing()` —
   список недостающего (адрес, e-mail для Impressum, представитель/реестр по форме, налоговые данные);
   свой текст Impressum / LegalDoc → пусто.
3. Лёгкий «Geschäft»: Kontakt · Standort · Logo · Rechtliches + превью Impressum + ссылка на Recht
   (в Mini App — «im Browser öffnen»); `contact_email` обязателен (префилл из почты входа).
4. Гейт E7.2 — **предупреждение, не блок** (быстрый старт T-8.5 адреса не собирает): первый шаг
   «Impressum vervollständigen» на главной, плашка на «Fertig» и «Sichtbar»; жёсткий блок — в T-8.32c.
   Демо/внутренние — без предупреждения; демо-киты получают вымышленные правовые данные.
5. Меню: «Anfragen» (`lite-requests`, при модуле jobs) вместо дубля «Teilen».
6. Mini App: фильтр `lite_allowed` (пакет + `TG_LITE_VIEWS`) на всех ссылках лёгких экранов;
   язык и выход в подвале лёгкого меню.
7. Демо-телефоны — в резервированные BNetzA диапазоны (сверить с актуальным списком ДО кода).

## Замки до кода
Поля формы и W0-запись; 403 сотруднику; `impressum_text` по формам лица (почта входа не
появляется); матрица `impressum_missing`; меню (нет `lite-share`, `lite-requests` только с jobs);
**Mini App: каждая ссылка лёгкого экрана в TG-сессии резолвится в `TG_LITE_VIEWS`**; телефоны
демо — только резервированные.

## Коммиты
1. E7.1/E7.2 (миграция, модель, форма, предупреждения, демо-данные, .po).
2. E8.9/E8.10 (заявки, меню, фильтр, подвал Mini App, замок тупиков).
3. E7.10 (телефоны демо + валидатор + замок).
