# FB-27 «Seiten» — список страниц и оболочка страницы

Дата: 2026-11-13. План составлен агентом `planner`. Основание — решения владельца в
`fb27-website-pages-ia-plan-2026-11-11.md`: «Один список без разделителей (правовые —
подписью „Rechtstext“); макеты S1–S3 приняты, у страницы вкладки Text · Blöcke ·
Suchmaschinen»; «С телефона — полное»; «Entfernen — с подтверждением»; инкремент 27b —
«карточками на телефоне; действия в меню „⋯“, без красных кнопок в строке».

Макеты: `docs/design/website-seiten-2026-11-11/S1_Seiten.dc.html`, `S2_Seite.dc.html`,
`S3_Mobil.dc.html`.

- **S1 (1440)** — одна таблица: Titel (под названием адрес, у правовых « · Rechtstext»),
  Status, Verlinkt in, Blöcke, ⋯. Статусы: Eigener Text / Nur Versandarten / Veröffentlicht /
  Entwurf / Automatisch erstellt / «Ausgeblendet – Text fehlt». «nicht verlinkt · ins Menü».
  В «⋯»: Ansehen · Blöcke · Im Menü verlinken · Zurücksetzen/Löschen (с вопросом);
  «Rechtstexte können nicht gelöscht werden».
- **S2 (1440)** — шапка «← Alle Seiten», h1, адрес · место ссылки, «Seite ansehen»; вкладки
  Text | Blöcke | Suchmaschinen; слева «Blöcke dieser Seite» (строка «Ihr Text», блоки с
  ↑ ↓ 👁, «+ Block hinzufügen», ссылка «Seitenaufbau › Textseiten»), справа «Vorschau ·
  gespeicherter Stand».
- **S3 (390)** — карточки: название, адрес · место, бейдж; «⋯» 44 px; «+ Neue Seite» 44 px.

## 1. Что есть в коде

- Список — `content_page_views.pages_list` рисует строки `content_pages.all_rows`
  (системные, правовые, свои; сначала со ссылкой, потом по названию).
- Редактор `_form` — одна форма (title/slug/body/is_published/Versand); удаление — POST
  `page_delete`. У правовых — свой редактор `legal_page_edit` (`legal.save_legal_doc`).
- Блоки страницы правятся только в «Seitenaufbau» (`text`, `text@versand`,
  `text@seite:<slug>`; черновик `aufbau_draft`).
- SEO своей страницы не хранится: title — из названия, description — из текста; `robots`
  в `_base.html` нет.

| Элемент | Сейчас | Цель S1–S3 |
|---|---|---|
| Колонки | Titel · Art · Status · Sichtbar | Titel (+адрес, «Rechtstext») · Status · Verlinkt in · Blöcke · ⋯ |
| Действия строки | «Bearbeiten» + красные Löschen/Zurücksetzen | меню «⋯» |
| Телефон | таблица с горизонтальной прокруткой | карточки |
| Вкладки страницы | нет | `?tab=text|bloecke|suche` |
| Удаление | кнопка внизу формы | «Löschen…» в «⋯» → подтверждение |

## 2. Решения

| № | Вопрос | Решение |
|---|---|---|
| P1 | Правовые тексты | Строки общего списка с подписью «Rechtstext». Открывают существующий редактор в той же оболочке, только с вкладкой Text (блоков у правовых нет); в «⋯» — только Ansehen. Второго писателя не заводим. |
| P2 | Вкладка «Blöcke» | Строки — `site_schema.blocks_for` по черновику; ↑ ↓ 👁 — обычные формы на `site-schema` со скрытым `zurueck=seiten`, после действия — возврат на вкладку (адрес по имени маршрута, не сырой `next`). Полоса черновика «Speichern/Verwerfen» — та же, что в «Seitenaufbau» (в S2 её нет — следует из решения «Черновик + Speichern»). «+ Block» и «Textseiten» — ссылки в «Seitenaufbau». Превью — сохранённое состояние, на телефоне свёрнуто. |
| P3 | «Suchmaschinen» | title, description, `noindex`. Хранение без миграции: `site_config["seo"]["pages"][<хост>]` (`info`, `versand`, `seite:<slug>` — как у блоков); точечная запись под блокировкой строки; ключ переезжает и удаляется вместе с блоками страницы. Витрина выводит `robots`. |
| P4 | Телефон | До `md` — список карточек, от `md` — таблица; обе из одних строк и одного меню. «⋯» — `<details>`, работает без JS. «Löschen…/Zurücksetzen…» ведут на шаг подтверждения в редакторе. Публикация — галочка на вкладке Text. Перестановки строк в макетах нет — не делаем. «Im Menü verlinken» — ссылка на экран меню. |
| P5 | Адреса | Не меняются (`content-pages`, `content-page-edit`, `content-page-system`, `legal-page-edit`) + `?tab=`; неизвестная вкладка → Text. Меню кабинета не трогаем. |
| P6 | Системные страницы | «Über uns» и «Versand» — как сейчас; блоки и SEO работают и без записи страницы (хосты `info`/`versand`). |

Вопросы владельцу (идём по рекомендации, пока не сказано иное): В-1 хранить SEO страницы
в настройках сайта без миграции (да); В-2 показывать на вкладке «Blöcke» полосу
«Speichern/Verwerfen» (да); В-3 вкладка «Suchmaschinen» у правовых текстов (нет).

Предположения (в макетах нет): вид вкладок и блоков страницы на 390 px — вкладки в одну
строку, превью свёрнуто; пункты «⋯» у системной страницы без записи и у AGB без текста.

## 3. Срезы

- **S-a — список по S1/S3** (только рендер): подпись «Rechtstext», сводка блоков (без запросов
  на строку), статус «Veröffentlicht», «Verlinkt in», меню «⋯», карточки, без красных кнопок.
  Осознанно переписать: `test_m21_10_text_pages_hub::test_hub_shows_all_pages_in_one_list`,
  `test_m21_6_content_pages::test_legal_pages_listed_with_state_and_link_to_legal_tab`.
- **S-b — оболочка вкладок + удаление с подтверждением** (`?loeschen=1`; кнопка удаления из
  формы уходит; правовая форма — в оболочке с одной вкладкой).
- **S-c — вкладка «Blöcke»** (`zurueck=seiten` в `site_schema_view`, строки, полоса черновика,
  превью).
- **S-d — «Suchmaschinen»** (узел SEO, перенос ключа, `robots` на витрине, sitemap).

## 4. Замки (до кода)

- в списке нет красных кнопок; ровно одно меню «Mehr zu …» на строку в каждом виде;
- карточки и таблица показывают одни и те же строки;
- у правовых — подпись «Rechtstext», удаления нет;
- сводка блоков не добавляет запросов на строку;
- неизвестная вкладка → Text; у правового редактора только Text;
- удаление требует шага подтверждения; GET ничего не пишет;
- возврат из «Seitenaufbau» — только по имени маршрута (мусор и `//host` игнорируются);
- вкладка «Blöcke» без права правки сайта — только чтение;
- узел SEO отклоняет неизвестные хосты и длинные значения; смена адреса переносит ключ,
  удаление — убирает; `noindex` выводит `robots`;
- замки прав экранов страниц остаются зелёными.

## 5. Риски и откат

- Двойная разметка списка (карточки + таблица): полей ввода в ней нет, W0 не задет.
- Новый писатель `site_config` для SEO — только точечная запись под блокировкой.
- Откат каждого среза — revert одного коммита; миграций нет.

## 6. ECC-прогоны

- До кода: `django-patterns`, `django-tdd`, `django-security`, `accessibility`, `e2e-testing`,
  `seo` (S-d).
- `django-reviewer` — каждый срез; `a11y-architect` — S-a, S-b (меню «⋯», вкладки, 44 px);
  `security-reviewer` — S-b (удаление), S-c (возврат, права), S-d (ввод); `seo-specialist` —
  S-d; `silent-failure-hunter` — S-d (запись в `site_config`).
- Стенд Playwright 1440/390, de/ru, без JS — на каждом срезе.
