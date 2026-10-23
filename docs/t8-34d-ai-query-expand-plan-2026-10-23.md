# T-8.34d — ИИ-подстраховка поиска (2026-10-23)

> Запрос владельца: «это же ИИ-поиск, он должен знать всё?» Поиск каталога — база
> (полнотекст + словарь), ИИ — только запасной ход. План — агент planner, вариант (б).

## Решение
- **Сначала словарь** (`search_synonyms.CROSS_LANG`, T-8.34c): ИИ зовётся, только если
  мост не знает хотя бы одного значимого слова запроса на ru/uk/en/tr, а точной выдачи нет
  или она ≤ `AI_SEARCH_MAX_RESULTS`.
- **Асинхронно** через канал подсказки D-2: тот же подписанный слот, общий опрос, те же
  лимиты на IP и дневной потолок `AI_SEARCH_DAILY`. Страница модель не ждёт.
- **Модель отдаёт только немецкие слова** (`ai_expand.clean_terms`): буквы 3–24, без
  цифр/ссылок/стоп-слов/топонимов/слов самого запроса и слишком общих («essen»), ≤ 5.
- **Карточки — из базы** тем же пулом и фильтрами страницы (`search.match_any`, ИЛИ по
  словам), ≤ 6; над ними «✨ Gesucht auch nach: kuchen, torte» — каждое слово ссылка на
  обычный поиск по нему.
- Кэш: ключ = хеш нормализованного запроса + язык, хранятся только проверенные слова.
- **Выключатель:** `AI_SEARCH_ENABLED` И задача `search_query_expand` в
  `AI_TASKS_ENABLED` (админка «KI-Einstellungen»). Подсказка фильтров D-2 независима.

## Владельцу (до включения)
Абзац в Datenschutzerklärung портала/платформы (юр. вычитка):
«Wenn die Suche keine passenden Treffer findet, kann der Suchtext — ohne IP-Adresse und
ohne Konto, Kontaktdaten werden entfernt — an einen KI-Dienst in der EU (Anbieter laut
Abschnitt KI-Dienste) übermittelt werden, um passende deutsche Suchbegriffe zu finden.
Das Ergebnis wird bis zu 24 Stunden ohne den Suchtext zwischengespeichert. Rechtsgrundlage:
Art. 6 Abs. 1 lit. f DSGVO (funktionierende Suche).»

## Отложено
- Счётчик `ai_expanded` в журнале поиска (миграция) — по спросу; частые слова из журнала
  дописывать в словарь `CROSS_LANG`.
