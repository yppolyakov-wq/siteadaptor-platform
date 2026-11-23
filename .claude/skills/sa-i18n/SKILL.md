---
name: sa-i18n
description: Переводы siteadaptor-platform (5 языков de/en/tr/ru/uk) — каталоги locale/*/django.po и .mo, язык кабинета и витрины, оверлеи контента, переводы списков по ключу, демо-словари, сторожа и гейты i18n. Грузить ДО кода при любой новой строке интерфейса (trans, gettext, label, choices), правке .po, i18n_input, i18n_cabinet, i18n_seq, i18n_json, block_i18n, form_spec labels_i18n, demo_i18n, scripts/i18n_*.py и при красном i18n-гейте CI.
metadata:
  origin: project
---

# Переводы: каталоги `.po`, язык кабинета, оверлеи контента

Все грабли — `docs/pitfalls.md` §4; единые точки — `docs/project-memory.md` §3. Здесь — что
звать и на чём уже ошибались. Дата у грабли — последнее срабатывание.

## Когда грузить
До плана и до кода любого среза, который добавляет или меняет видимую строку (шаблон, форма,
реестр, письмо, PDF), трогает `.po`, оверлеи переводов контента или демо-словари.

## Модель в пяти строках
- Базовый msgid хрома — **немецкий**; языки — de/en/tr/ru/uk; запись в `.po` всех пяти
  каталогов — в том же коммите, что и строка.
- Три разных языка: **кабинета** (сессия, `CABINET_LANGUAGES`), **витрины** (кука) и
  **переводов контента** (оверлеи бизнеса). Не смешивать.
- База контента редактора — `settings.LANGUAGE_CODE`, не `Tenant.default_locale`.
- Переводится ПОКАЗ, не запись: снимки заказа, ключи учёта, value `<option>`, ключи фасетов и
  ответов анкеты остаются на базовом языке; в реестрах переводится только `label`.
- `.mo` собирает образ (Dockerfile, msgfmt по ВСЕМ `locale/*/django.po`); локально gettext
  нет — `.mo` собирать polib.

## Единые точки
**Язык кабинета:** `apps/core/i18n_cabinet.py::resolve_cabinet_locale, set_cabinet_locale,
browser_language, cabinet_language_codes, CABINET_PREFIXES`; список языков —
`config/settings/base.py::CABINET_LANGUAGES`. Язык писем — `apps/notifications/services.py::email_locale`.

**Ввод переводов в формах кабинета:** `apps/core/i18n_input.py::extra_locales, form_locales,
i18n_inputs_for, apply_i18n_overlay, apply_seq_overlay, i18n_form_groups, save_row_translations,
DynamicI18nFormMixin, OverlayI18nFormMixin, RICH_OVERLAY_FIELDS`; переключатель языка ввода —
`templates/tenant/_i18n_switch.html` (единственный партиал); кнопка «Übersetzen» —
`templates/tenant/_i18n_translate_js.html` (единственный клиент, второй копии JS не заводить).

**Три слоя оверлеев (показ):**
- скаляры — `apps/core/models.py::I18nMixin, resolve_overlay` (метод `get_overlay`);
- плоские списки — `apps/core/i18n_seq.py::overlay_seq`;
- вложенный JSON — `apps/core/i18n_json.py::overlay_json, build_overlay, collect_strings,
  SKIP_KEYS` (служебные ключи — в `SKIP_KEYS`).

**site_config:** что переводимо и разбор ввода — `apps/tenants/siteconfig.py::TRANSLATABLE_KEYS,
NON_TRANSLATABLE_FIELDS, split_translation, localize, realign_block_overlays,
realign_list_overlays`.

**Писатели переводов (по одному на данные):**
- тексты блока в окне «Seitenaufbau» — `apps/core/block_i18n.py::take, drop, apply, check,
  conflict, TEXT_FIELDS` (Студия пишет своим `split_translation` — не переводить на модуль);
- поля формы заявки и корзины по ключу (`labels_i18n`, `label_i18n`, `options_i18n`,
  `event_types_i18n`) — `apps/core/form_spec.py::put, view, event_type_choices,
  absorb_legacy_event_i18n, set_event_translations`; перенос старых позиционных —
  `apps/core/management/commands/form_i18n_realign.py` (шаг `scripts/deploy.sh`);
- общий FAQ и `i18n[*].faq` — `apps/core/faq_content.py::put, remap_overlay, apply_explicit`.

**Демо:** обход перевода — `apps/tenants/demo_i18n.py::t, overlay_config, PROPER_NAMES`;
словари `apps/tenants/demo_i18n_ru.json` и соседи; замер покрытия — `scripts/demo_i18n_gap.py`.

**Сторожа:** `scripts/i18n_quickcheck.py` (msgid без записи в `.po`, локальный гейт),
`scripts/i18n_untranslated.py` (строка без пути перевода; долг — в
`locale/i18n-untranslated-baseline.json`), `scripts/i18n_gap.py` (гейт CI, нужен xgettext),
`scripts/i18n_status.py` (сводка каталогов), `.claude/hooks/i18n-watch.sh` (после правки
файла), `.githooks/pre-commit` (ставит `scripts/install-git-hooks.sh`).

## Нельзя
- Сохранять `.po` через `polib.save()` — polib только читает; записи дописывать текстом в
  конец файла, править и удалять — текстовой заменой.
- Сортировать `demo_i18n_<loc>.json` и писать в них identity-записи (S→S); имена и топонимы —
  в `PROPER_NAMES`.
- Читать или писать перевод списка по позиции — только по ключу или id элемента.
- `gettext` в модульных константах (только `gettext_lazy`), `gettext` внутри f-строки,
  псевдонимы `_t`/`_l`, `_(переменная)` в цикле.
- Брать язык кабинета через `get_language_from_request` (читает куку витрины).
- Заводить второй писатель переводов рядом с `block_i18n`, `form_spec`, `faq_content`.
- Обходить замок `apps/core/tests/test_lang_switch.py`: свой механизм перевода — запись в
  `_OWN_MECHANISM`.
- Переводить DATEV-экспорт, `USt-IdNr.`, `Steuernummer`, § 19 UStG; у ваучеров переводов нет.
- Немецкий литерал в сообщении журнала (`log.warning`) — писать по-английски.
- Дописывать в `locale/i18n-untranslated-baseline.json` ради зелёного гейта без решения
  владельца.

## Грабли
- «Строка уже есть в `.po`» — проверять парой (msgctxt, msgid) polib-ом: «Wie anordnen» есть
  только с `msgctxt "block window tab"`, `{% trans %}` без контекста — другая запись, локально
  не ловится (CI `i18n_gap`) · посл. 2026-11-22.
Каталоги `.po` и `.mo`:
- `polib.save()` переформатирует весь каталог (дифф в десятки тысяч строк); испорченное уже в
  индексе откатывать `git restore --source=HEAD --staged --worktree` · посл. 2026-11-13.
- Параллельные срезы добавляют один msgid — на верхушке стопки дуп-чек (msgctxt, msgid) polib
  во всех пяти `.po`; дубли бывают и в многострочной форме · посл. 2026-11-20.
- Якорь среза стоит в конце `.po`: вставку частями вести от конца уже вставленных записей
  · посл. 2026-11-20.
- Переименование msgid — от исходника (`grep -rn` по `apps/ templates/`), потом `.po`;
  sed по каталогам пропускает вторую строку-источник · посл. 2026-10-26.
- Запись с `\n` в msgid самописный дописыватель ломает — такие через `polib.POEntry`
  · посл. 2026-10-25.
- Протухшие `.mo` (старый снапшот, нет gettext): тесты «немецкие», а эталон не на немецком
  ловит непереведённую строку — перед пересъёмкой собрать `.mo` polib · посл. 2026-11-19.
- Литеральный `%` в msgid делает строку непереводимой; `_("…%…")` в аргументе шаблонного тега
  печатает «%%» — брать через `{% trans … as var %}` · посл. 2026-11-03.

Гейты и сторожа:
- `i18n_quickcheck.py` без аргументов видит только незакоммиченное: перед пушем стопки гнать
  по `git diff --name-only origin/main...HEAD` · посл. 2026-11-06.
- Он же не видит untracked-файлы и `.txt`-шаблоны писем (`git add` до проверки); по
  `test_fb33_m3_window.py` даёт ложное «нет в .po» (f-строка) · посл. 2026-11-20.
- `i18n_gap` в CI строже: видит `_()` в шаблонах и в `{% include … with %}` — такие msgid
  сверять с `.po` вручную · посл. 2026-09-03.
- `i18n_untranslated` принимает пару строк в кортеже («stays», «StayUnit») за подпись — ссылку
  на модель писать «app.Model» · посл. 2026-11-20.
- Замок «нет старых имён» по `_("…")`/msgstr — только по границам слова и по записям реестра
  · посл. 2026-11-20.
- Подписи полей ModelForm без `Meta.labels` — машинные имена, не переводятся и не
  извлекаются · посл. 2026-08-27.

Тексты и омонимы:
- Короткая строка с двумя смыслами — `msgctxt` («Fragen» в en уже «Ask»; «Vor Ort»); кнопка
  «OK» — «OK» на всех языках · посл. 2026-11-20.
- Машинный перевод: строки ≤ 4 символов, финансовые термины («Net», «Quote», «Draft») и
  плюралы ru/uk (4 формы) вычитывать вручную · посл. 2026-11-09.
- «Обёрнуто ≠ переведено»: msgid без записи в `.po` молча идёт по-немецки · посл. 2026-07-31.

Языки и оверлеи:
- Язык кабинета у GET окна и у POST правки может отличаться — «стандартную подпись» сравнивать
  на любом языке платформы · посл. 2026-11-20.
- Перевод списка по позиции едет при перестановке, удалении и вставке; два одинаковых
  вопроса получают один перевод · посл. 2026-11-20.
- Правка немецкого текста снимает перевод поля (`block_i18n.py::take`) — замок в
  `apps/core/tests/test_fb27_r3_width.py`; у подписей полей формы (`form_spec` `labels_i18n`)
  такой логики НЕТ — кто меняет подпись программно (пресет), заменяет и переводы
  · посл. 2026-11-22.
- Подсказка «без перевода будет немецкий» неверна для системных полей: показывать то, что
  покажет сайт (`translation.override(loc)`) · посл. 2026-11-20.
- `TenantFactory` по умолчанию de+en; «один язык» в тесте — `enabled_locales=["de"]`
  · посл. 2026-11-20.
- Оверлей JSON мерджится позиционно: индексы — из нормализованного списка, порядок
  «нормализация → перевод → фильтр» · посл. 2026-08-14.
- `gettext_lazy` в данных для JSON — сериализовать `DjangoJSONEncoder`; письма, собираемые в
  Python, — под `translation.override(email_locale())` · посл. 2026-08-27.
- Форма с оверлеями получает тенанта явно (`form.init_overlay_i18n(tenant)`), не патчем
  `connection` · посл. 2026-10-31.

## Что гейтить
- `uv run python scripts/preflight.py` (шаг i18n = quickcheck + `i18n_untranslated.py --check`).
- Перед пушем стопки: `uv run python scripts/i18n_quickcheck.py $(git diff --name-only
  origin/main...HEAD | grep -E '\.(py|html)$')`.
- Только CI: `msgfmt --check-format` по всем `.po`, `scripts/i18n_gap.py`,
  `scripts/i18n_untranslated.py --check` — локально первые два не запускаются.
- Замки: `apps/core/tests/test_lang_switch.py`, `apps/tenants/tests/test_demo_kits.py`
  (identity-записи словарей); правка шаблонов — `apps/core/tests/test_template_comments.py`.
- Стенды переводов: `scripts/fb33_m2i5b_i18n_stand.py`, `scripts/fb33_m35c_i18n_stand.py`.
- «Не переведено» на скриншоте: сначала авто-перевод Chrome и язык кабинета, потом `.po`.

## Агенты ECC
`django-reviewer` — каждый срез; `silent-failure-hunter` — писатели переводов и конфликты
черновика; `a11y-architect` — новые поля перевода (подпись называет поле, цитата исходника с
`lang`); `e2e-runner` — переключатель языка и кнопка «Übersetzen»; `security-reviewer` —
ввод переводов владельцем и письма.
