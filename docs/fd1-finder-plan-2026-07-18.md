# FD-1: движок Finder «вопросы → 3 предложения» (план)

> По `live-selling-finder-concept-2026-07-18.md §3` + решения владельца §6
> (FD первым; Finder — ОПЦИЯ, не дефолт). Ветка сессии
> `claude/registration-email-confirmation-698nwb`, FF-мерж в main по зелёному CI.

## Объём FD-1 (этот инкремент)
1. **Конфиг**: `site_config["finder"]` → `normalize_finder` (presence-minimal,
   как `board` W5 — ключ только при непустом; golden-замки целы):
   `{"enabled": bool, "questions": [{key,label,chips:[{key,label,match}]}]}`.
   `match`: `words` (список слов), `collection` (slug, service/stay),
   `category` (slug, product), `price_min`/`price_max` (EUR). Пустые
   `questions` → пресет архетипа из реестра (кастом-дерево — FD-3).
2. **Движок** `apps/core/finder.py`: реестр пресетов по primary-модулю +
   спец-деревья архетипов (bakery/butcher/friseur/hotel/events);
   `tree_for(tenant)`, `enabled(tenant)`, `resolve(tenant, answers, locale)` —
   скоринг в Python по активным сущностям primary-kind (кап 200):
   слова +2 (имя/описание, локализованные), collection/category +3,
   price — жёсткий фильтр (без цены — проходит). Топ-3, лучший — в середине
   («Unser Vorschlag»); <3 → добор новейшими активными; пусто → 3 новейших
   + подсказка «спросите в чате». Карточки — `sellable_for` (контракт готов).
3. **Витрина**: `/finder/` (name `storefront-finder`, вьюха в
   promotions/public_views): серверные шаги БЕЗ JS — чипы = ссылки,
   накапливающие ответы в `?a=`; последний ответ → выдача 3 карточек
   (`sellable_card`) + «Alle ansehen →» (листинг primary) + «Noch mal».
   404, если `enabled` falsy (опция!) или primary-модуль не sellable.
4. **Демо**: включить finder в китах `friseur` и `baeckerei` (демо-кнопки
   владельца сразу показывают фичу).
5. **Тесты** `apps/promotions/tests/test_finder.py`: normalize (golden-паритет:
   ключ не материализуется), скоринг/фильтр цены/фолбэк-добор, 404 при
   выключенном, рендер шагов и выдачи, «средний = лучший».

## Вне объёма (следующие инкременты)
FD-2: секция-CTA на главной (опция в Look'ах) + пресеты остальных архетипов
глубже; FD-3: кабинет `/dashboard/finder/` (тумблер + редактор дерева,
Studio-стиль); FD-4: агрегатор. LS-3 — после FD.

## Риски
- normalize дропает неизвестные ключи → добавить `finder` в схему сразу.
- Пустая выдача не должна выглядеть ошибкой → фолбэк-добор + CTA в чат.
- i18n: лейблы пресетов — немецкие литералы (msgid-конвенция), чипы кастомных
  деревьев — свободный текст владельца (не переводим).
