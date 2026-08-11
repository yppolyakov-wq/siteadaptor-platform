# SM-4: раскрывающиеся подпункты разделов в сайдбаре (план)

Запрос владельца (2026-08-11, скрин «Расширенный» на Angebote): «вынесем
настройки в дополнительные пункты продаж, предложений и т.д. — выпадающим
списком для каждого раздела; отчёты — в продажах». Уточнение mid-turn:
**выпадающий список — слева в МЕНЮ (сайдбар), раскрытие «слайдером»; у
Веб-сайта в подпунктах — и добавление домена**. Решения по развилкам
(AskUserQuestion): Finanzen → Продажи · Abläufe только в списке (кнопку из
тулбара убрать) · каталожные страницы — единый компакт-бар · Website — фикс
SEO-страницы + подпункты.

## 0. Принцип

**Подпункты раздела в сайдбаре = advanced-состав его хаба из `nav_registry`**
(единый источник правды W8: гейты модулей, палитра Ctrl+K и подсветка «где я»
достаются даром). Основные табы остаются НА странице хаба; сайдбар раскрывает
глубокие/настроечные входы. Раскрытие — `<details>`-слайдер: активный раздел
раскрыт автоматически, шеврон — вручную; строка-якорь остаётся ссылкой.
Мобильный таб-бар (первая четвёрка) не трогаем.

## 1. Состав подпунктов по разделам (после переездов)

| Раздел | Подпункты (advanced его хабов) | Откуда |
|---|---|---|
| Übersicht | — | |
| **Verkäufe** | 📊 Auswertungen (gate analytics) · 💶 Finanzen (gate finance) · 🛎 Berichte Hotel (`stays:reports`, gate stays) · ⚙️ Abläufe (`ablaeufe`) | Auswertungen+Finanzen ПЕРЕЕЗЖАЮТ из settings-хаба; stays:reports — сирота получает вход; ablaeufe — дубль-запись (таб Einstellungen остаётся) |
| **Angebote** | Produkte · Kategorien · Lager · Einkauf · Kombi · Import · Kollektionen | уже есть (sellables advanced — ровно скрин) |
| **Marketing** | Einlösen · Treuepunkte · Telegram · Kanäle · Beiträge · Blog & News · Newsletter | уже есть (marketing advanced) |
| **Website** | 🔍 SEO (`site-seo`) · 🌐 Domains (`domains` — «добавление домена») · 🖼 Medien (`media-library`) | НОВЫЙ хаб `site` в ENTRIES; Domains переезжает из main-табов settings, Medien — из advanced settings |
| **Einstellungen** | Zusatzleistungen · Funktionen · Finder · Hilfe | как было, минус Medien |

Settings-хаб слимится: main 12 → 9 табов (−Finanzen, −Auswertungen,
−Website & Domains), advanced 5 → 4 (−Medien).

## 2. Изменения по файлам

1. **`apps/core/nav_registry.py`**:
   - `HUBS` += `"site"`; ANCHORS: якорь Website получает `hubs=("site",)`,
     якорь Verkäufe уже `("board",)`.
   - board-хаб += advanced-записи: Auswertungen (`promotions:analytics`,
     nav `analytics`, gate analytics), Finanzen (`finance:journal`, nav
     `finance`, gate finance), Berichte (`stays:reports`, nav `stays`, gate
     stays), Abläufe (`ablaeufe`, nav `ablaeufe`) — дубль-запись класса
     sellables/catalog (палитра дедупит по url_name).
   - settings-хаб: удалить записи Finanzen/Auswertungen/Domains; Medien →
     site-хаб. site-хаб: SEO (`site-seo`, nav `seo`) · Domains (`domains`,
     nav `domains`) · Medien (`media-library`, nav `media`) — все advanced
     (main-табов у site нет: страница хаба = Studio).
   - НОВОЕ: `sidebar_children(anchor_key)` — advanced-записи хабов якоря
     (url_name/label/nav/module_key) для сайдбара.
   - Подсветка: nav `finance`/`analytics` теперь через board-хаб → якорь
     Verkäufe; nav `seo`/`domains`/`media` через site-хаб → якорь Website
     (auto из `_anchor_by_hub`). `site_seo` view: `nav="site"` → `nav="seo"`.
2. **`apps/core/modules.py::sidebar_nav`** (или контекст): каждому якорю —
   `children` (гейт по модулю через `is_module_active`, как hub_tabs).
3. **`templates/tenant/_base_dashboard.html`** (десктоп-сайдбар): якорь с
   children → `<details class="group">` со стрелкой-шевроном; `open` при
   активном якоре/подпункте; подпункты — компактные ссылки с подсветкой по
   `nav`. Мобильный таб-бар без изменений.
4. **`templates/core/verkaeufe.html`**: убрать «⚙️ Abläufe» из тулбара
   (решение владельца — только в списке). Контекстные входы настроек модулей
   в шапках календарей (`_tagesplan_body`/`_belegungsplan_body`) остаются.
5. **`templates/finance/journal.html`, `templates/promotions/analytics.html`,
   `templates/tenant/domains.html`, `templates/tenant/media_library.html`,
   `templates/tenant/site_seo.html`**: снять `hub_tabs "settings"` (иначе
   рисуется чужой таб-бар без активного таба — класс дефекта site_seo).
   Взамен — заголовок как был; навигация — сайдбар.
6. **Каталог-компакт (решение владельца)**: в catalog-хабе Lager/Kombi/Import
   → advanced (main: Angebote·Produkte·Kategorien; advanced: Lager/Einkauf/
   Kombi/Import/Kollektionen) — таб-бар каталожных страниц совпадает по духу
   со скрином Angebote.

## 3. Замки (характеризационные — ДО правок; осознанные переписки — W9/ST-4b)

1. Сайдбар: у Verkäufe/Angebote/Marketing/Website/Einstellungen есть
   подпункты; Auswertungen/Finanzen/Berichte/Abläufe — под Verkäufe;
   Domains/SEO/Medien — под Website; гейт модуля (нет analytics → нет
   Auswertungen); Übersicht без подпунктов.
2. Settings-хаб: Finanzen/Auswertungen/Domains/Medien в табах НЕТ (осознанная
   переписка W9-замков состава).
3. `verkaeufe.html`: в тулбаре нет ссылки на ablaeufe (осознанная переписка).
4. Палитра Ctrl+K находит Berichte/Finanzen/Auswertungen/SEO (новые/переехавшие
   записи reverse'ятся — инвариант W8 уже это ловит).
5. Подсветка: nav finance/analytics → якорь Verkäufe; nav seo/domains/media →
   якорь Website.
6. Каталог: product_list — main-табы ≤3 + Erweitert с Lager (осознанная
   переписка test_hub_tabs).
7. site_seo/journal/analytics/domains/media_library: settings-таб-бара нет.
8. Golden normalize: не затронут (навигация — не site_config).

## 4. Порядок

Один инкремент, БЕЗ миграций: реестр → sidebar_children + шаблон сайдбара →
чистки шаблонов → замки → локальный гейт (ruff + core/tenants/catalog/
promotions/finance + i18n_gap + template_comments) → стенд Playwright
(раскрытие слайдера, переходы, подсветка, гейты по модулям на 2-3 демо) →
push → CI → мерж. Новые msgid: только «Berichte» при отсутствии (проверить;
остальные метки уже переведены).

## 5. Вне волны (кандидаты, зафиксировано)

- Легаси-доска `/dashboard/board/` с дублем «Customize columns» — кандидат на
  снос (входы: «Full view» на Übersicht).
- Контекстные настройки модулей (booking Services/Passes; stays Units/Preise;
  orders KDS/QR) — остаются в шапках календарей; при желании владельца можно
  добавить вторым уровнем в подпункты Verkäufe (v2).
- Studio-подстраницы site-menu/pages/sections/preview — без изменений.
