# Исполнение: «задача-первым» — доводка M20U по архетипам

Дата: 2026-07-23. Родитель: `archetype-first-screen-concept-2026-07-23.md`
(принципы утверждены) + `archetype-behavior-specs-2026-07-23.md` (18 вопросов
= все по дефолту). **Честная рамка (согласована с владельцем):** это не новый
подход, а ДОВОДКА M20U «архетип = главный товар + способ покупки» (2026-06-25):
реестры `primary_item`/`primary_section`/`purchase_mode` и archetype-aware
hero-CTA (`_hero_cta.html`) уже есть. Owner-зеркало той же философии —
анти-Битрикс (AB1 язык задач, ST-4a «что сегодня»). Закрываем конкретные гэпы.

**Инварианты (замки каждого инкремента):** существующие сайты не трогаем
(меняем только ДЕФОЛТ-шаблоны/новые применения) · classic_ui цел · golden
normalize цел (новые ключи presence-minimal) · паритет нетронутых раскладок ·
секции гейтятся модулем (неактивный модуль → секция не рендерится).

## Инкременты

### E1 — Дыра отеля: date-search на дефолт-главную ✅ (этот инкремент)
- **Проблема:** демо-отель ведёт `stay_search`+`stay_rooms` (`_kit_sections`),
  но дефолт-шаблон `gastgeber` для НОВЫХ регистраций = `[hero, about, contact]`
  — поиска дат на главной нет. S6-тест покрывает friseur/werkstatt/handwerker/
  events, но hotel в параметрах отсутствовал → дыра проскочила.
- **Фикс:** `gastgeber.sections` → `[hero, stay_search, stay_rooms, about,
  contact]` (как у демо-кита). Секции гейтятся `stays`-модулем.
- **Замок:** параметр `("hotel", "gastgeber", "stay_rooms")` в
  `test_s6_archetype_template_recommended_and_keeps_primary` — навсегда
  закрывает пропуск hotel из проверки «primary на главной».
- **Риск:** минимальный. gastgeber = hotel-only; существующие отели хранят свой
  config (не затрагиваются); demo уже так делает.

### E2 — Аудит «primary-секция на дефолт-главной» для ВСЕХ архетипов ✅
- **Вывод аудита: почти всё уже верно, hotel был выбросом (E1).** Честно, не
  выдумываем правок:
  - `termine` (services 2-й) · `handwerk` (before_after 2-й) · `veranstaltung`
    (events 2-й) — primary сразу после hero. ✓ уже correct.
  - `laden` (bakery/butcher/grocery/retail/clothing/online_shop) = hero →
    **promotions** → products. Для еды promotions-first = Wochenangebote
    ИНТЕНЦИОНАЛЬНО (MB-1 утверждён). Для retail/clothing/online_shop products-
    first был бы чуть лучше, но шаблон общий с едой → оставляем; возможный
    сплит (retail-вариант products-first) — future, не выдумываем сейчас.
  - `gastro` (cafe/restaurant): hero → products (Speisekarte) → promotions.
    Reservation идёт через hero-CTA (`primary_module=booking` → «Termin buchen»).
    Два РАВНЫХ CTA (R-1/R-2) — визуальный hero-узел → E4.
  - **`dienstleister` для tour_operator — РЕАЛЬНЫЙ гэп (исправлен):** дефолтил
    на `dienstleister` (about-first), хотя primary тура = события с датами.
    Убран `tour_operator` из `dienstleister.recommended_for` → дефолт стал
    `veranstaltung` (events-first). Замок: параметр
    `("tour_operator","veranstaltung","events")` в S6-тесте.

### E3 — G2 «Выбор мастера» — ✅ УЖЕ РЕАЛИЗОВАН (моя ошибка в концепции)
- **Честная поправка:** заявленный «функциональный гэп G2» НЕ существует.
  Проверка кода показала — выбор мастера работает end-to-end:
  - `availability.service_slots(service, day, resource=…)` и `assign_resource(…,
    resource=…)` уже принимают конкретного мастера (параметр #4).
  - Вьюха `service_slots` уже читает `?resource=`, фильтрует слоты, несёт мастера
    по календарю/слотам; `service_book` ре-валидирует и назначает выбранного.
  - Шаблон `service_slots.html` (стр. 23-44) уже рендерит пикер: «Anyone» (=Egal)
    ПЕРВЫМ + карточки мастеров с фото/должностью/био.
  - Демо friseur создаёт Resource(staff) Lea/Jonas/Mia → пикер виден на
    `/termin/` и реально фильтрует/назначает.
- Отличие от концепции: пикер — инлайн-чипы над слотами (одна страница), а не
  отдельный «шаг Мастер». Инлайн — не хуже, а лучше (без лишней навигации). НЕ
  переделываем. Возможная микро-доводка (по спросу): фильтровать пикер только
  на `type=staff` (сейчас показывает любой ресурс при >1; для friseur = staff,
  для ресторана столы — но рестораны обычно не дают гостю выбирать стол).

### E4 — G1 «Интерактивный hero» ✅ (запрос владельца: «ведём клиента с первого экрана»)
- **Механизм (без миграции, presence-minimal):** `site_defaults.hero_widget`
  ("" | "stays" | "services") — primary-виджет ВНУТРИ баннера. Партиал
  `_hero_widget.html` (белая карточка поверх фото/акцент/plain-hero), гейт по
  модулю (stays → date-search на /unterkunft/; services → топ-3 услуги с
  «Termin buchen»). `apply_template` доносит `template["site_defaults"]`;
  golden целы (ключ только при валидном значении).
- **Отель (флагман):** `gastgeber` → hero несёт date-search (site_defaults
  hero_widget=stays), секция stay_search убрана (жила бы дублем), карточки
  номеров — сразу под баннером. Демо-кит HOTEL так же (`hero_widget="stays"`,
  `_kit_sections` гасит дубль). **Существующие отели не затрагиваются** (нет
  ключа hero_widget → баннер как прежде).
- **Замки:** render-тест партиала (поиск дат + гейт модуля), gastgeber
  hero_widget=stays через apply_template, демо-отель (секция off + флаг),
  golden/template_comments целы. 1 msgid («Min») → 4 .po.
- **Дальше (services-вариант для friseur):** механизм готов (hero_widget=
  "services" рендерит топ-услуги); включить у `termine`/демо friseur —
  отдельный микро-инкремент E4b по желанию владельца.

## Порядок / итог
E1 ✅ → E2 ✅ → E3 (уже был готов, поправка) → [E4 опц.]. Каждый: локальный
гейт (ruff+pytest+template_comments) → push → CI → FF-merge.

**ЧЕСТНЫЙ ИТОГ доводки.** «Задача-первым» на 90% уже была реализована (M20U +
A3 профили мастеров + kit-секции). Реальных гэпов оказалось ровно ДВА, оба
закрыты: **E1** (date-search не на главной у новых отелей) и **E2** (tour_operator
дефолтил на about-first). G2 (выбор мастера) — уже работал (ошибка концепции,
исправлена выше). Остаётся один по-настоящему открытый пункт — **E4/G1
«интерактивный hero»** (слить primary-виджет В баннер, а не секцией под ним):
это ВИЗУАЛЬНАЯ доводка, не функция. Делать по решению владельца — не выдумываем
работу, если текущего (виджет секцией сразу под hero) достаточно.
