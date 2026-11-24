---
name: sa-stand
description: Playwright-стенды siteadaptor-platform — каркас standlib (запуск Chromium, вход, Report, размеры, языки, режим без JS), как писать и гонять scripts/*_stand.py, приёмка вёрстки 1440/390 на de и ru. Грузить ДО кода при любой правке static/js, вёрстки кабинета или витрины, при новом стенде, правке старого и при приёмке экрана в браузере.
metadata:
  origin: project
---

# Стенды: каркас `standlib`, запуск, приёмка в браузере

Стенд — скрипт Python-Playwright, который ходит по живому серверу стенда и печатает «N ✓, M ✗».
В CI стендов нет (там нет браузера) — это локальный гейт JS и вёрстки. Источники:
`docs/pitfalls.md` §5 и `docs/fb33-next-2026-11-20.md` §4. Дата у грабли — последнее срабатывание.

## Когда грузить
До кода — при правке `static/js/aufbau.js`, `static/js/cabinet.js` и любого другого скрипта,
вёрстки экрана кабинета или витрины; при новом `scripts/*_stand.py` и правке старого; перед
приёмкой экрана (1440 и 390, de и ru, с JS и без).

## Порядок работы
1. Тенант стенда `ptx` (владелец `owner@ptx.test`) — один раз:
   `uv run python scripts/text_pages_stand.py --setup` (заявки для «Felder» — `--jobs`).
2. Сервер: `python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand --noreload`
   (настройки стенда — `config/settings/stand.py`: без debug-toolbar, медиа с диска).
3. Стенд: `uv run --no-project --with playwright python scripts/<имя>_stand.py <папка>`;
   другой порт — `STAND_URL=http://ptx.siteadaptor.de:<порт>`.
4. **Стенд гонять ДО правки и после**: красное «до» отделяет старый дефект от своего.
5. После правки каркаса — `uv run --no-project --with playwright python scripts/standlib.py
   --selftest` (без сервера и БД; итог «standlib selftest: N ✓, 0 ✗»).

## Единые точки
Каркас — `scripts/standlib.py` (пример нового стенда на 20 строк — в его докстринге):
- счёт и выход — `scripts/standlib.py::Report` (`check` с подписью дефекта `sigs` и кодом
  `code`, `note`, `summary`, `finish`: есть ✗ → код 1);
- что обходить — `scripts/standlib.py::SIZES, LANGS, JS_MODES, matrix` (1440×900 и 390×844;
  de и ru; сначала без JS);
- браузер и страница — `scripts/standlib.py::launch, open_page` (Chromium из
  `/opt/pw-browsers/chromium`; размер, `java_script_enabled`, язык — `locale` и кука
  `django_language`; ошибки страницы — в `page.js_errors`);
- шаги — `scripts/standlib.py::login, settle, overflow, shot`;
- доступность (T-14.5) — `scripts/standlib.py::a11y_check, small_targets, hidden_focusable,
  unnamed_controls, low_contrast, focus_returns, contrast_ratio`: `a11y_check(rep, page, tag,
  scope=…, minimum=24 | 44)` пишет коды `a11y-target`, `a11y-hidden-focus`, `a11y-name`,
  `a11y-contrast`; витрина — 24, кабинет и окно — 44; «не измерено» — наблюдение, не ✗;
- адрес и учётка — `scripts/standlib.py::BASE_URL, EMAIL, PASSWORD` (адрес — из `STAND_URL`).

Рядом:
- тенант `ptx` — `scripts/text_pages_stand.py::SETUP, JOBS` (единственный установщик);
- обход владельца с проверками целей касания и «немецкое в ru» —
  `scripts/fb33_m3_9_owner_stand.py::targets, german, check_common` (демо-киты, своя стенд-БД
  `DB_NAME=…_stand`);
- окно блока — `scripts/fb33_m3_window_stand.py`; золотые пути сделок — `scripts/golden_paths.py`;
- замок каркаса и правило «новый стенд — через каркас» — `apps/core/tests/test_standlib.py`
  (`LEGACY_STANDS` только сокращать).

## Нельзя
- Запускать `playwright install` и ставить браузеры или npm-пакеты (`agent-browser`) — Chromium
  уже лежит в `/opt/pw-browsers`.
- Писать новый стенд мимо каркаса (свой `sync_playwright`, свой счётчик, свои размеры) и
  дописывать его в `LEGACY_STANDS`; старый стенд переносить на каркас при следующей правке.
- Поднимать сервер стенда на `config.settings.development` (debug-toolbar даёт 500 на каждом
  субдомене) и вызывать `--setup` на не-стенд-БД.
- Принимать JS-фичу по curl или серверному тесту; принимать вёрстку на одном размере, одном
  языке или только с JS.
- Ждать `networkidle` и «нет анимаций вообще»; мерить по тексту интерфейса вместо data-атрибутов.
- Останавливать сервер через `pkill -f` — только по PID; чужие процессы не трогать.
- Гонять стенд по проду (прокси рвёт туннель) и два тяжёлых прогона одновременно.

## Грабли
Запуск и среда:
- Версия Chromium в `/opt/pw-browsers` не совпадает с пакетом — путь задаёт `launch`, пакет
  ставит `uv run --no-project --with playwright`; хост демо — по `Domain` тенанта
  (`restaurant-demo.…`) · посл. 2026-10-26.
- `pkill -f "<строка>"` убивает свою же оболочку (exit 144) · посл. 2026-10-26.
- 500 «relation … does not exist» — стенд-БД отстала от миграций ветки
  (`migrate_schemas`), не дефект кода · посл. 2026-10-26.
- Django кэширует шаблоны и в DEBUG — после правки шаблона рестарт runserver, иначе стенд
  показывает старое · посл. 2026-11-13.
- В свежем контейнере нет `node_modules`: `npm run build:css` молча падает, стенд видит
  мобильную раскладку на компьютере — сначала `npm ci` · посл. 2026-11-08.

- При DEBUG=True `handler404` не зовётся: стенд страницы ошибки — `STAND_DEBUG=0` и
  `runserver --insecure` (`config/settings/stand.py`) · посл. 2026-11-22.
- Витрина `ptx` говорит de+en: проход «ru» по витрине без включения языка идёт по-немецки и
  ничего не проверяет (`scripts/fb33_m5a_404_stand.py`) · посл. 2026-11-22.

Язык и ожидание:
- Кабинет на стенде открывается по-английски — язык задавать явно (`open_page(lang=…)`),
  проверки вести по data-атрибутам · посл. 2026-11-20.
- С JS ждать только КОНЕЧНЫЕ анимации: слайдер витрины крутится бесконечно, «анимаций нет» не
  наступит (`settle`) · посл. 2026-11-21.
- Клик по кнопке формы панели ≠ переход: `aufbau.js` придерживает отправку, пока правка в
  пути; ждать новый элемент (`wait_for_selector`), а не загрузку · посл. 2026-11-20.
- Переключатель вкладки окна уходит через 350 мс — до проверки «занято» ждать ≥ 700 мс;
  перезагрузка даёт новый токен открытия окна · посл. 2026-11-21.
- Кнопки «Felder» («+ Frage», «Übernehmen») — обычный POST и со скриптами: ждать навигацию,
  а не ответ фонового запроса · посл. 2026-11-21.
- Геометрию окна мерить после анимации открытия; `route.abort` на POST-переходе оставляет
  страницу на месте · посл. 2026-11-20.

Что стенд видит неверно:
- Tab после последней цели `<dialog>` в Chromium уходит в оболочку браузера (BODY) и
  возвращается — это не утечка фокуса · посл. 2026-11-21.
- Стенд мерит КЛАСС целей по страницам, а не список из плана: список оказывается неполным
  (`scripts/fb33_m39c_targets_stand.py`) · посл. 2026-11-22.
- `sr-only` в ленте без `relative` у карточки растягивает страницу (390 → 455 px) — мерить
  `documentElement.scrollWidth` (`overflow`) · посл. 2026-11-08.
- `data-reveal` прячет секции на скриншоте всей страницы · посл. 2026-09-01.
- `a11y_check` — только механика. Контраст над фото, градиентом, подложкой идёт в «не измерено»
  (смотреть глазами); поле с одним `placeholder` — ✗; sr-only «Übernehmen» без `aria-hidden` —
  верно, `aria-hidden` на ней — ✗ `a11y-hidden-focus` (решение M3-5c) · посл. 2026-11-24.
- `innerText` не видит пункт в свёрнутом «Mehr»; `radio.check()` ждёт `checked=true`, которого
  сбрасываемый пикер не держит · посл. 2026-09-10.
- Студия: панель после входа схлопнута, строки зависят от типа открытой страницы
  (`?page=<тип>`); ждать инструментацию кадра, не фикс-таймаут · посл. 2026-09-10.

- Параллельные стенды: сервер стенда — с `DB_CONN_MAX_AGE=0` (иначе `max_connections` Postgres
  кончается: «too many clients», ложные ✗ входа); инвентарь и стенд не гонять одновременно
  (общий Redis — ложные «ответ 302») · посл. 2026-11-24.
- Сессии стенда — в кэше Redis, а тесты зовут `cache.clear()` (FLUSHDB): стенд по умолчанию на
  своей базе `/2` (`config/settings/stand.py`), параллельным серверам — `REDIS_CACHE_URL=…/<N>`
  каждому свою; замок `test_stand_redis_isolated.py` · посл. 2026-11-24.

- Зум 200 % / 400 % — вьюпорт 720×450 / 360×225 (при 1440), а не `html{font-size:200%}`: подмена шрифта не меняет брейкпоинты и даёт ложную «ширину» кабинета (`scripts/fb33_e7_woher_stand.py`) · посл. 2026-11-24.

## Что гейтить
- `uv run pytest apps/core/tests/test_standlib.py -q` — каркас и правило (без браузера и БД).
- `scripts/standlib.py --selftest` в Chromium — после любой правки каркаса; сломанная функция
  обязана дать ✗ и ненулевой код.
- Новый стенд зовёт `a11y_check` на КАЖДОЙ открытой странице (и в окне — со `scope` окна), окно
  закрывает через `focus_returns`. Машина НЕ видит осмысленность имени, порядок фокуса, объявления
  живых областей, связи вкладок и `lang` — это остаётся ревьюеру `a11y-architect`.
- Свой стенд: до правки и после, полный обход `matrix()` — оба размера, оба языка, оба режима;
  итог «N ✓, 0 ✗» и скриншоты 1440/390 в отчёт. Не доиграл — написать, какие сочетания.
- Правка шаблонов рядом: `apps/core/tests/test_template_comments.py` и
  `uv run python scripts/i18n_quickcheck.py`; общий гейт — `uv run python scripts/preflight.py`.

## Агенты ECC
`e2e-runner` — новый стенд и правка `static/js` (Python-Playwright стендами, без npm);
`a11y-architect` — новый элемент интерфейса (фокус, цели касания, роли); `django-reviewer` —
каждый срез; `silent-failure-hunter` — стенд, который глотает исключения или таймауты.
- Сверка «до/после» — базовый коммит (`git archive`) сервером рядом на ТОЙ ЖЕ стенд-БД в то же
  время: витрина зависит от часа (слоты, отель); хэш тела — без `csrfmiddlewaretoken`, `form_token`,
  `nonce` · посл. 2026-11-22.
- Демо-киты стенда владельца: `seed_demo_tenants --kit shop restaurant friseur hotel retreat`
  (ключи китов, не типы); владельцы `<slug>@example.com` — в схеме бизнеса (`set_tenant` до
  поиска); копия стенд-БД — `CREATE DATABASE … TEMPLATE …` вместо пересева · посл. 2026-11-22.
- Скрипт без браузера под владельцем (`scripts/fb33_m5d_inventory.py`): только настройки стенда,
  сессию удалять в `finally` · посл. 2026-11-23.
