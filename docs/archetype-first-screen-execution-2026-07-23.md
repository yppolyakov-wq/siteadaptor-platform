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

### E3 — G2 «Выбор мастера» при записи (функциональный)
- Слот-пикер booking фильтрует слоты по выбранному staff; шаг «Мастер» с
  опцией «Egal — nächster Termin» первой; 0–1 мастер → шаг пропущен. Профили
  staff (A3) уже есть; нужен фильтр слотов + UI шага.

### E4 — G1 «Интерактивный hero» (по спросу после E1–E3)
- Вариант секции hero со встроенным primary-виджетом (date-search / услуги /
  афиша). Больший визуальный сдвиг; делаем, если после E1–E3 видна ценность.

## Порядок
E1 (сейчас) → E2 → E3 → [E4 опц.]. Каждый: локальный гейт (ruff+pytest
затронутого+template_comments при шаблонах) → push → CI → FF-merge.
