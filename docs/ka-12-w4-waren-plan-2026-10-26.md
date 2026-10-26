# KA-12 Волна 4 · Waren-рост (2026-10-26)

Последнее направление Волны 4 (`ka-12-master-plan-2026-10-23.md` §2): E3.1, E3.2, E3.5, E3.7,
E3.8, E3.10–E3.12, E1.5. Источник сценариев — `ka-5a-waren-2026-10-23.md` (W-2, W-3, W-4, W-6,
W-8, B8, B10). Разведка 2026-10-26 (два агента): большая часть базы есть; не хватает проверок,
единиц, списка производства, поштучного возврата и номеров добавок на витрине.

## 1. Инкременты (порядок: малые без миграций → с миграциями)
| ID | Что | Миграция |
|---|---|---|
| **WR-1** (E3.7) | Фид Google: `g:size`/`g:color` у вариантов, фото варианта в `image_link`, состояние по карте (`ausstellung`/`retoure` → `refurbished`, `wie_neu`/`gut` → `used`; баг B10) | — |
| **WR-2** (E3.12) | Номера Zusatzstoffe на витрине из того же источника, что PDF (`food.additive_number_str`): сноска в строке прайса + легенда | — |
| **WR-3** (E3.11) | Шум формы товара по направлению: «Marke & Zustand» и UVP не у гастро; переключатель Chargen на складе — только у гастро/продуктов (CSS-скрытие, W0) | — |
| **WR-4** (E3.8) | Grundpreis: `ProductForm.clean` (единица ⇔ количество), единицы m/m²/m³, Grundpreis акции для товара с вариантами («ab …») | choices (AlterField) |
| **WR-5** (E3.1) | Генератор вариантов «размеры × цвета» (пропуск существующих, общая цена/остаток, леджер) + фото на ЦВЕТ (одна загрузка → все варианты цвета) | — |
| **WR-6** (E3.2) | Массово: видимость/цена (=, ±%, ±€) выбранных товаров через `.save()` (PriceLog §11) + CSV-экспорт товаров + импорт gtin/UVP/Marke/MwSt/EK (presence-guard) | — |
| **WR-7** (E3.10) | Производственный список дня (Backliste/Zerlegeliste): Σ qty по товару+варианту на день выдачи, печать, вход из KDS. Абонементы (Brötchen-Abo) — **решение владельца, отложено** | — |
| **WR-8** (E1.5) | Возвраты: статус `delivered` (shipped→delivered→returned), поштучный возврат (`OrderItem.returned_qty`): склад только для «без повреждений», Gutschrift через `reduce_price`, деньги `refund_partial` | ⚠️ orders |
| **WR-9** (E3.5) | Скидка на категорию / весь магазин (цель акции) во всех путях цены (витрина/корзина/чекаут/фид) + §11 по вариантам со своей ценой | ⚠️ promotions |

## 2. Сквозные правила
- Цена — только через существующий слой (`price_layer`, `create_order`), «показано = списано».
- Склад — через `record_movement`/`_move_stock`, не `.update()`; цены — `.save()` (PriceLog §11).
- Формы — presence-guard (W0); скрытие полей — только CSS.
- Каждая миграция аддитивная; после деплоя пересев не нужен, кроме демо-данных (по инкременту).

## 3. ECC-прогоны
| Инкремент | Скиллы | Агенты |
|---|---|---|
| WR-1 | django-patterns, seo | django-reviewer |
| WR-2/3 | django-patterns, accessibility | django-reviewer |
| WR-4 | database-migrations, django-tdd | django-reviewer |
| WR-5/6 | django-patterns, django-security, error-handling | django-reviewer, security-reviewer (CSV/массовые POST), silent-failure-hunter |
| WR-7 | django-patterns, postgres-patterns | django-reviewer, database-reviewer (агрегат) |
| WR-8 | database-migrations, error-handling | django-reviewer, database-reviewer, security-reviewer (деньги), silent-failure-hunter |
| WR-9 | database-migrations | django-reviewer, database-reviewer, security-reviewer, silent-failure-hunter |

Для всех: `ruff check .` + `ruff format --check .`, `test_template_comments`, `i18n_quickcheck`,
`test_orphan_decorators`/`test_view_perms`/`test_x0_x7_locks` при новых вьюхах; зелёный CI → FF.
