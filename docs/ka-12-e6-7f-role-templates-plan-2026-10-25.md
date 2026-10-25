# KA-12 E6.7f — шаблоны ролей + новые дефолты сотрудника (2026-10-25, без миграций)

Основа — `ka-12-e6-7-staff-permissions-plan-2026-10-25.md` §A.5 (шаблоны по архетипу) и
решения В-2/В-3 («по рекомендации» владельца).

## 1. Дефолты пресета staff (В-2/В-3) — осознанное изменение паритета
- Убрать у staff по умолчанию: `finanzen.kennzahlen`, `finanzen.berichte`, `finanzen.journal`,
  `finanzen.edit` (В-2), `ablaeufe.edit`, `domains.edit`, `funktionen.edit` (В-3).
- Admin не меняется. Владелец возвращает точечно чекбоксом или шаблоном.
- Хранение — дельта к пресету: у существующих staff ключи пропадут (их `add` их не содержит);
  замок `test_perm_parity` переписывается с таблицей «было/стало» в коммите.
- Влияние на пилоты: в журнал работ + заметка владельцу (сотрудников сегодня мало).

## 2. Шаблоны ролей — `apps/core/role_templates.py`
- Реестр `TEMPLATES = {key: RoleTemplate(label, hint, role, keys, business_types)}`; ключи —
  явные множества (без наследования), `keys ⊆ ROLE_LIMIT[role]` (замок).
- Все типы: **Leitung** (admin, пресет admin) · **Mitarbeiter** (staff, пресет staff) ·
  **Buchhaltung** (admin: finanzen.* + geld.erstatten + verkaeufe.view + kunden.view) ·
  **Aushilfe/Kasse** (staff: verkaeufe view/edit, geld.einloesen, geld.bezahlt, kunden.view).
- Отель: **Rezeption** (staff: verkaeufe view/edit, rezeption.edit, geld.bezahlt, kunden view/edit,
  finanzen.kennzahlen) · **Housekeeping** (staff: verkaeufe.view).
- Гастро (cafe/restaurant/catering/bakery/butcher): **Küche** (staff: verkaeufe view/edit).
- `templates_for(tenant, role)` — шаблоны роли цели и типа бизнеса.
- `perm_grants.TEMPLATE_KEYS` ← реестр (имя шаблона хранится только для подписи).

## 3. UI и сервер
- На форме прав участника — карточки шаблонов его роли: кнопка `name="apply_template"
  value=<key>` в той же форме (без JS). Сервер: `requested = keys шаблона`, `template = key`,
  тот же `set_member_permissions` (области/requires/stale — как обычно).
- Шаблон, который актор применить не может (выдаёт или снимает вне своей области), — disabled с
  причиной. Расчёт — та же функция, что у писателя: `perm_grants.preview(...)` (вынести общий
  расчёт `new` из `set_member_permissions`, без блокировки).
- Подпись сводки: «Vorlage: Rezeption» / «Vorlage: Rezeption · angepasst» (эффективные ≠ шаблон).
- Инвайт: селект «Vorlage» (опционально) — права шаблона вместо пресета роли.

## 4. Замки (до кода)
- Каждый шаблон: ключи в реестре, ⊆ лимита роли, замкнуты по requires.
- Применение шаблона даёт ровно его ключи и сохраняет имя; «angepasst» после ручной правки.
- Admin не может применить шаблон с 🔒 или снимающий его недоступное — кнопка disabled, сервер
  отказывает (подделка POST).
- Новый пресет staff: без finanzen.*/ablaeufe.edit/domains.edit/funktionen.edit; меню staff не
  показывает Finanzen (E6.7e подхватит).
- i18n: подписи шаблонов ×5 локалей.

## ECC-прогоны
- Скиллы до кода: django-patterns, django-tdd, django-security.
- `django-reviewer` + `security-reviewer` (применение шаблона = выдача прав) после кода;
  Playwright-стенд экрана команды (кнопки шаблонов, подпись «angepasst»).

## Грабли
Правка формы через скрипт после `ruff format` (повтор E6.7e — замена не применилась): проверять
`assert old in s`; новые msgid → `.po` ×5 + `i18n_quickcheck`; не гонять два pytest на одной БД.
