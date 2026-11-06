# AIS A-1 — статьи справки + поиск без ИИ в шторке «✨ Assistent» (план, 2026-11-06)

План — агент ECC `planner`, сверен с кодом A-0 (`apps/core/assistant.py`, `assistant_views.py`,
`diagnoses.py`, `_assistant_body.html`). Источник — `ais-modules-directions-assistant-plan-2026-11-05.md`
§2.1–2.5, §5.2. Миграций нет.

**Открытый вопрос «А-1 (язык статей)» — решение ведущего:** исходник на немецком, переводы — тем же
путём, что весь интерфейс (msgid в 5 `.po`), без ИИ-перевода и квоты платформы. Обратимо: позже
ИИ может лишь предложить черновик перевода, путь хранения тот же.

## 1. Хранение — реестр в коде `apps/core/help_articles.py`

`Article(key, title, summary, steps, links, keywords, screens, directions, modules_any, owner_only,
readiness, diagnoses)` + `ArticleLink(key, url_name, label, query, method)` — frozen dataclass,
строки `gettext_lazy` / `pgettext_lazy("help-keywords", …)`. Почему не markdown и не БД: gettext
извлекает строки сам (гейты `i18n_gap`/quickcheck), ссылки проверяются `reverse`-замком, гейты —
тем же кодом, что меню, миграций нет, A-2 берёт объекты напрямую.

- **Один шаг = один короткий msgid** (правка длинного немецкого абзаца сделала бы его fuzzy во
  всех языках). Плейсхолдеров `%` в статьях нет (замок).
- **Ключевые слова** — один msgid с контекстом `help-keywords`; переводчик пишет СВОИ синонимы.
- `assistant.known_screens()` — общий набор экранов (вынос из `assistant_views._seite`).

## 2. Поиск — Python, не FTS

60 статей ≈ 20 КБ текста на язык — поиск в памяти без БД. FTS дал бы таблицу (миграцию) и словари
стемминга на язык (для `uk` штатного нет), а переводы живут в `.mo`. `database-reviewer` снят.

1. `norm`: casefold → NFKD без диакритики (ä→a, ё→е, İ/ı→i), ß→ss, слова `\w+`, < 3 символов —
   отброшены, запрос ≤ 80.
2. Индекс на язык (`lru_cache` по `get_language()`): текст в языке пользователя + немецкий.
3. Совпадение: слово ≥ 4 — подстрока (немецкие композиты), 3 — префикс.
4. Вес: заголовок 3 · ключевые слова 3 · summary 2 · шаги 1; сначала И, пусто — ИЛИ.
5. Гейты применяются ПО ХОДУ обхода отсортированного списка до кап 5 (скрытые не вытесняют).

## 3. «Hilfe zu dieser Seite»

`articles_here(request, seite)`: `screens ∩ assistant.screen_names(seite)`, кап 3, те же гейты.
`screens` по умолчанию = `links[0].url_name`.

## 4. Гейты

`owner_only` → только владелец; `directions`/`modules_any` — любой активен (сбой → скрыть);
основная ссылка через `assistant.link`: `None` или пустой URL → статью скрыть; `blocked=owner|
package|browser` → показать с пометкой (как у диагнозов). Доп. ссылки: `None` → выпадают.

## 5. UI

Партиал `core/_assistant_article.html` (`<details>` + шаги + ссылки через `_assistant_item.html`),
секция «Hilfe zu dieser Seite» после «Auf dieser Seite fehlt»; при `?q=` — две подписанные группы
«Anleitungen» и «Einstellungen», «Nichts gefunden.» — только если пусты обе. `?artikel=<key>` —
только whitelist ключей и гейты, иначе молча игнор (без отражения ввода). Без `|safe`/`<script>`.

## 6. Первая партия — 24 статьи

oeffnungszeiten · betriebsferien · kontakt_adresse · email_bestaetigen · impressum · agb_datenschutz
· website_veroeffentlichen · stadtkatalog · startseite_gestalten · erstes_produkt · kategorien ·
allergene · bezahlung · lieferung_abholung · leistung_anlegen · mitarbeiter_zeiten · buchungsregeln ·
zimmer_anlegen · zimmerpreise_saison · veranstaltung_anlegen · anfrageformular · aktion_erstellen ·
telegram_bot · team_rechte (owner_only). Тексты — по `cabinet-glossary.md`; налоги/право — только
«wo eintragen» + «Steuerberater/Anwalt fragen». До 40–60 — позже.

## 7. Замки ДО кода — `apps/core/tests/test_help_articles.py`

Реестр (ключи/шаги/ссылки) · каждая ссылка ∈ `known_screens` и reverse'ится, POST только
`OWNER_ACTIONS`, query без `?`/`//`/схемы · переводы во всех 5 `.po` (polib только читать) и без `%` ·
поиск: синоним, ru-слово, немецкое слово в ru, без умляута, композит, И→ИЛИ, кап, короткий запрос ·
гейты: выключенный модуль/направление → нет нигде, гейт до капа · сотрудник: владельческой нет,
недоступный экран — пометка без href · `?artikel=`: известный раскрыт, мусор/скрытый — игнор без
отражения · «Hilfe» по `seite` и через `SCREEN_EXTRA` · шаблоны без `|safe` · GET без записи ·
шов A-2 `for_prompt(request, keys)` → `{key, title, summary, steps, links:[{key,label}]}` без URL.

## 8. ECC-прогоны

Скиллы: `django-patterns`, `django-tdd`, `accessibility`, `error-handling`; pitfalls §3–§6.
`django-reviewer` (lazy, `lru_cache` × язык, гейты до капа, `_safe`) · `security-reviewer` (короткий:
whitelist `?artikel=`, отражение, права) · `silent-failure-hunter` (сбой блока → `help_failed`) ·
a11y (`details/summary`, уровни `hl`, 44 px) · Python-Playwright стенд шторки 390/1440 + ru.

## 9. Инкременты

A1.1 ядро + замки · A1.2 UI + немецкие msgid · A1.3 переводы en/ru/tr/uk + «Anleitung» у диагнозов
+ стенд. Один батч — один CI, затем FF в main.

## 10. Риски

Тексты устаревают вместе с UI (ссылки держит замок; правка экрана → правка статьи, строка в
`cabinet-screen-dod.md`). Fuzzy при правке немецкого (короткие msgid + замок). Ложная подсказка вне
прав — только `link()`. Для A-2: статьи — доверенный контент, вопрос владельца — в рамке
недоверенных данных; модель вернёт только ключи статьи и ссылки, URL строит сервер.
