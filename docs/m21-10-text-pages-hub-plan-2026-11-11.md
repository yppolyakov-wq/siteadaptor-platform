# M21.10 — «Seiten» = единый центр всех текстовых страниц + полноценный редактор (план, 2026-11-11)

## 0. Что проверено в коде (факты)
- Своих страниц две системные: `SYSTEM_PAGES = {"versand": "storefront-shipping", "ueber-uns": "storefront-about"}` (`apps/core/content_pages.py`). «Versand» исчезает (`system_url` → None), если модуль `orders` выключен.
- В меню (`apps/tenants/menu.py`) есть цели `_PAGE_URL_NAMES` / `PAGE_TARGET_LABELS`. **Там нет Versand, Impressum, Datenschutz, Widerruf и AGB.** Тип `cpage` берёт только опубликованные `ContentPage`. Поэтому без своей страницы `versand` ссылку на `/versand/` в меню поставить нельзя: это и есть жалоба владельца.
- Правовые адреса уже есть: `storefront-impressum|privacy|withdrawal|agb|shipping` (`config/urls_tenant.py:945–951`). Текст берётся через `apps/core/legal.py::legal_text`: LegalDoc[локаль] → LegalDoc[дефолт] → плоское поле → автотекст. У AGB без текста страницы нет (404).
- Права (`apps/core/view_perms.py`): у `legal-docs` стоит `_r(FLOOR)`, править может только владелец. У `content-pages*` — `website.view/edit`, у `content-page-image` — `website.edit`. В `legal_docs_view` (`apps/core/views.py:1742`) в одном POST записываются и налоговые реквизиты (`sec_steuer`), и тексты `doc_<kind>_<locale>`.
- «Über uns»: на `/ueber-uns/` своя страница `ueber-uns` побеждает `site_config["about_text"]` (`apps/promotions/public_views.py:1107`). `about_text` при этом живёт ещё в секции главной и на канве Студии.
- Санитайзер: `apps/core/richtext.py::sanitize_page` (nh3). Атрибут `class` разрешён только у `div/p/figure/h2/h3` и проходит фильтр `^sf-(grid|center|col-N)$`. **У `img` класса нет, у `h4/blockquote/li` тоже.** JS-копия `safeCopy` в `templates/catalog/_richtext_editor.html:35–64` повторяет те же списки вручную, это второй источник правды.

## 1. Решения (предлагаю, нужен «ок» владельца)
- **Р-1. Один экран.** На `/dashboard/website/seiten/` (`pages_list`) три группы.
  - **Systemseiten**: «Über uns», «Versand» (только если магазин отправляет или продаёт: модуль `orders` активен) и «Kontakt».
  - **Rechtliches**: Impressum, Datenschutz, Widerruf, AGB.
  - **Eigene Seiten**: добавить, изменить, удалить.
  - Каждая строка показывает: статус (свой текст / автотекст / пусто), языки с текстом, адрес, «Ansehen», «Bearbeiten».
- **Р-2. «Kontakt» — без текстовой страницы.** `/nachricht/` — это форма. Строка ведёт в настройки контактов, редактора там нет. Иначе получилась бы вторая сущность «текст над формой» без потребителя.
- **Р-3. Правовые тексты правятся прямо в «Seiten».** Хранилище прежнее — `LegalDoc` (kind × locale), фолбэк `legal.py` не трогаем.
  - Новая вьюха `legal-page-edit/<kind>/` с тем же редактором `data-rte="page"`.
  - Языки — переключателем E9.10 (`tenant/_i18n_switch.html`).
  - Кнопка «Automatischen Text übernehmen» вставляет автотекст в поле. На запись она не влияет.
  - Пустое поле удаляет строку, как сейчас (presence-guard `doc_<kind>_<locale>`).
  - **Право: `FLOOR` (только владелец).** Это юридическая ответственность § 5 DDG. Новое право в `permissions.py` не вводим. Сотрудник с `website.edit` видит строки «Rechtliches» с 🔒 и пометкой «Nur Inhaber», кнопка «Bearbeiten» скрыта через `can_open`.
  - В «Recht & Steuern» остаются только налоговые и Impressum-реквизиты (`sec_steuer`). Блок текстов `doc_*` оттуда снимаем и ставим ссылку «Texte bearbeiten → Seiten». Иначе у одних данных было бы два писателя.
  - Писатель текстов выносится в `apps/core/legal.py::save_legal_doc(kind, locale, html)`: санитайз → upsert или delete. Его зовут обе вьюхи, пока старая форма жива, потом остаётся одна.
- **Р-4. «Über uns» — один источник для страницы.** Текст страницы `/ueber-uns/` хранит `ContentPage(slug="ueber-uns")`.
  - Data-миграции нет. При первом «Bearbeiten» системной строки, если страницы нет, создаётся черновик с телом из `about_text`: экранированный плоский текст, переносы → `<p>`. Создание идемпотентно через `get_or_create` с ловлей IntegrityError.
  - `about_text` остаётся тизером секции главной на канве Студии.
  - Канва Студии на `/ueber-uns/`: если своя страница существует, инлайн-правка тела отключается, вместо неё подсказка «Text wird unter Website › Seiten bearbeitet» со ссылкой. Иначе правка на канве молча не была бы видна, а это класс дефектов «обещание без исполнения».
- **Р-5. Системная «Versand» без своей страницы** тоже открывается редактором: та же ленивая заготовка со способами доставки (`show_shipping_methods=True`).

## 2. Цели меню (батч B2)
- В `_PAGE_URL_NAMES` и `PAGE_TARGET_LABELS` (единственный реестр) добавить `shipping → storefront-shipping`, `impressum`, `privacy`, `withdrawal`, `agb`.
- Гейты добавляются в тот же `_page_has_content` / `_PAGE_MODULE_GATES`, второго списка не заводим:
  - `shipping` — только когда `content_pages.system_url("versand")` не None;
  - `agb` — только когда `legal_text(tenant, "agb")` непустой;
  - `impressum` / `privacy` / `withdrawal` — всегда, у них есть автотекст.
- Если у бизнеса есть `cpage:versand` и одновременно `page:shipping`, дубль не нужен. Оба ведут на один адрес: `system_url` уже даёт `/versand/`.
- Селект целей в «Website › Menü» (`page_target_choices`) получит новые пункты сам. Подвал тоже.
- Демо-киты не меняем: в подвале правовые ссылки уже есть отдельно.

## 3. Редактор (батчи B3–B4), всё через белый список классов, `style` запрещён
| Функция | Разметка | Класс |
|---|---|---|
| Выравнивание текста | `p/h2/h3/h4/li/blockquote` | `sf-left`, `sf-center` (уже есть), `sf-right`, `sf-justify` |
| Размер фото | `img` или обёртка `figure` | `sf-img-sm` (25 %), `sf-img-md` (50 %), `sf-img-lg` (75 %), `sf-img-full` |
| Положение фото | `figure` | `sf-float-left`, `sf-float-right`, `sf-center` (у float на мобильном ширина 100 %) |
| Подпись фото | `figure > img + figcaption` | — |
| Alt-текст | `img[alt]` | — (поле в поповере фото обязательно, предупреждение при пустом) |
| Заголовки | `h2/h3/h4` | уже есть |
| Цитата, разделитель | `blockquote`, `hr` | добавить `hr` |
| Колонки | `sf-grid` + `sf-col-N` | уже есть |
| Undo/Redo | `execCommand('undo'/'redo')` + Ctrl+Z / Ctrl+Y | — |
| Таблица | **не в v1** | предлагаю отдельным решением (пейсты из Word ломают вёрстку, a11y заголовков) |

- **Один источник белого списка.** Регулярка классов, список тегов и атрибуты переезжают в `apps/core/richtext.py::PAGE_RULES`. Шаблон получает их через `{{ rte_rules|json_script:"rte-rules" }}` (контекст редактора). Ручные `PAGE_TAGS` и регулярка в JS удаляются. Замок: JSON в шаблоне совпадает с Python.
- В `sanitize_page` добавить:
  - атрибут `class` у `img/h4/li/blockquote/figure`;
  - тег `figcaption`, `hr`;
  - у `img` атрибут `loading` только со значением `lazy`. Атрибут ставит рендер, не ввод.
  - `alt` у `img` обрезать до 300 символов.
- UI: поповер выбранного фото (S/M/L/Voll · Links/Mitte/Rechts · Alt · Bildunterschrift · Entfernen). Кнопки выравнивания текста в тулбаре. Тулбар = `role="toolbar"` с roving tabindex, `aria-pressed` у активных, у иконок `aria-label`.
- Витрина: CSS классов в `static/src` с `@layer components`. Safelist `^sf-(img|float|left|right|justify)` в Tailwind-конфиге, затем `npm run build:css` и `static/css/app.css` в коммите. Проверить `_page_body.html` и `legal` шаблоны: рендерятся через `sanitize_page`, затем `|safe`.
- Правовые шаблоны (`impressum/datenschutz/widerruf/agb`): плоский текст (`is_rich` False) рисуется как прежде (pre-line). Rich проходит `sanitize_page` на рендере.

## 4. Безопасность
- Санитайз дважды: при записи (`save_page`, `save_legal_doc`) и при показе. Замок: XSS-набор (`<img onerror>`, `javascript:`, `style=`, `<svg>`, `class="sf-x evil"`, `/\\host`, `%2f`, `<a href=data:>`) прогоняется через обе функции.
- Загрузка картинки (`page_image_upload`): прежние лимиты (размер, сигнатура, EXIF-strip). Добавить rate-limit `ratelimit.hit("page-img", user, 30/ч)` и проверку, что правка правовой страницы тоже идёт через `website.edit`. Картинку правового текста вставляет владелец, так что `FLOOR` ⊇ `website.edit`.
- Права по действиям:
  - `content-page-new/edit/delete/image` — `website.edit`;
  - `legal-page-edit` — `FLOOR`;
  - запись в `view_perms.RULES`, иначе middleware fail-closed.
  - Удаление системной страницы = «вернуть автотекст» (для «Über uns» — `about_text`). Сам адрес не удаляется.
- POST только с CSRF. Вставка из буфера проходит через `safeCopy` (клиент) и через сервер. Сообщения об ошибках без утечки HTML.
- `X7`: новый экран `legal-page-edit` — параметризованный, вход из «Seiten». Отметить в nav_registry / EXPECTED_UNLISTED по `docs/cabinet-screen-dod.md`.

## 5. Батчи (каждый: замки ДО кода → локальный гейт → CI → FF в main)
- **B1. Хаб «Seiten» (без миграций).** Группы, статусы и языки в строках. Ленивое создание системных страниц (Р-4, Р-5). «Kontakt»-строка ссылкой. 🔒 у правовых строк для не-владельца.
  - Файлы: `apps/core/content_page_views.py`, `apps/core/content_pages.py` (`system_rows(tenant)`, `ensure_system_page(slug)`), `templates/tenant/content_pages.html`.
  - Замки: `apps/core/tests/test_m21_10_hub.py` — все архетипы (параметр 16 типов): строки видны; Versand есть ⇔ orders активен; ленивое создание из `about_text` идемпотентно; сотрудник с `website.edit` не видит «Bearbeiten» у правовых.
- **B2. Правовые тексты в «Seiten» + цели меню.**
  - Код: `legal-page-edit` + `save_legal_doc`; снять блок `doc_*` из `legal_docs_view` (оставить `sec_steuer`), шаблон «Recht & Steuern» → ссылка; меню §2.
  - Замки:
    - POST `legal-page-edit` от не-владельца → 403;
    - пустое поле удаляет LegalDoc и включает фолбэк;
    - сохранение реквизитов в «Recht» не трогает тексты (W0);
    - каждая новая цель меню реверсится;
    - `agb` гаснет без текста, `shipping` — без orders;
    - селект меню содержит все `PAGE_TARGET_LABELS`.
- **B3. Белый список одним источником + сервер.** Новые классы, теги и атрибуты в `richtext.py`, `json_script` в редакторе, CSS витрины, safelist, `app.css`.
  - Замки: `apps/core/tests/test_richtext_page.py` — паритет JS↔Python, XSS-набор, каждый класс проходит, чужой отбрасывается, `style` всегда режется.
- **B4. UI редактора.** Поповер фото, выравнивание, `hr`, `figcaption`, undo/redo, a11y тулбара. Студия на `/ueber-uns/` показывает подсказку вместо инлайн-правки, когда страница существует.
  - Стенд Playwright `scripts/rte_stand.py`: вставить фото → M → справа → alt → сохранить → витрина показывает `figure.sf-float-right img.sf-img-md`; пейст HTML с `style` и `onerror` очищается; Ctrl+Z работает; 390 px без переполнения; de и ru.
- **B5. Демо и документы.** `seed`: у одного товарного кита своя страница «Versand» с фото, у отеля — «Über uns» с колонками (`SEEDER_VERSION` +1). Обновить build-log, task-catalog (M21.10a–e) и §3 CLAUDE.md.
- **Миграции не нужны.** Хранилища `ContentPage` / `LegalDoc` прежние, новые классы живут в HTML. Если владелец захочет таблицы — отдельное решение.
- **i18n:** все новые подписи (группы, статусы, поповер, «Nur Inhaber», «Automatischen Text übernehmen», цели меню) — немецкий msgid → `.po` × 5 (de/en/tr/ru/uk). Перед пушем `uv run python scripts/i18n_quickcheck.py`; подписи кнопок в JS — через `json_script`, не литералами.
- **Гейт перед пушем:** `ruff check .` и `ruff format --check .` целиком, `apps/core/tests/test_template_comments.py`, `test_x0_x7_locks.py`, `apps/tenants` (меню и демо-киты).

## 6. Риски
- Сейчас правовые тексты пишутся из двух мест (переходный период B2). Риск закрываем одним писателем `save_legal_doc` и снятием формы в том же батче.
- Ленивое создание «Über uns» меняет вид `/ueber-uns/` только после «Speichern»: создаём черновиком (`is_published=False`), публикует владелец. Значит, до публикации витрина показывает прежний `about_text` без изменений.
- Float-картинки ломают колонки на узком экране. На мобильном float снимаем (CSS `@media`), проверяем стендом.
- Расхождение JS/сервера. Закрываем одним источником правил и замком паритета.

## 7. ECC-прогоны
- **Скиллы до кода:** `django-patterns`, `django-security`, `django-tdd`, `accessibility`, `e2e-testing`, `error-handling`. Плюс `docs/pitfalls.md`: разделы «шаблоны», «i18n», «права».
- **Сразу после плана:** `security-reviewer` — ревью плана (белый список, права FLOOR и website, загрузка); `a11y-architect` — макет тулбара и поповера фото до B4.
- **B1/B2:** `django-reviewer` (всегда); `security-reviewer` — права legal-page-edit, presence-guard, отсутствие второго писателя.
- **B3:** `security-reviewer` — санитайзер и XSS-набор; `django-reviewer`.
- **B4:** Playwright-стенд (`e2e-runner`, Python-Playwright, Chromium в `/opt/pw-browsers`); `a11y-architect` — проверка готового тулбара; `django-reviewer`.
- **database-reviewer:** не нужен, миграций нет. Звать, если появится таблица или data-миграция «Über uns».
- **Перед мержем ветки:** `code-reviewer` по всей ветке; `doc-updater` для build-log, task-catalog и §3 CLAUDE.md.

## 8. A11y-ревью плана M21.10 §3 против текущего `_richtext_editor.html` (WCAG 2.2 AA)

### 0. Что не так сейчас (факты из шаблона)
- Панель: `<div class="rte-bar">` без `role="toolbar"`, все кнопки в Tab-порядке (14+ остановок), нет `aria-pressed`.
- Кнопки 28×26 px (<44, но ≥24: ок для 2.5.8, ниже комфорта). Зазор 2px — на границе, считать только пока размер ≥24.
- Подписи: `aria-label` есть, но «B/I/U/•/1.» в `textContent` — иконки; `🔗` и `🖼` — эмодзи (SR читает по-разному). Нужен `aria-hidden="true"` на глифе.
- `.rte-area` `role="textbox"`: хорошо. Но подпись берётся из `label[for]` только если у textarea есть id.
- Статус загрузки пишется в `[data-rte-status]` — но живого региона нет (проверить в разметке, в скрипте только textContent). Нужен `role="status"`.
- Картинки вставляются с `alt=""` — молча «декоративные»: нарушение 1.1.1 по умолчанию.
- Ссылка и адрес картинки — `window.prompt` (нет программируемой метки, не стилизуется). Заменить на поповер-диалог.
- Цвет кнопок `#374151` на `#fafbfc` ≈ 9:1 — ок. hover `#4338ca` на `#eef2ff` ≈ 7:1 ок. Граница панели `#e5e7eb` на белом ≈ 1.25:1 — для границы поля ввода нужно ≥3:1 (1.4.11): `.rte-area` и `.rte-bar` границу сменить на ≥ `#767676`-класса (напр. `#6b7280`). Фокус: `.rte-area:focus{outline:none; border-color:#a5b4fc}` — индикатор ≈1.8:1, НАРУШЕНИЕ 2.4.7/1.4.11/2.4.13 → заменить на `outline:2px solid #4f46e5; outline-offset:2px`.
- Нет дефиса: `title` дублирует `aria-label` — оставить только `aria-label` + видимый tooltip по hover/focus (1.4.13: скрываемый, наводимый, постоянный).

### 1. Тулбар (паттерн APG Toolbar)
Атрибуты:
- Контейнер: `role="toolbar" aria-label="Textformatierung" aria-controls="<id .rte-area>"`, `aria-orientation="horizontal"` (по умолчанию, можно не ставить).
- Группы: `<div role="group" aria-label="…">` — Zeichen (B/I/U), Absatz (H2/H3/H4/¶/Zitat), Ausrichtung (links/zentriert/rechts/Blocksatz), Listen (•/1.), Einfügen (Link/Bild/Spalten/Trennlinie), Verlauf (Rückgängig/Wiederholen). Визуально разделитель `role="separator"` не нужен внутри toolbar, достаточно `aria-hidden` span.
- Roving tabindex: ровно одна кнопка `tabindex="0"`, остальные `tabindex="-1"`; ←/→ двигают (циклично), Home/End — первая/последняя; Tab выходит из панели в `.rte-area`. Запоминать последнюю активную кнопку. ↑/↓ не перехватывать.
- Состояния: форматы-переключатели (B, I, U, списки, выравнивание, H2/H3/H4, Zitat) — `aria-pressed="true|false"`, обновлять на `selectionchange` (`document.queryCommandState`/проверка блока). Группа выравнивания — взаимоисключающая: допустимо `aria-pressed` на каждой (простой вариант) — не смешивать с `role=radio` внутри toolbar. Действия (Link, Bild, Spalten, Hr, Undo, Redo) — без aria-pressed.
- Undo/Redo: `aria-disabled="true"` (не `disabled`, чтобы оставались в roving-порядке) когда нечего отменять; `aria-keyshortcuts="Control+Z"` / `"Control+Y Control+Shift+Z"`.
- Имя кнопки: `aria-label="Fett"` и т.д.; глиф внутри `<span aria-hidden="true">`. Для выравнивания в имени — действие + состояние не дублировать (состояние даёт aria-pressed).
- Ввод в `.rte-area` не должен терять выделение при клике по кнопке: оставить `mousedown` + `preventDefault()` (иначе фокус уходит и `aria-pressed` врёт). Для клавиатуры фокус остаётся на кнопке: после действия НЕ возвращать фокус в область автоматически (APG), но предложить `Escape` на панели = вернуть фокус в `.rte-area` (без смены выделения — выделение хранить в `saved`, т.к. SR-пользователь и так его потеряет).
- Горячие клавиши в области: Ctrl+B/I/U (нативно), Ctrl+Z/Y, плюс `Alt+F10` (как Word/TinyMCE) — фокус на панель; документировать в `aria-describedby` скрытой подсказкой: «Alt+F10 Symbolleiste, Alt+F9…». Не конфликтовать с SR-командами.
- Мобильный 390px: панель `flex-wrap: wrap` (не горизонтальный скролл — 1.4.10 reflow), кнопки min 44×44 CSS px на `pointer: coarse` (сейчас 28×26), на десктопе ≥24×24 при зазоре ≥2px (2.5.8). Группы переносятся целиком; sticky-панель (`position: sticky; top:0`) должна учитывать `scroll-padding-top` (2.4.11 Focus Not Obscured) — иначе sticky закрывает фокус в области.

### 2. Выбор изображения клавиатурой внутри contenteditable
Проблема: `<img>` в contenteditable не фокусируется и не выбирается стрелками надёжно (в Chromium стрелка перешагивает как «символ», выделение схлопывается; SR читает «Grafik» только в browse-mode). Предлагаю подход «обёртка-виджет + явная команда»:
1. Каждую вставленную картинку оборачивать в `<figure contenteditable="false" tabindex="-1" class="sf-…">` (на этапе рендера редактора; на серверный HTML не влияет, `contenteditable`/`tabindex` в санитайзере режутся — удалять перед `sync()`; хранить только `figure>img(+figcaption)` с whitelisted-классами). `figcaption` внутри — вложенный `contenteditable="true"` (для подписи) — тогда она редактируется прямо, `role="textbox" aria-label="Bildunterschrift"`.
2. Роль виджета: `role="group" aria-roledescription="Bild" aria-label="Bild: <alt или «ohne Alternativtext»>"` + `tabindex="0"` у фигур (все figure в Tab-порядке? — нет: делать **roving внутри области** слишком хрупко). Поэтому: фигура получает `tabindex="-1"`, а доступ даёт:
   - Стрелки: каретка стоит рядом с фигурой → `ArrowRight/ArrowLeft` перехватываются обработчиком `keydown` на `.rte-area`: если следующий узел по направлению — `figure`, вызвать `figure.focus()` (фокус на виджет, `preventDefault`). Это даёт «вход» стрелками.
   - Сочетание **Enter/Space/F2** на сфокусированной фигуре = открыть поповер; **Delete/Backspace** = удалить (с анонсом «Bild entfernt», Undo доступен); **Escape**/ArrowUp/ArrowDown = вернуть каретку в текст рядом (выделение `Range` до/после фигуры); `Shift+Enter`/Enter у каретки перед фигурой не должны ломать её.
   - Кнопка тулбара «Bildeinstellungen» (`aria-haspopup="dialog"`, `aria-expanded`) — становится активной (`aria-disabled=false`), когда выделение содержит/касается figure; также `aria-keyshortcuts="F2"`. Это запасной путь для SR-пользователей без фокуса на фигуре.
   - Мышь/touch: клик по img → `figure.focus()` + `aria-selected`-стиль (рамка ≥3:1, не только цвет: плюс угловые маркеры) и всплывающая кнопка «Bild bearbeiten» (44px, `aria-label`) у фигуры — видимая, чтобы на 390px не нужен был двойной тап (2.5.1/2.5.8; жест — только одиночный указатель).
3. Анонс при входе на фигуру: `aria-label` фигуры содержит alt и состояние («Bild, Größe M, links, Alternativtext: …»), подсказка `aria-describedby` «Enter: bearbeiten, Entf: entfernen».
4. Не использовать `role="img"` на figure (скроет потомков, figcaption перестанет редактироваться).

### 3. Поповер фото — non-modal dialog
- Разметка: `<div role="dialog" aria-modal="false" aria-labelledby="rte-img-h" id="rte-img-pop">` с заголовком «Bild» (`h2`/`id`), НЕ `<dialog>.showModal()` (модальный ловит фокус и делает остальное inert — противоречит «поповер»). `aria-modal="false"` явно.
- Фокус: при открытии — на первое поле (Alt-текст, т.к. он обязателен); без фокус-ловушки: Tab идёт по диалогу и выходит дальше в документ; при выходе из диалога Tab/Shift+Tab закрывать НЕ нужно, но Escape закрывает.
- Escape: закрыть, вернуть фокус на `figure` (или на кнопку-вызывальщик, если открыт из тулбара — хранить `opener`). Фокус не должен падать в `body`. Если фигура удалена («Entfernen») — фокус на `.rte-area` в позиции удаления (сохранить Range) + анонс.
- Позиционирование: рядом с фигурой, но на 390px — нижний лист на всю ширину (`position: fixed; bottom:0; max-height:70vh; overflow:auto`), чтобы не перекрывать фокусируемый элемент (2.4.11) и клавиатурный фокус внутри (`scroll-margin`). Видимая кнопка «Schließen» (`aria-label="Schließen"`, 44px) в шапке — для touch/SR.
- Размеры/положение — радио-группы: `<fieldset><legend>Größe</legend>` с 4 `input[type=radio]` (S 25 %, M 50 %, L 75 %, Voll) и `fieldset` «Position» (Links, Mitte, Rechts). Нативные radio дают стрелки, `aria-checked` бесплатно, правильную группу. Метки видимые («S», «M»…) + `aria-describedby`/текст «25 % der Breite» — не только буква (3.3.2). Не использовать `button+aria-pressed` для эксклюзивного выбора.
- Alt: `<label for="rte-img-alt">Alternativtext (Beschreibung des Bildes)</label><textarea|input maxlength="300" aria-required="true" aria-describedby="alt-help alt-err">`. Подсказка: «Beschreiben Sie, was zu sehen ist, nicht „Bild von …“».
- Подпись: `<label>Bildunterschrift (sichtbar, optional)</label><input>`.
- «Entfernen»: `<button type="button">` в конце, не красный-только цветом; без подтверждения (есть Undo) либо с отменой через live-region «Bild entfernt. Rückgängig mit Strg+Z».
- Применение: изменения живые (на `change`) + кнопка «Fertig» (закрывает) — или «Übernehmen»; не требовать Apply, иначе SR-пользователь не знает, что изменение сохранилось. После каждого изменения — анонс (см. §5).
- Контраст/размер: контролы ≥24×24 (радио 20px → обернуть в label с min 44px hit-area на coarse); граница полей ≥3:1; фокус 2px outline ≥3:1 и не обрезан `overflow:hidden`.

### 4. Alt-текст: обязательно / декоративное
- По умолчанию alt обязателен: пока поле пусто и не отмечено «Dekoratives Bild», фигура получает видимый индикатор (иконка ⚠ + текст «Alternativtext fehlt», не только цвет), `aria-invalid="true"` на поле, сообщение в `aria-describedby` (`id="alt-err"`, текст: «Bitte beschreiben Sie das Bild oder markieren Sie es als dekorativ.»).
- Чекбокс «Dekoratives Bild (kein Alternativtext)» (`aria-controls` alt-поля): при отметке поле alt `disabled`-подобно (`aria-disabled`, очищается, фокус остаётся), выводится `alt=""` — осознанное решение, а не молчаливое значение по умолчанию. Состояние хранить через `data-decorative` в редакторе; на сервер уходит только `alt=""`. Чтобы различать «ещё не решили» и «декоративное» в повторном редактировании — при загрузке `alt=""` считать «неопределено»→ предупреждать, а ПРИ СОХРАНЕНИИ формы страницы: не блокировать (мягкое предупреждение в `role="alert"`-сводке: «N Bilder ohne Beschreibung» со ссылками-якорями на фигуры), т.к. блокировка = риск потери правки. Решение владельца нужно (R: предупреждение, а не запрет). Нельзя автоподставлять имя файла.
- Серверная сторона: `alt` ≤300 символов (как в плане); не принимать «image», «Bild», имя файла? — опционально эвристика-предупреждение, не отказ.
- Если есть `figcaption`, alt всё равно обязателен (подпись не заменяет, но не дублировать дословно: подсказка).

### 5. Анонсы (aria-live)
- Один постоянный регион, существующий в DOM с загрузки страницы (не создавать «по требованию»): `<div class="sr-only" role="status" aria-live="polite" aria-atomic="true" data-rte-status>` (заменить текущий `[data-rte-status]`, сделать его видимым ТЕКСТОМ + live: загрузка видимая и для SR). Ошибки — отдельный `role="alert"` (ошибка загрузки, ошибка формата).
- Тексты (через `json_script`, не литералы — согласно плану): «Bild wird hochgeladen …» → «Bild eingefügt. Alternativtext fehlt.»; «Größe: M»; «Position: rechts»; «Ausrichtung: zentriert»; «Bild entfernt. Rückgängig mit Strg+Z.»; «Rückgängig» / «Wiederholt»; «Trennlinie eingefügt»; «Link gesetzt». Очищать/перезаписывать после ≈1 с (без накопления). Не дублировать, когда фокус сам объявляет состояние (aria-pressed) — для кнопок-переключателей анонс не нужен.
- 4.1.3: каждое изменение без перемещения фокуса (выравнивание, размер) обязано дать статус.

### 6. Hr, Undo/Redo, выравнивание текста
- Hr: вставляется как `<hr>` (в области — `contenteditable="false"`, фокусируем как фигура, `role="separator"`), у кнопки «Trennlinie einfügen», декоративный → не нужен alt. Удаление Delete.
- Undo/Redo: `document.execCommand('undo'/'redo')` (устарел, но работает в Chromium/Firefox/Safari); следить, что программные DOM-правки (обёртка figure, классы выравнивания) попадают в стек: при прямом `classList.toggle` стек НЕ пополняется (текущий `toggleCenter`) → Ctrl+Z молча не откатит. Требование: свой короткий стек снимков `innerHTML` (≤50) на изменения вне execCommand или делать правки через `execCommand('insertHTML')`; иначе кнопка Undo врёт (4.1.2/3.2.4). Включить в замки стенда: Ctrl+Z после смены размера/позиции/выравнивания.
- Выравнивание: 4 кнопки, `aria-pressed` по текущему блоку; применяется к блоку (`p/h2/h3/h4/li/blockquote`), класс `sf-left|center|right|justify` — смена класса взаимоисключающая. Блокировать `justify` как дефолт-совет (читаемость: 1.4.8 AAA) — оставить, но без пометки «рекомендуется».

### 7. Витрина (рендер)
- Структура: `<figure class="sf-float-right sf-img-md"><img src alt="…" loading="lazy" width height><figcaption>…</figcaption></figure>`. План §3 даёт размер классом на img/figure — выбрать ОДНО место (figure), иначе конфликт; img внутри `max-width:100%; height:auto`.
- `alt`: непустой по умолчанию; `alt=""` только у декоративных. `figcaption` — видимая подпись, не заменяет alt. Без `figcaption` — не рендерить пустой элемент; пустой `figcaption` — убирать на сервере (санитайзер/пост-обработка).
- Float: на `max-width:640px` (и при 400% зума/320 CSS px) float снимается (`float:none; width:100%; margin:1rem 0`), иначе 1.4.10 Reflow и колонка текста 1–2 слова. Отступ вокруг float ≥1rem, `clear` у заголовков (`h2,h3,hr{clear:both}`), контейнер `display:flow-root`. Размеры в `%` от контейнера, `min-width` для 25 %-варианта ≥120px.
- Порядок чтения = порядок DOM: float не меняет, но `figure` с картинкой справа не должна стоять ДО абзаца, к которому относится, если важен порядок — OK при вставке перед абзацем; не использовать `order` в CSS.
- Выравнивание текста: `sf-justify` только на ≥640px (`text-align:justify; hyphens:auto; lang` обязателен), иначе на узких экранах реки. Контраст подписей ≥4.5:1 (не `text-gray-400`), размер ≥ .875rem.
- Ссылки в тексте: подчёркнуты (1.4.1) — как в `.rte-area a`; повторять на витрине.
- Картинка-ссылка: если img внутри `a` без текста — alt обязателен (иначе «пустая ссылка», 2.4.4) — серверная проверка: `a>img[alt=""]` → предупреждение в редакторе.
- Safelist/CSS: классы только через `@layer components`; `prefers-reduced-motion` не нужен (нет анимации).

### 8. Сводка требований по SC
1.1.1 alt обязателен/декоративный осознанно · 1.3.1 toolbar/group/fieldset/legend/figure+figcaption · 1.3.5 — н/п · 1.4.1 выбранное фото/ошибки не только цветом · 1.4.3 текст ≥4.5:1 · 1.4.10 reflow 320/390 (wrap панели, снятие float) · 1.4.11 границы полей/фокус ≥3:1 (исправить `#e5e7eb`/`#a5b4fc`) · 1.4.13 tooltip hover/focus · 2.1.1 всё с клавиатуры (стрелки к фигуре, F2/Enter, Alt+F10) · 2.1.2 нет ловушки (диалог без trap, Escape) · 2.4.3 порядок фокуса, возврат фокуса · 2.4.7/2.4.11/2.4.13 видимый фокус, не перекрыт sticky панелью/нижним листом · 2.5.1 нет жестов · 2.5.3 Label in Name (видимая «Fett» = aria-label «Fett», не «B» с другим именем: у «B» видимый текст «B» → aria-label должен СОДЕРЖАТЬ «B»? безопаснее `aria-label="Fett (B)"`) · 2.5.8 ≥24px (44px на coarse) · 3.2.2 изменения не на фокус · 3.3.1/3.3.3 ошибка alt текстом с исправлением · 3.3.2 метки · 4.1.2 name/role/value (toolbar, aria-pressed, dialog) · 4.1.3 статусы.

### 9. Конкретные правки к плану §3 (предложения)
1. В таблицу добавить строки: «Alt-текст: обязательное поле + чекбокс „dekorativ“» (сейчас «предупреждение при пустом» — слабо), «Фигура фокусируема: tabindex=-1, стрелки/Enter/F2», «Поповер: role=dialog aria-modal=false, радио-группы».
2. Размер: выбрать носителем `figure` (убрать «img или обёртка figure»).
3. В «UI» §3 дописать: `aria-keyshortcuts`, Alt+F10, `role=status` регион, живое состояние `aria-pressed`.
4. Стенд §B4 дополнить проверками: Tab-порядок (1 остановка у панели), стрелки по панели, фокус в фигуру стрелкой, F2 открывает, Escape возвращает фокус, `role=status` текст после смены размера, axe-core на панели/поповере (нет критичных), 390px без горизонтального скролла, фокус не перекрыт sticky/листом, Undo после смены размера/выравнивания.
5. Серверные замки: `figcaption` непустой, `alt` ≤300, `a>img[alt=""]`-предупреждение; `contenteditable/tabindex/aria-*` из редактора санитайзер режет (проверить, что не попадают в сохранённое).

Файлы: /home/user/siteadaptor-platform/templates/catalog/_richtext_editor.html, /home/user/siteadaptor-platform/docs/m21-10-text-pages-hub-plan-2026-11-11.md. Кода не менял.

## 9. Security-ревью плана (security-reviewer, 2026-11-11)

**Принято в план:** системная страница создаётся ТОЛЬКО POST'ом. GET формы показывает несохранённый экземпляр, запись — по «Speichern».

Остальные правки:
- `is_rich` знает все теги белого списка;
- все точки рендера страниц и правовых текстов идут через `sanitize_page`;
- вставка из буфера проходит через `safeCopy` на клиенте;
- `loading` не включаем в белый список: атрибут ставит рендер;
- `alt` обрезается до 300 символов на сервере;
- `fullmatch` для токенов класса;
- лимит тела текста — 200 КБ;
- `legal-page-edit` закрыт правом FLOOR на GET и POST;
- `kind` проверяется по белому списку;
- после снятия блока старые поля `doc_*` в «Recht & Steuern» игнорируются;
- CSS новых классов — только под `.sf-page-body`/`.rich-text`, без `position`/`vw`.

Ревью плана M21.10 (docs/m21-10-text-pages-hub-plan-2026-11-11.md). Сверено с кодом: richtext.py, _richtext_editor.html, content_page_views.py, view_perms.py, templatetags/richtext.py, content_pages.py, menu.py. Кода не правил.

**Как сейчас работает фильтр class (ответ на вопрос 1).**
- nh3 сначала пропускает атрибут по allowlist `PAGE_ALLOWED_ATTRIBUTES`. Класс разрешён только у div/p/figure/h2/h3.
- Затем `_local_image_only` получает ВЕСЬ строковый атрибут целиком и сам режет его по токенам: `split()` → якорный `_PAGE_CLASS_RE` → join. Остаток пуст → атрибут убирается. То есть чужие токены в `class="sf-x evil"` отбрасываются, правильные остаются.
- Схема безопасная: расширение списка не открывает XSS и инъекции CSS, пока нет `style` и токены якорные. JS `safeCopy` повторяет это правило, но он только UX. Граница безопасности — сервер.

**Findings**

1. **HIGH, тихая поломка: `is_rich` не знает про новые теги.**
   - Регулярка (`richtext.py:43`, копия в JS `RICH_RE` на строке 35 шаблона) не содержит `hr` и `figcaption`.
   - Правовой текст или страница, где из нового есть только `<hr>` или `<figcaption>`, считается плоским. `clean_page_input` его не санитайзит, а рендер экранирует. Владелец увидит буквальный `&lt;hr&gt;`.
   - Дополнительно: `clean_page_input` пропускает не-rich значения без чистки. Сейчас это безопасно только потому, что `rich_block` экранирует плоскую ветку через `format_html`.
   - Фикс в план (B3): добавить `hr|figcaption|h4|li|blockquote` в `_RICH_TAG_RE`. Вынести эту регулярку в `PAGE_RULES` и отдавать в JS через `json_script`, как остальное. Замок: каждый разрешённый тег ⇒ `is_rich(f"<{tag}>")`. Замок: `<script>` и `<hr>` в ветке записи.

2. **HIGH, неверная предпосылка плана (§3, «Витрина … затем `|safe`»).**
   - Разные пути рендера используют разные санитайзеры.
   - `storefront_page` → `sanitize_page`. Правовые тексты идут через `{% rich_block mode="page" %}`, где `sanitize_page`. Это верно.
   - Но фильтр `rich_text` и `rich_block` без `mode` зовут УЗКИЙ `sanitize`. Он режет классы, img и h2.
   - План не перечисляет, какие шаблоны получат новые классы. Если `legal`/`impressum`/`agb` где-то вызываются без `mode="page"`, фото и выравнивание молча пропадут. Это класс «обещание без исполнения».
   - В `_page_body.html:29` стоит `{{ body|safe }}`. Безопасность держится только на том, что вьюха всегда передаёт санитайзнутое. Замок (стиль `test_orphan_decorators`): скан шаблонов на `|safe` у переменных страниц, и тест рендера для каждой правовой поверхности (impressum, privacy, withdrawal, agb, shipping, about, cpage) с `<figure class="sf-float-right"><img class="sf-img-md" …>`.
   - Фикс: в B3 перечислить все точки рендера. Добавить замок «все правовые/страничные шаблоны на `mode="page"`».

3. **MEDIUM, nh3-детали, которых нет в плане.**
   - Класс у `img`: добавить `"img": {"src","alt","width","height","class"}` в allowlist и учесть в `_local_image_only`. Сейчас ветка `class` общая для всех тегов, это ок.
   - Токен-regex сделать `fullmatch` (или проверять, что нет `\n`). `re.match("^…$")` пропускает завершающий `\n`. Сейчас токены идут после `split()`, поэтому не эксплуатируется, но хрупко.
   - `loading="lazy"`: чтобы значение было ТОЛЬКО `lazy`, нужна ветка в `attribute_filter`: `tag=="img" and attribute=="loading"` → `value if value=="lazy" else None`. Либо проще: не разрешать `loading` в allowlist вовсе, и пусть рендер ставит атрибут постобработкой. План говорит «ставит рендер, не ввод», так что allowlist не нужен. Не добавлять `loading` в `PAGE_ALLOWED_ATTRIBUTES`.
   - `alt` ≤ 300: обрезка в `attribute_filter` (`value[:300]`), не только в JS.
   - Дублирующиеся классы `sf-img-sm sf-img-full`: токены по отдельности валидны, но взаимоисключающие. Это не безопасность, а вёрстка. Нужен CSS-приоритет (последний в файле) или нормализация: «не более одного класса из группы».
   - `figcaption` внутри `figure` — вложенность nh3 не проверяет. Допустимо, но тест рендера нужен.

4. **MEDIUM, CSS-риски новых классов (§3, «Витрина: CSS»).**
   - Классы сами безопасны (без `style`). Но CSS для `sf-float-*`, `sf-img-full` не должен содержать `position:absolute/fixed`, `width:100vw` и отрицательных margin вне `.sf-page-body`. Иначе пользовательский HTML сможет перекрыть шапку (clickjacking-подобное).
   - Фикс: scoped-правила только под `.sf-page-body` и `.rich-text`, `overflow:hidden`/`display:flow-root` на контейнере (clearfix), на мобильном float снят. Замок: файл с правилами не содержит `position:` и `vw`.

5. **MEDIUM, права (вопрос 2): FLOOR против `website.edit` у загрузки.**
   - Расхождение безопасно: `page_image_upload` с `website.edit` ничего не публикует сам. Картинка попадает на страницу только через текст, а правовой текст пишет FLOOR. Утверждение плана «FLOOR ⊇ website.edit» верно, если у владельца это право есть по построению. Подтвердить замком.
   - Но сотрудник с `website.edit` может залить файлы в `pages/` без ограничения общего объёма. Лимит 60/ч (по `schema:user`) есть, суточного потолка и квоты хранилища нет.
   - В плане есть противоречие: в §4 предлагается «добавить rate-limit 30/ч», а он УЖЕ есть (60/ч, `ratelimit.hit("page-image", …)`). Исправить формулировку: ничего не добавлять, либо осознанно снизить. Не плодить второй ключ `page-img`.
   - Остаточный риск: права `legal-page-edit` в `view_perms.RULES` должны быть записаны как `_r(FLOOR)` и для чтения тоже, иначе сотрудник увидит содержимое правового текста. План скрывает кнопку, но GET самой вьюхи должен отдавать 403. Замок на оба метода. Плюс: у сотрудника в списке «Seiten» поле `state` не раскрывает тексты — норм.
   - Автотекст для «Automatischen Text übernehmen» (E9-подобная кнопка) должен приходить только в ответе вьюхи владельцу, не через общий JSON.

6. **HIGH, GET с побочными эффектами (вопрос 3): ленивое создание на GET.**
   - В §1 Р-4/Р-5 и B1 «при первом „Bearbeiten“» создаётся черновик ContentPage. Если «Bearbeiten» — ссылка (GET на `content-page-edit`/новый `ensure`-роут), то это запись в БД на GET: CSRF-создание, предзагрузка/краулеры браузера создают строки, гонки при двух вкладках (в плане IntegrityError ловится, ок), аудит.
   - Фикс: создание только POST (`require_POST`, CSRF) через `ensure_system_page(slug)`: кнопка «Bearbeiten» у системной строки без страницы — форма-кнопка POST → `get_or_create` → redirect на `content-page-edit`. Права `website.edit`. Для сотрудника без права кнопка скрыта (`can_open`), POST отдаёт 403 через view_perms. GET на несуществующий slug ничего не создаёт.
   - Дополнительно: `pages_list` (GET) не должен звать `ensure_*`; `system_rows(tenant)` — только чтение.

7. **MEDIUM, about_text → HTML (вопрос 4).**
   - В плане сказано «экранированный плоский текст, переносы → `<p>`». Фикс: `django.utils.html.escape` на каждую строку (`linebreaks`/`conditional_escape`), НЕ `mark_safe` на исходник. Двойное экранирование не страшно, но `&amp;` вместо `&` попадёт в редактор — ловить в тесте: `about_text="Tom & Jerry <b>x</b>"` ⇒ тело `<p>Tom &amp; Jerry &lt;b&gt;x&lt;/b&gt;</p>`, после `sanitize_page` без изменений.
   - Результат в любом случае прогонять через `sanitize_page` (второй рубеж) и сохранять только черновиком. План это уже предусматривает.
   - Блок про «правку канвы отключается, пока страница есть»: серверный приёмник инлайн-правки `about_text` всё равно остаётся (siteconfig.py:2535, `inline_edit`). Отключение в UI не защищает от прямого POST; безопасности это не касается, но может молча писать в невидимое поле. Фикс: в приёмнике при наличии страницы `ueber-uns` возвращать 409 с подсказкой, или документировать как «тизер секции главной».
   - `views.py:2930` пишет `about_text` без санитайза (`.strip()`). Плоский текст, который рендерится экранированным; не трогать, но замок «`about_text` с `<script>` на странице экранируется».

8. **MEDIUM, цели меню agb/shipping (вопрос 5).**
   - `agb` гаснет без текста: `legal_text(tenant,"agb")` на каждый рендер меню даёт запросы в БД. Урок ST-8: `resolve_menu` зовётся из шапки, подвала и процессора кабинета. Нужна мемоизация на объекте тенанта + `.exists()` и fail-closed пробник (как для контент-гейта ST-8). Замок на число запросов.
   - Локаль: гейт `agb` должен проверять цепочку локалей (`_locale_chain`) как `legal_text`, иначе в языке без текста пункт ведёт в 404. Использовать тот же `legal_text`, не отдельный запрос.
   - `shipping`: `system_url("versand")` уже требует модуль orders. Дубль `cpage:versand` + `page:shipping`: ведут на один адрес, но дубль в меню виден. Лучше не показывать `page:shipping` в селекте, если есть `cpage:versand` (или наоборот).
   - Цели меню и профиль «Nur Aktionen» (`storefront_profile`, menu.py:393): добавить новые URL-имена в проверку профиля. Если `storefront-shipping` попадёт под `CATALOG_URL_NAMES`, пункт нужно скрыть в профиле. Замок: каждая новая цель реверсится в профиле aktionen.
   - Инвариант «пометка в селекте = `_resolve`» (STU-16d): новые цели должны проходить замок «noch leer» для недостижимых.

9. **MEDIUM, `legal_docs_view` и presence-guard (§1 Р-3).**
   - Перенос записи в `save_legal_doc` ок. Но пока старая форма жива, у `doc_*` два писателя и разные правила (`views.py:1808` `update_or_create` с `clean_page_input`; пустое → delete). Два писателя в переходный период: тот, кто сохраняет «Recht & Steuern» без `doc_*` полей, не должен стирать тексты. Сейчас это держит presence-guard `doc_<kind>_<locale>`; сохранить его до снятия блока.
   - При снятии блока: старый POST с `doc_*` (закешированная страница, старая вкладка) должен игнорироваться, не удалять. Замок: POST без `doc_*` — тексты целы; POST со старыми `doc_*` после B2 — не пишутся (или идут через `save_legal_doc` под FLOOR).
   - `save_legal_doc`: `kind` и `locale` брать из белого списка (`LegalDoc.KIND_CHOICES`, `settings.LANGUAGES`/локали тенанта), не из URL без проверки. 404 на чужой `kind`.
   - Размер: ограничить длину тела (например 200 КБ) в `save_page`/`save_legal_doc`; сейчас лимита в `_form` нет (DoS через гигантский POST/раздутый nh3).

10. **LOW/MEDIUM, прочее.**
    - JS: `alt` из поповера пишется через `setAttribute`, не innerHTML — ок. Подписи кнопок через `json_script` (план верно). Не собирать поповер конкатенацией `innerHTML` с `alt`/`figcaption` (XSS в самой админке: alt приходит с сервера-санитайзера, но подпись/alt могут содержать `"`).
    - `execCommand('insertHTML')` при вставке фото (старый код, строка 161) и вставка из буфера: `safeCopy` вызывается только в `fill`, но НЕ на paste. В contenteditable paste внесёт любой HTML (стили, on*) в DOM админки; `value()` отдаёт `innerHTML` как есть, санитайз только на сервере. Для самого редактора XSS-риск нулевой (on*-атрибуты из буфера браузер не исполняет при paste в contenteditable, но `<img onerror>` из paste исполняется в некоторых браузерах). План §4 утверждает «вставка проходит через `safeCopy`» — в коде этого нет. Фикс: `paste`-обработчик → `preventDefault`, взять `text/html` через `DOMParser`, прогнать `safeCopy`, вставить результат (или `text/plain`). Замок Playwright (в плане B4 есть пейст — оставить с проверкой, что `onerror` не исполняется, а не только что очищено после сохранения).
    - Загрузка: убедиться, что `page_image_upload` не принимает SVG (сигнатура `validate_image` — jpeg/png/webp, ок) и что `src` в `sanitize_page` остаётся строго `MEDIA_URL`. Новые классы не меняют это. Не расширять allowlist `src` на data:/внешние.
    - Удаление системной страницы («вернуть автотекст») = `page_delete` без `require_POST`-различий; сейчас `page_delete` для системных slug допустим. Проверить `menu_references` и что 404-фолбэк `/versand/` после удаления не ломается.
    - X7: новый параметризованный экран `legal-page-edit/<kind>/` и `ensure`-POST: добавить в `view_perms.RULES` (иначе fail-closed middleware ответит 403 всем, включая владельца) — план это знает; добавить замок «каждая вьюха в urls имеет запись» (уже есть класс замков).
    - Документ-рекомендация юристу: правка Impressum/AGB в WYSIWYG позволяет владельцу вставить внешние ссылки `target=_blank` без `rel`; `link_rel` задаёт nh3 — ок.

**Итог:** XSS/CSS-инъекции через расширение allowlist по плану нет, если соблюсти пп. 1–4. Блокеры до кода: п. 6 (POST-only создание системных страниц), п. 1 (`is_rich`), п. 2 (все точки рендера на `sanitize_page`), п. 10-paste (клиентский paste-путь вопреки утверждению плана), п. 8 (запросы меню на каждый рендер).
