---
name: sa-block-editor
description: Редактор страниц siteadaptor-platform (FB-27/FB-31/FB-33) — экран «Seitenaufbau», черновик страницы, окно блока и его вкладки (Wie anordnen, Karte, Texte, Felder, Seite, Vorschau), блоки и виды, FAQ, переводы текстов блока, Студия. Грузить ДО кода при любой правке aufbau_draft, block_*, form_spec, faq_content, object_faq, site_schema, шаблонов _bw_*, static/js/aufbau.js, их эталонов и стендов.
metadata:
  origin: project
---

# Редактор блоков: «Seitenaufbau», окно блока, Студия

Полная модель — `docs/fb33-editor-model-2026-11-19.md`; очередь и правила работы —
`docs/fb33-next-2026-11-20.md`; все единые точки — `docs/project-memory.md` §3. Здесь — что
звать и на чём уже ошибались. Дата у грабли — последнее срабатывание.

## Когда грузить
До плана и до кода любого среза FB-33 и любой правки редактора страниц, окна блока, Студии.

## Модель в пяти строках
- Правка идёт в **черновик страницы в сессии** (`apps/core/aufbau_draft.py`), в `site_config`
  пишет только «Speichern» (`aufbau_draft.py::commit`) под блокировкой. Показ черновика —
  `aufbau_draft.py::overlay`.
- **Окно блока** — `<dialog>`; без JS те же части открываются колонкой по ссылкам `?tab=`.
  Каждая часть окна — партиал `templates/tenant/_bw_fields.html` и соседи `_bw_<часть>.html`.
- Студия правит только содержимое; ⚙ Студии открывает то же окно (`apps/core/window_links.py`).
- Всё, что блок умеет, описано реестрами; экран строится из них, второго списка нет.
- Каждый срез: замки → код → эталоны → стенд 1440/390, de/ru, с JS и без.

## Единые точки
**Писатели (по одному на данные; рядом второй не заводить):**
- поля форм заявки и корзины, `site_config["form_fields"]` — `apps/core/form_spec.py::put`
  (разбор ввода `parse_post`, модель вкладки `panel`, показ `view`); свои вопросы и ответы —
  `apps/core/form_answers.py`;
- общий FAQ и `i18n[*].faq` — `apps/core/faq_content.py::put` (переводы списка — `remap_overlay`);
- свои вопросы объекта — `apps/core/object_faq.py::put, save_from_form, window_op, commit`;
- переводы текстов блока — `apps/core/block_i18n.py::take, drop, apply, check`;
- SEO страницы — `apps/core/content_pages.py::put_page_seo`;
- места баннера «Wo zeigen» — `apps/core/window_banner.py`.

**Черновик:** части вне сохранённого состояния (form, faq, ofaq, show_on) — одна таблица
`apps/core/aufbau_draft.py::SIDE_PARTS`; новый срез дописывает строку туда. Конфликт FAQ —
`aufbau_draft.py::faq_conflict`; форма — `form_state`.

**Окно:** вкладки и части — `apps/core/block_window.py::parts, tabs, apply_form, goto_tab,
default_op, field_meta`; части-формы — `APPLY_FORM_PARTS`. Порядок декораторов:
`fill_options` → `apps/core/block_views.py::decorate` → `apps/core/block_card.py::decorate` →
`block_window.py::tabs`. Части FAQ и плашек — `apps/core/window_parts.py`; строка «Seite» —
`apps/core/page_window.py`; закреплённые правовые кнопки — `apps/core/legal_buttons.py`.

**Реестры:**
- семьи и библиотека блоков — `apps/core/block_catalog.py` (`INACTIVE_FIELDS`, `active_data` —
  любой читатель текста блока берёт `active_data`);
- виды FAQ — `apps/core/faq_views.py` (единственный список);
- формы карточки — `apps/core/card_forms.py::card_applies, forms_for_view` (вид побеждает);
- плашки «Schnellzugriff» — `apps/core/hero_tiles.py::QUICK_LINK_TILES`;
- неподвижные строки и разделы «на месте» — `apps/core/detail_parts.py::PINNED,
  flow_section_keys`;
- встраиваемость страницы и адрес окна формы — `apps/core/site_schema.py::page_embeddable,
  form_window_url`.

## Нельзя
- Писать `site_config` мимо писателя или мимо черновика; заводить второй список видов,
  форм, полей, плашек рядом с реестром (плитки строятся из уже заполненных пунктов).
- Импортировать `siteconfig` в `card_forms` и `faq_views` (ast-замки).
- Выдавать постоянные номера `q<n>` в черновике — только в `commit` под блокировкой.
- Читать перевод списка по позиции — только по ключу или id (перестановка сдвигает).
- Возвращать Студии правку разделов, шаблонов и раскладки; восстанавливать «Seitenvorlagen».
- Давать `aria-hidden` фокусируемому элементу, в том числе sr-only «Übernehmen».
- Править подпись закреплённой кнопки § 312j («Zahlungspflichtig bestellen»).
- Коммитить общие эталоны окна и `static/css/app.css` из параллельного среза.

## Грабли
Черновик и конфликты:
- Новый ключ в сохранённом состоянии меняет отпечаток у всех открытых черновиков — фильтр в
  `_base_fingerprint` и `_settle` · посл. 2026-11-20.
- Конфликт переводов проверять ДО записи пунктов; сверку «изменено в другом месте» повторять
  под блокировкой объекта · посл. 2026-11-21.
- Удалённый блок обязан снять свои переводы (`block_i18n.py::drop`), иначе конфликт видит
  ушедшие блоки · посл. 2026-11-21.
- Форма объекта на `ModelForm.save()` пишет ВСЕ столбцы и затирает свои вопросы FAQ — писать
  через `object_faq` после `lock_fresh` · посл. 2026-11-20.
- «Пустая» настройка, которая всё же действует: отличать «не задано» от «задано пусто»
  · посл. 2026-11-19.
- Блок `faq_ref` с `source=object` — не общий FAQ; нет ключа — общий · посл. 2026-11-20.
- Блоки хоста по умолчанию (`apps/core/not_found_page.py::DEFAULT_ROWS`) — с постоянными id и
  без хранимого текста, иначе черновик «меняется» сам; умолчание считает
  `apps/tenants/siteconfig.py::page_rows`, пустой ключ хранится (`KEEP_EMPTY_HOSTS`)
  · посл. 2026-11-22.
- `apps/core/hero_tiles.py::QUICK_LINK_SETS` — наборы ПЕРЕНОСА (на них замки и эталон); новый
  набор плиток — производным кортежем `BLOCK_LINK_SETS` · посл. 2026-11-22.
- «Не задано» и «задано пусто» различимы, только если писатель хранит пустой ключ:
  `apps/core/form_spec.py::put` пустую запись снимает · посл. 2026-11-22.

Окно без JS и с JS (`static/js/aufbau.js`):
- Кнопка с `form="…"` вне формы тоже становится её кнопкой по умолчанию; первая кнопка формы
  не `op=update` → запись в `_DEFAULT_SUBMIT` · посл. 2026-11-20.
- Окно со скриптами прячет «Übernehmen» и пишет правку по `change`; программное заполнение
  поля должно слать `change` · посл. 2026-11-21.
- Радио-плитки применяются сами только в формах из `FORMS`; `hideApply` прячет ПЕРВУЮ
  `button[value=update]` · посл. 2026-11-20.
- Кнопка «нажатое состояние» не шлёт операцию-тумблер (повторный клик снимает выбор)
  · посл. 2026-11-20.
- `autofocus` не срабатывает при якоре в адресе; `hidden` и display-класс Tailwind на одном
  элементе конфликтуют · посл. 2026-11-21.
- Ключ секции канвы (`data-sf-section`) ≠ ref строки схемы: точное совпадение ref раньше
  снятия префикса · посл. 2026-11-21.
- Студия: сервер учится понимать новое ДО шаблона (иначе старая панель шлёт снятые ключи)
  · посл. 2026-11-21.
- Правило `[data-schema-panel] :is(…)` и `.ui-bwin :is(…)` (0,2,0) сильнее утилиты `min-h-[…]`
  у элемента: высоту целей окна задаёт `static/src/app.css`, не класс в шаблоне
  · посл. 2026-11-22.
- «Vorschau»: кадр без `allow-scripts`, `aria-hidden`, без `title`; прокрутка — только
  `contentWindow.scrollTo`; фокус из кадра — на кнопку · посл. 2026-11-21.

Шаблоны, переводы, эталоны:
- Тег шаблона на своей строке и вынос куска в партиал сдвигают пробелы → падают эталоны;
  пересъёмка — осознанно, со сверкой списка изменившихся случаев · посл. 2026-11-21.
- Подписи в модульных константах — только `gettext_lazy`; правка немецкого текста снимает
  его перевод · посл. 2026-11-21.
- `TenantFactory` по умолчанию de+en; подсказка «без перевода — немецкий» верна не везде
  · посл. 2026-11-20.
- Поля перевода называют поле («Überschrift», «Frage N»), цитата исходника — с `lang`
  · посл. 2026-11-21.

Стенд:
- Клик по кнопке формы панели ≠ переход; кабинет на стенде открывается по-английски — язык
  задавать явно; ждать только конечные анимации; переключатель вкладки уходит через 350 мс
  · посл. 2026-11-21.

## Что гейтить
- `uv run python scripts/preflight.py` (правка `apps/core` тянет импортёров сама).
- Эталоны окна: `apps/core/tests/test_fb33_m3_window_before.py` (пересъёмка `FB33_M3_REGEN=1`,
  только на верхушке стопки и только со свежими `.mo`).
- Замки «один писатель»: `apps/core/tests/test_fb33_m35b_faq_writers.py`,
  `apps/core/tests/test_fb33_m2b2b_object_faq.py`, `apps/core/tests/test_fb33_m2i5_before.py`.
- Стенд окна — `scripts/fb33_m3_window_stand.py` (инструкция в шапке; тенант `ptx` —
  `scripts/text_pages_stand.py`); обход владельца — `scripts/fb33_m3_9_owner_stand.py`.

## Агенты ECC
`django-reviewer` — каждый срез; `a11y-architect` — новая часть окна или новый элемент;
`e2e-runner` — правка `aufbau.js` и вёрстки окна; `silent-failure-hunter` — писатели и
конфликты черновика; `security-reviewer` — ввод полей форм, свои вопросы, письма.
