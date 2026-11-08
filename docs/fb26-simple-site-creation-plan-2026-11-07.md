# FB-26 — упрощение создания сайта: «Was verkaufen Sie?» + ниша или «Überspringen»

Фидбэк владельца 2026-11-07: «упростить создание сайта — один тип „продаю всё“ и пресеты по
нишам, или пропустить». Разбор батча — `fb-feedback-batch-2026-11-07.md`. **Статус: FB-26a сделан (2026-11-08).**

## 1. Что есть сегодня (разведка)

- Регистрация `/registrieren/` и шаг мастера `business` (`apps/tenants/onboarding.py:253`,
  `templates/tenant/setup/_step_business.html`) — **16 карточек типа бизнеса**
  (`Tenant.BUSINESS_TYPES`). Тип питает: пресеты модулей (`recommended_for`), JSON-LD, шаблоны
  витрины/Look'и/сборки, hero-плитки, образцы «Angebot prüfen», демо-кнопку.
- «Как продаёт бизнес» уже отделено от типа — `apps/core/directions.py` (M-0/M-1: Waren ·
  Termine · Zimmer · Tickets · Anfragen · Gastro) и экран «Richtungen & Funktionen».
- Мастер v4 (`SETUP_WIZARD_V4`, AIS): Was haben Sie schon? → Firma → Angebot → Recht → Fertig.

Вывод: «тип» сегодня делает две работы — **что продаёт** (направления → модули) и **какая
ниша** (тексты, образцы, вид, JSON-LD). Первую уже несут направления; вторая — данные.

## 2. Решение (на согласование)

1. **Первый вопрос — «Was verkaufen Sie?»** чипами-направлениями с мультивыбором
   (Produkte · Termine/Dienstleistungen · Zimmer · Tickets & Touren · Anfragen/Aufträge ·
   Speisen & Getränke). Это и есть «продаю всё»: можно отметить всё сразу.
2. **Второй, необязательный — ниша** («Bäckerei», «Friseur», «Hotel», …): поиск по списку
   16 типов + «Andere». Ниша = **данные**: образцы, тексты, вид, JSON-LD — модулей она не
   включает (их включили направления).
3. **«Überspringen»** на обоих: без направлений — включено всё базовое (товары + заявки +
   сообщения), ниша `other`; всё меняется позже на «Richtungen & Funktionen».
4. Внутренний `business_type` **не сносим**: ниша пишется в него, «Andere» → `other`;
   направления пишутся единственным писателем `directions.set_state`. Пресеты модулей по
   `recommended_for` применяются только как подсказка, если направления не выбраны.

## 3. Инкременты

| ID | Что | Миграции |
|---|---|---|
| FB-26a | шаг «Was verkaufen Sie?» (направления, мультивыбор) в регистрации и мастере v4 + «Überspringen» | нет |
| FB-26b | ниша — поиск по 16 типам + «Andere», необязательно; образцы/вид по нише | нет |
| FB-26c | замер `onboarding_report` до/после (AIS-0) + стенд регистрации 390/1440 | нет |

## 4. Вопросы владельцу
1. Направления — первым вопросом, ниша — вторым и необязательным: так?
2. «Überspringen» без направлений: включать «Produkte + Anfragen + Nachrichten» — достаточно?
3. Демо-кнопка «Beispiel ansehen» остаётся у ниши (как сейчас у типа) — да?

## 5. ECC-прогоны
- Скиллы: `django-patterns`, `accessibility` (чипы мультивыбора, фокус), `e2e-testing`.
- `django-reviewer` — каждый инкремент; `a11y-architect` — макет шага; Playwright — 26c.

## 6. Решения владельца (2026-11-08) и сделанное

1. Порядок — по рекомендации: направления первыми, ниша вторым вопросом и по желанию.
2. **Направления выбрать обязательно** — «иначе непонятно, отель это или…». Кнопки
   «Überspringen» у направлений нет; у ниши — пропуск (пустая ниша).
3. «Demo ansehen» у ниши — да.

**FB-26a ✅** (⚠️ миграция `tenants/0042`, аддитивная): `apps/tenants/signup_directions.py` —
шесть чипов регистрации поверх реестра направлений («Speisen & Getränke» = Speisekarte +
Tisch, по типу), вывод пустой ниши только однозначно (гастро → restaurant, только номера →
hotel, только билеты → events, иначе other), стартовые модули по направлениям (неотмеченные
Termine/Tisch/Zimmer/Tickets/Anfragen выключены; Waren онлайн-продажу не включает — её
открывает «Verkauf öffnen»). Ответ хранится в `SignupRequest.directions`, при создании
бизнеса — в `onboarding["directions"]` (мастер v4 «Wie verkaufen Sie?» уже отмечен).
Страница: чипы до ниши, карточки ниш фильтруются по чипам («Alle Branchen zeigen»; без JS
видны все), `?type=` с Branchen-страницы предотмечает чипы. Замки
`test_fb26_signup_directions.py` (9), стенд Playwright 390 px.
FB-26b/c (поиск по нишам, замер `onboarding_report`) — по спросу.
