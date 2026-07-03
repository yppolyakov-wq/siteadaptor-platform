# L3d — per-locale ввод форм + мультиязычный демо-засев (план, 2026-07-03)

ID — каталог §3 (L3d.1–L3d.5; углубление L3 по конвенции). Остаток Волны L
по `multilanguage-wave-L-plan §10` + `master-track §7.0`. Разведка агентом
2026-07-03 (карта file:line в транскрипте). Миграций НЕ требует — поля
`*_i18n` уже есть (Service/StayUnit/Combo).

## Факты разведки (ключевое)

- Service/StayUnit/Combo правятся СЫРЫМИ POST-вьюхами (не ModelForm):
  `booking/views.py:280-304` (`services_view`; update НЕ правит name!),
  `stays/views.py:228-259` (`units`), `catalog/views.py:577-610` (combo).
  Всё пишет плоские поля (= дефолт-локаль).
- Прецеденты per-locale: catalog/promotions ModelForm — ХАРДКОД пар de/en;
  **N-locale образец — `legal_docs_view` (`core/views.py:528-554`)**:
  цикл по `tenant.active_locales`, имена `doc_<kind>_<locale>`,
  presence-guard. Копировать его.
- Демо: `_i18n_text` (demo_kits.py:44) жёстко de/en; services/stay_units
  сеются плоскими DE-строками, i18n НЕ пишется; **Combo в демо не сеется
  вообще** (двойная дыра). EN-контент только у pranasy.
- Инлайн-диспетчер: product/promotion i18n-поля пишут в `dict["de"]` —
  захардкоженная локаль (`inline_edit.py:148`); service/stay пишут плоско
  (база) — ок.
- Замки: `test_service_i18n`/`test_stayunit_i18n` (семантика overlay — НЕ
  трогать, инвариант «default-локаль не пишется в оверлей»); CRUD-замки
  test_services/test_rooms/test_cabinet/test_combos — перепин осознанно.

## Дизайн

Общий helper `apps/core/i18n_input.py`:
- `extra_locales(tenant)` → active_locales минус default (для шаблонов);
- `apply_i18n_overlay(obj, post, tenant, fields=("name","description"))` —
  для каждого поля: `<f>_<loc>` из POST → `obj.<f>_i18n[loc]` (пустое
  значение удаляет ключ; presence-guard — отсутствующее поле не трогаем;
  **default-локаль в оверлей не пишется никогда**).
Шаблоны: при `extra_locales` рендерим доп. инпуты «Name (EN)…» рядом с
базовыми; 1 локаль → ноль изменений UX. Плоское поле остаётся базой.

## Слайсы

- **L3d.1 (M)** — helper + Service/StayUnit/Combo вьюхи и шаблоны
  (create+update; update Service/StayUnit начинает править и name —
  смена поведения, перепин замков осознанно).
- **L3d.2 (S)** — демо-засев: `_i18n_text` генерализовать по реестру;
  спеки kit.services/kit.stay_units принимают i18n; EN-оверлеи в
  friseur (пара услуг) и hotel (пара номеров).
- **L3d.3 (S)** — Combo: демо-засев (gastro-киты, пара комбо с EN) —
  закрывает дыру master-track §7.0.
- **L3d.4 (S)** — инлайн-гигиена: `"de"` → `settings.LANGUAGE_CODE`-
  резолв в inline_edit.py:148 (замок test_inline_edit перепин).
- **L3d.5 (M, отдельным батчем)** — Category/Product/Promotion ModelForm:
  статические de/en поля → динамика по active_locales (реюз helper).

Замки: тенант с 1 локалью — формы byte-паритет (характеризационный тест
ДО правок); оверлей без дрейфа (существующие test_*_i18n); pranasy
EN-контент не ломается.

## Статус

- **L3d.1–L3d.4 ✅ (2026-07-03)** — детали в build-log. Грабля: Product.name —
  i18n-JSONField, лукап демо-комбо по `name__de__in`; request.tenant в CRUD-
  вьюхах — через getattr (тесты без tenant-миддлвари).
- **L3d.5 ✅ (2026-07-03)** — DynamicI18nFormMixin/form_locales; статические
  en-поля убраны, динамика по active_locales (без tenant — весь реестр,
  паритет); шаблоны без правок ({% for field in form %}). L3d ЗАКРЫТ ЦЕЛИКОМ.
