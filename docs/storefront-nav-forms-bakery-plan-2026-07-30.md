# План: меню витрины v2 + ширина форм + главная Bäckerei (2026-07-30)

Фидбэк владельца (3 пункта, референс unitheme.net — CS-Cart-тема с классической
магазинной шапкой): (1) верхнее меню непрактично для всех архетипов — нужна одна
строка с нормальными дропдаунами; (2) формы витрины прижаты влево, справа пустота;
(3) «Our offerings» непрактичен для пекарни — первым слайдер + блок «направлений»
(акции / каталог / заявка Partyservice / предзаказ ко времени).

Разведка: шапка инлайн в `storefront/_base.html:84-175` (group-дропдаун hover-only,
ряд без `whitespace-nowrap` → «About us» ломается в 2 строки, нет overflow-механики);
гастро-плитки — `sections/_hero_widget.html` ветками по `site_defaults.hero_widget`
(presence-minimal whitelist `siteconfig.py:892`, data-driven — расширяемо);
«Our offerings» — секция `archetypes` (выкл по умолчанию, кит включает флагом);
~27 шаблонов с `max-w-*` без `mx-auto` (полный список — отчёт разведки).

## И1 — меню v2 (все архетипы, только шаблон+JS, без миграций)
- Пункты ряда: `whitespace-nowrap` (лечит перенос), font-medium, hover-подчёрк.
- Overflow «Mehr ▾»: JS меряет ширину ряда, не влезающие пункты уходят в дропдаун
  «⋯» справа (resize-aware). Группы уходят целиком (дети с отступом).
- Дропдаун group: hover + `focus-within` (клавиатура) + тап-toggle на мобиле-десктопе.
- Стили classic/centered/minimal сохраняются; бургер/таб-бар не трогаем.
- Замок: рендер шапки с группой — дропдаун-разметка, nowrap.

## И2 — формы/страницы по ширине (только классы)
- Всем контейнерам из списка разведки добавить `mx-auto` (формы — на `<form>`).
- `anfrage.html` расширить до `max-w-2xl mx-auto` (одноколоночная форма).
- Паритет-замки buybox/календарей: прогнать, обновлять ОСОЗНАННО только если
  пиняют полную строку класса (ожидаю: точечные).

## И3 — главная Bäckerei: слайдер + направления
- `hero_widget` whitelist += `"bakery"`; ветка в `_hero_widget.html`: 4 плитки —
  🔥 Aktionen (→ /aktionen/), 🥨 Sortiment (→ /sortiment/), 🎉 Partyservice
  (→ /anfrage/, гейт jobs), ⏰ Zur Wunschzeit vorbestellen (→ /sortiment/,
  подпись «жми — заберёшь без очереди к выбранному часу»). Сетка sm:grid-cols-2.
- Ветка `heroes`-слайдера в `_hero.html` начинает включать `_hero_widget`
  (раньше виджет терялся при слайдере — латентный пробел; гейт: ключ задан).
- Кит BAKERY: `heroes` = 3 слайда (Brot/Torten/Feierabendtüte),
  `hero_widget="bakery"`, `enable_archetypes_section=False` («Our offerings» долой).
- Замки: hero_widget bakery рендерит 4 плитки; слайдер+виджет вместе.

Гейты: ruff + pytest (promotions/tenants/core затронутые) + template_comments +
`npm run build:css` при новых классах. Стенд: скрины меню (десктоп узкий/широкий),
anfrage по центру, главная пекарни. Коммиты по инкрементам, один CI на верхушке.
