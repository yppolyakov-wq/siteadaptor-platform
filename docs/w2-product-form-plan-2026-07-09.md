# W2 — упрощение формы товара (план, 2026-07-09)

Из аудита `docs/admin-global-audit-2026-07-09.md §3`. Жалоба владельца: «настройка товара
очень громоздка и непонятна, оптимизировать/сделать проще, визуально».

Файлы: `apps/catalog/forms.py:102-206` (ProductForm), `templates/catalog/product_form.html`
(плоский `{% for field %}` рендер), модель `apps/catalog/models.py:48-117`.

## Проблемы (подтверждены вживую на стенде friseur)
1. Порядок сломан: `name_de` рендерится **17-м из 23** (после цены/валюты/склада/EK/reorder/
   происхождения/ингредиентов). Первое, что видит новичок — «Einkaufspreis netto».
2. `help_text` не выводится вообще (в шаблоне нет вывода help_text).
3. Нет группировки: 33 чекбокса маркировки (allergens 14 + additives 13 + diets 6) + T5-склад
   + unit/content + sku/gtin навалены в одну колонку.
4. Обязательны только 2: `name_de` + `base_price`. Всё прочее — optional.
5. `currency` — свободный TextInput (опечатки).

## Предлагаемая структура (секции + аккордеон + режим)
Рендер по ЯВНЫМ секциям (не плоский цикл). Порядок и группировка:

**① Basis (всегда открыто) — 90% товаров тут:**
- name, description, category, base_price, фото (drag-drop с превью), is_active.

**② ▸ Preis & Einheit (аккордеон, свёрнут):**
- unit + content_amount (в один ряд, live-подсказка «Grundpreis: X €/kg»), currency (бейдж EUR
  + «ändern», не свободный ввод).

**③ ▸ Lager & Einkauf (аккордеон, свёрнут) — T5:**
- stock_quantity, cost_price, reorder_point, reorder_target, sku. Live-плашка маржи
  (`Product.margin_pct`, готовая формула).

**④ ▸ Lebensmittel-Kennzeichnung (аккордеон, свёрнут; по спросу для гастро):**
- allergens/additives/diets — ЧИПАМИ вместо 33 вертикальных чекбоксов; origin, ingredients, gtin.

**⑤ ▸ Marketing (аккордеон, свёрнут):**
- is_featured (toggle), badge.

**Режим Простой/Эксперт (переиспользуем S5 `ui_mode`):** в Простом — показываем только ①
(+фото), аккордеоны ②–⑤ скрыты (доступны в Эксперте). Хранение выбора — уже есть S5-механика;
на форме — тумблер локально (localStorage) ИЛИ по tenant `ui_mode`.

## Реализация (инкременты, низкий риск — форма/шаблон, без миграций)
- **W2-1:** порядок + секции. `ProductForm.field_order` ИЛИ переписать шаблон на явные секции
  (как `settings.html` после W0). name/description первыми. Вывести `help_text`.
- **W2-2:** аккордеоны `<details>` для ②–⑤ (паттерн из кабинета). Toggle-свитчи для boolean,
  currency-бейдж, live Grundpreis/маржа (JS, формулы в модели готовы).
- **W2-3:** чипы для allergens/additives/diets (компактно, сворачиваемо).
- **W2-4:** режим Простой/Эксперт на форме (в Простом видно только Basis).
- Аналогично облегчить variant/combo (спрятать T5-тройку под «Erweitert»); category — slug/sort/
  icon в «Erweitert», icon-пикер.

## Замки
- Характеризационный тест ДО правок: сабмит формы с полным набором → все поля сохраняются
  (как W0 round-trip). Порядок: тест «name_de рендерится в первой секции, не 17-м».
- Гейт: `apps/catalog` + рендер product_form на стенде; ruff; при новых Tailwind-классах —
  `npm run build:css` + коммит app.css (урок W1: freshness ловит и removed-классы).

## Развилки для владельца (перед кодом)
1. Группировка ①–⑤ выше — ок? (что должно быть в Basis vs аккордеонах.)
2. В Простом режиме на форме товара — прятать ВСЕ аккордеоны (только Basis) или оставить
   ② Preis тоже? (цена/единица — базовое для многих.)
3. Пищевая маркировка (④) — прятать по архетипу (только еда: bakery/butcher/grocery/restaurant/
   cafe), у friseur/retail/hotel скрывать секцию целиком?
