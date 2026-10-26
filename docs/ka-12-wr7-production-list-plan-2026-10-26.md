# KA-12 WR-7 (E3.10) · Produktionsliste des Tages (2026-10-26)

Сценарий W-6 (`ka-5a-waren-2026-10-23.md`): пекарня/мясная/кафе в 5 утра должны знать,
**сколько чего** произвести под предзаказы дня, а не листать заказы по одному.

## Что
- `apps/orders/production.py::production_list(day)` — Σ qty по (товар, вариант, набор) для
  заказов с `pickup_slot` в этот день (локальная дата), статусы `new`/`confirmed` = «zu
  produzieren», `ready` = «fertig» отдельной колонкой; отменённые/выданные/возвращённые — нет.
  Один агрегатный запрос (`values().annotate(Sum, Count(distinct order))`), имена — одним
  `in_bulk` по товарам/наборам.
- «Ohne Abholzeit»: сколько открытых заказов без времени выдачи (честная подсказка — они в
  список дня не попали).
- Экран `/dashboard/orders/produktion/?tag=YYYY-MM-DD` (← день →, печать), вход: сайдбар
  «Verkäufe» у продуктовых типов (`FOOD_TYPES`) + кнопка на KDS.
- Права: `verkaeufe.view` (только чтение).

## Не делаем (v1)
Раскладка наборов на компоненты (состав — снимок в `modifiers`, разный у free_pool) и
модификаторы («ohne Zwiebeln») — строкой «Hinweise» в v2 по спросу; Brötchen-Abo —
решение владельца (отложено).

## ECC-прогоны
Скиллы: django-patterns, postgres-patterns. Агенты: django-reviewer + database-reviewer
(агрегат/индексы) после кода. Гейты: ruff, `test_x0_x7_locks`, `test_view_perms`,
`test_orphan_decorators`, `test_sidebar_st4b`, `test_template_comments`, `i18n_quickcheck`.
