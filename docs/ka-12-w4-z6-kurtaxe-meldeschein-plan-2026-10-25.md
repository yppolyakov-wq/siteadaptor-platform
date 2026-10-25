# KA-12 · Zimmer Z-6: Kurtaxe-отчёт для общины + Meldeschein (E1.15). План от 2026-10-25

Родитель — `ka-12-w4-zimmer-plan-2026-10-25.md` (§0 E1.15, §4 п. 6, §8 О-5/О-10). Решения
«по рекомендации». Миграция — одна аддитивная `stays/0045`.

## 0. Что есть
- Снимок `StayBooking.kurtaxe_cents` (входит в итог); `pricing.kurtaxe_total_cents(adults, nights)` —
  только взрослые; флаг `StaySettings.kurtaxe_children_free` хранится, но не действует.
- Meldeschein `GuestRegistration` — только онлайн (подписанная ссылка гостя, `unterkunft_checkin`);
  экран `stays:checkins` — read-only список; выгрузки за период нет; ввода со стойки нет.

## 1. Инкременты
- **Z-6a Kurtaxe детей.** `StaySettings.kurtaxe_child_cents` (`0045`, default 0).
  `kurtaxe_total_cents(adults, nights, settings=None, children=0)`: при `kurtaxe_children_free=False`
  + дети × ночи × ставка детей. Все 4 вызывающих передают детей. Форма Kurtaxe: чекбокс «Kinder
  frei» + ставка детей. Старые брони — по своему снимку (не пересчитываем).
- **Z-6b отчёт за месяц** `stays/kurtaxe.py::month_report(start, end)`: брони в учитываемых статусах
  (`counted_statuses_for("stay")`), пересекающие месяц; на бронь — ночи в месяце, ночи взрослых/детей,
  освобождённые ночи детей, сумма = снимок × ночи_в_месяце / ночи (остаток копеек — последнему
  месяцу брони, чтобы Σ по месяцам = снимок). Экран `/dashboard/stays/kurtaxe/?month=` — таблица
  (код брони, категория, даты, ночи) без имён гостей + CSV + PDF; право `finanzen.berichte`; вход —
  подпункт «Kurtaxe» в Finanzen рядом с «Berichte».
- **Z-6c Meldescheine за месяц** CSV (`/dashboard/stays/meldescheine.csv?month=`): персональные
  данные → право `kunden.export` + `audit_export`; **номер документа не выгружаем** (О-10).
- **Z-6d ввод со стойки + печать.** На карточке брони «Meldeschein erfassen» (форма → `stay_action
  action=registration`, право `kunden.edit`, существующую подписанную онлайн-регистрацию не
  перетираем) и «Meldeschein drucken» — PDF на подпись гостя (номер документа только в печати).

## 2. Замки (до кода)
Kurtaxe детей 0/ставка; Σ по месяцам = снимок (бронь через границу месяца); отменённые не в отчёте;
CSV/PDF отчёта без имён; Meldeschein CSV без номера документа, staff без `kunden.export` — 403;
ввод со стойки не перетирает онлайн-подпись; печать — только с правом; i18n ×5.

## ECC-прогоны
Скиллы до кода: `django-security`, `django-tdd`. Агенты: `security-reviewer` (персональные данные,
права выгрузок) на итоговом диффе. Широкую регрессию гоняет CI (решение владельца 2026-10-25).
