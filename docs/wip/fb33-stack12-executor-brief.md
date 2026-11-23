# Бриф исполнителя среза стопки 12 (общая часть; снять после стопки)

Репозиторий siteadaptor-platform (Django 5.2, django-tenants). Работаешь в своём git worktree. Язык общения и
коммитов — русский; идентификатор модели в артефакты не писать. База среза — коммит `51adc24` ветки
`claude/fb33-stack-12-098ih4` (в ней: план, срез K, ядро P0 = M5d-2).

## Первым делом
1. `git fetch origin claude/fb33-stack-12-098ih4 && git merge --ff-only 51adc24`.
2. `uv sync --frozen --extra dev --inexact`; `.mo` polib-ом:
   `uv run python -c "import polib,pathlib; [polib.pofile(str(p)).save_as_mofile(str(p.with_suffix('.mo'))) for p in pathlib.Path('locale').glob('*/LC_MESSAGES/django.po')]"`.
3. Во ВСЕХ pytest/preflight — своя `DB_NAME` (в задании), локально `--reuse-db`. Не править файлы во время своего
   pytest; ждать конца по ` in [0-9.]+s`. Длинным фоновым командам ставить длинный лимит (preflight ≈ 20–40 мин).
   `bash scripts/dev-services.sh`, если Postgres/Redis лежат. Чужие процессы не убивать.

## Прочитать до кода
`CLAUDE.md` §5; `.claude/skills/sa-increment`, `sa-block-editor`, `sa-i18n`, `sa-stand` («Нельзя», «Грабли»);
`docs/fb33-stack12-plan-2026-11-23.md` целиком — §0 (цитаты артбордов — тексты дословно), §3 (карта источников своего
среза), §4 (замки своего среза), §5, §10 (правки ревью — поверх плана), §11 (ответы владельца);
`docs/review-checklist.md`. Ядро: `apps/core/detail_sections.py` (`ContentSource`, `DetailSection.source`,
`ONLY_IF_FILLED`, якоря `# --- <module> ---`), `apps/core/window_parts.py::content_part`,
`templates/tenant/_bw_inhalt.html`, `apps/core/site_schema.py` (`OBJECT_WORDS`, `object_field_label`, `word_kind`,
`object_back`), замки ядра `apps/core/tests/test_fb33_m5d2_core.py` (образец тестов).

## Что знать о ядре (отчёт P0)
- `field` требует `content_nav` = url-имя СПИСКА объектов (запись `nav_registry`); `page` — `content_nav="content-pages"`;
  `setting` — `content_nav` экрана (+ `query`, `sub`); `auto` — без ссылки. Нет записи реестра — ошибка в журнал.
- `shows` — без точки в конце; `%(page)s` в нём — имя страницы. `woher` у `setting`/`auto` — целой фразой с точкой.
- У раздела с presence-гейтом `only_if` обязателен (для полей — `detail_sections.ONLY_IF_FILLED`).
- A10: подпись поля — по имени поля из кода формы, где она там есть (`site_schema.object_field_label`); иначе
  `field_label` + замок «подпись реально есть на странице формы объекта».
- `object_only=True` — часть только на строке одного объекта (тип не трогать, если у типа уже есть окно).
- Объект акции части не получает (так и до среза).

## Правила среза
- Править ТОЛЬКО свои кортежи в `apps/core/detail_sections.py` (между своими якорями модулей), свои тесты, свой блок
  случаев стенда `scripts/fb33_m5d_inhalt_stand.py` (после своего `# --- cases: <срез> ---`), свои записи `.po` — сразу
  ПОСЛЕ записи-якоря своего среза (`msgid "fb33-stack-anchor-<срез>"`) во всех пяти `.po`, с переводами en/tr/ru/uk
  (de — msgstr = msgid). Сверить polib-ом, что дублей пары (msgctxt, msgid) нет; если нужная строка уже есть в `.po` —
  не добавлять вторую.
- НЕ править: `window_parts.py`, `_bw_inhalt.html`, `block_window.py`, `site_schema*.py`, `nav_registry.py`,
  `static/css/app.css` (кроме случая, когда pre-commit хук сам требует пересборку — тогда пересобрать штатно и
  закоммитить; `--no-verify` нельзя), общие эталоны окна (`FB33_M3_REGEN`, `FB33_M32_REGEN`, `FB33_M35C_REGEN` — НЕ
  запускать), доки (`build-log`, `task-catalog`, `project-memory`, `CLAUDE.md`, `skill-feedback`, скиллы). Если ядру не
  хватает возможности — НЕ дописывать ядро, а написать в отчёте, что нужно (координатор сделает).
- Порядок: коммит 1 — замки (красные на базе / strict xfail), коммит 2 — записи реестра + `.po` + стенд; на каждый
  подсрез (например G1a, G1b, G1c) — своя пара коммитов.
- Тесты старых стопок, которые осознанно меняются (план §4, §10 A8), править в коммите кода со ссылкой на план.
- Подписи экранов и полей сверять с кодом grep-ом (карта §3 — гипотеза): url-имя должно существовать в
  `apps/core/nav_registry.py` (`entry_by_url`), иначе — `auto` и строка в отчёте.
- Стенд: сервер `DB_NAME=<своя стенд-БД> uv run python manage.py runserver 0.0.0.0:<свой порт> --settings=config.settings.stand --noreload`
  (остановить по своему PID в конце), прогон `STAND_URL`/порт — по шапке стенда; 1440/390, de/ru, с JS и без. Стенд
  гонять ДО своих записей (красное «до») и после. Плюс `DB_NAME=<своя стенд-БД> uv run python scripts/fb33_m5d_inventory.py`
  — строки своей группы без окна должны уйти.
- Перед отчётом: `DB_NAME=<своя> uv run python scripts/preflight.py`. Ожидаемо красные эталоны из прогноза плана §5 —
  списком в отчёте (их пересъёмет координатор); прочее зелёное. Известные нестабильные при параллельном прогоне:
  `test_migration_state`, `test_async_signup`, `test_admin_dashboard::test_dashboard_callback_counts` — перепроверить
  отдельно.
- Каждый законченный коммит СРАЗУ пушить в свою ветку (в задании). Сообщения `FB-33 <ID>: …`, в конце:
  `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>` и
  `Claude-Session: https://claude.ai/code/session_01L61ZS24HP4BknhAYeFZoy5`.

## Отчёт
Коммиты (хеши); таблица «ключ → kind, content_nav, тексты»; что было красным до кода; новые msgid; итог preflight
(числа); итог стенда и инвентаря (числа, команда); красные эталоны против прогноза; отступления от плана и почему;
чего не хватило в ядре; что НЕ проверено; находки для журнала. «Измерено / не задевает» — только с командой и выводом.
