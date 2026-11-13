# FB-27 «Design» — экран по макетам D1–D2

Дата: 2026-11-13. План составлен агентом `planner`. Основание — решения владельца в
`fb27-website-pages-ia-plan-2026-11-11.md` (макеты D1–D2 приняты; перестройка главной —
галочкой, по умолчанию выключена). Макеты: `docs/design/website-seiten-2026-11-11/
D1_Design.dc.html` (1440), `D2_Mobil.dc.html` (390).

## 1. Что на макетах

- Заголовок «Design», подпись «So sieht Ihre ganze Website aus…». Три вкладки:
  **Fertige Designs** (открыта) · Farben & Schrift · Karten & Fotos.
- «Empfohlen für <тип бизнеса>» с пометкой «Ändert Farben, Schrift und Kartenform. Ihre Texte
  und Blöcke bleiben». Карточки: мини-превью, имя, строка описания, «Übernehmen» + «Vorschau»
  (у кнопок имя карточки в `aria-label`); у активной — рамка и бейдж «Aktiv».
- Панель подтверждения «„Klar“ übernehmen?»: **Das ändert sich** (акцент, шрифт, карточка,
  товаров в ряд) и **Das bleibt**; «Jetzt übernehmen», «Abbrechen»; галочка «Auch die
  Startseite neu aufbauen…» — снята.
- Внизу — «Alle 18 Designs anzeigen» и ссылка «Seitenaufbau».
- 390: те же разделы, вкладки пилюлями, карточки в столбец, кнопки 44 px.

## 2. Что есть в коде (`apps/core/design_page.py`, `templates/tenant/design.html`)

Одна лента: форма «Farbe & Schrift + Karten & Fotos» → «Quick start» (демо, `apply_template`)
→ «Startpaket» (`bundles_for`) → «Looks» (все 18). POST: `apply_template`, `load_demo`,
`clear_demo`, `design_settings` (`_save_design_settings`, патч по сентинелам `*_present`),
`bundle`, `look`. `apply_bundle` пишет кожу И состав главной; `apply_look` — только кожу.
Подтверждение — `confirm()` в скрипте (без скриптов не работает).

| Макет | Сейчас |
|---|---|
| 3 вкладки | лента |
| Сначала готовые дизайны | они внизу |
| Панель «что изменится / что останется» | `confirm()`, перечня нет |
| Кожа по умолчанию, главная — галочкой | пакет всегда перестраивает главную |
| «Alle 18» вторым уровнем | все Looks видны сразу |
| Подписи 13–14 px, «Sie» | 10–11 px, местами «du» |
| Демо-содержимого на экране нет | блок «Quick start» |

## 3. Решения

| № | Вопрос | Решение |
|---|---|---|
| Р1 | Граница «кожа ↔ главная» | Без галочки — `apply_look` + оси оформления пакета (форма карточки, фото, стили секций без включения и порядка, раскладка каталога). С галочкой — полный `apply_bundle`. Писатель один: `_apply_bundle_axes` делится на две части. **Вопрос владельцу.** |
| Р2 | Подтверждение без скриптов | «Übernehmen» — ссылка `?tab=fertig&confirm=<key>`; сервер рисует панель; «Jetzt übernehmen» — POST; «Abbrechen» — ссылка. |
| Р3 | Перечень «Das ändert sich» | Чистая функция `sitetemplates.design_diff(cfg, key, rebuild)` на том же коде, что превью-оверлей (оверлей выносится в функцию — второй копии логики нет). |
| Р4 | `design.bundle` без перестройки главной | Пишем `{look, bundle}` — бейдж «Aktiv» честный. |
| Р5 | Шаблоны (`apply_template`) | Из интерфейса убрать, обработчик оставить на релиз. |
| Р6 | Демо laden/löschen | Строка внизу вкладки «Fertige Designs». **Вопрос владельцу.** |
| Р7 | «Alle 18» | `?alle=1` (только кожа, без галочки). |

## 4. Срезы

- **D-a — вкладки.** `?tab=`, форма на вкладку со своими сентинелами, «Sie», 44 px.
- **D-b — «Fertige Designs» и подтверждение.** Разделение осей, `design_diff`, `confirm`,
  `rebuild_home`.
- **D-c — «Alle 18», демо, телефон, доступность.**

## 5. Замки (до кода)

- W0: форма каждой вкладки без правок не меняет `site_config` и `primary_color` — для
  каждого из 18 Looks.
- Форма «Karten» не трогает шрифт и тему; «Farben» — `site_defaults`.
- Без `rebuild_home` секции и блоки главной не меняются, кожа меняется; с ним — результат
  равен `apply_bundle`.
- `?confirm=<мусор>` — 200 без панели; POST с неизвестным ключом — отказ, конфиг цел.
- В разметке нет `onsubmit=`; у кнопок — имя карточки.
- `design_diff` совпадает с фактическим результатом применения.

Осознанно переписать: `test_stu12_design_screen` (2 теста), `test_design_page` (3 теста);
сверить `test_sitetemplates`, `test_looks`, `test_stu12_shell`, `test_w11_5_redirect`.

## 6. Риски и откат

Смена смысла POST `bundle` — мастер и демо-киты зовут `apply_bundle` напрямую, их не трогаем.
Миграций нет; откат — revert коммита среза.

## 7. ECC-прогоны

- До кода: `django-patterns`, `django-tdd`, `accessibility`, `e2e-testing`; `docs/pitfalls.md`.
- `django-reviewer` — каждый срез; `security-reviewer` и `silent-failure-hunter` — D-b;
  `a11y-architect` — D-a, D-c; стенд Playwright 1440/390, de/ru, без скриптов — D-b, D-c.
