# FB-33 стопка 16 — состояние на 2026-11-26 ~14:55 UTC (лимит сессии)
В ветке стопки: P0, D9 (+правки ревью), T2, T1a (+правки ревью), T4 (+правки ревью, app.css, замок событий).
Ветки срезов (origin): claude/fb33-stack-16-e10 (готов, ревью django шло), claude/fb33-stack-16-t1b и claude/fb33-stack-16-t3 (в работе — проверить, что запушено).
- T1b: + content_pages.schema_ref(versand) при выключенных заказах -> seite:versand (находка E10).
- E10: правка двух старых тестов (test_fb32_s6a_text_pages.py:117, test_m21_11_page_type.py:41) — проверить.
- CI стопки: отменено 3, после 10-й мин 2.
- Красные CI срезов: T4 x2 (app.css без npm ci; test_fb33_m37_preview — реестр событий aufbau.js не взят preflight --slice).
- Грабли в журнал: ревьюер сделал checkout в основном дереве; a11y-architect без Bash — дифф файлами; стенд --noreload кэширует шаблоны.
- Журнал: 30 находок плана записаны 4 сводными строками — расписать.
Дальше: свод E10, T1b, T3 -> волна 4 (K1, T6) новой сессии; полный preflight, обход, снимок dev_stats, handoff §1–§3.
- E10 ревью django: блокирующих нет (2 LOW без замков); правка двух старых тестов законна; CI ветки e10 — проверить, зелёный → сводить.
- T1b готов (ветка t1b, a9dbd0a): preflight --slice 748 ✓, стенд 176 ✓; эталоны 2 (прогноз 3); «Grundtext» из кода ушёл (msgid в .po снять на верхушке). Ревью ещё не было: django-reviewer, security-reviewer, seo-specialist.
- T1b не сделал schema_ref(versand) -> seite:versand при выключенных заказах (нужен E10): отдельная правка после свода E10, замок через вьюхи «Blöcke» и «Suchmaschinen» (content_page_views:110,:164, studio_pages:900).
- T1b → T3: подпись поля перевода (what) внутри _bw_tr.html идёт с lang бизнеса — это строка интерфейса; empty_ui у пустого перевода уже есть.
- T1b: битый оверлей seo — предупреждение в журнал на каждое чтение тега (1–3 на страницу), не одно.
- T3 готов (ветка t3, e027120, база 61154a8): preflight --slice 118 ✓, связанный набор 1058 ✓, стенд 550 ✓; эталоны 0. Ревью не было: django-reviewer, a11y-architect (файлы в scratchpad), e2e-runner.
- T3: правил литералы «Ihre Seite zeigt zuerst» в test_s16_t2_felder_langs.py (2) и test_fb33_m35c_window.py (1) — вне строки; T1b правил тот же test_fb33_m35c_window.py:62-64 — при своде T1b+T3 конфликт возможен, брать обе правки.
- T3 предлагает: _bw_tiles.html и _schema_usp.html явно передают first_note, убрать запасной путь fl.first_note в _bw_langs.html (plan_check --add).
- Кнопки ИИ у USP и SEO нет: _schema_usp.html/_bw_seo.html не задают tr — после свода T3 (разметка of/field готова); её стенд — на верхушке.
- T3 не гонял стенд m2i5c (нет тенанта ptx), 844×390 и prefers-reduced-motion.
Порядок свода волны 3: E10 → T1b → T3 (общий test_fb33_m35c_window.py), каждый по зелёному CI своей ветки; затем schema_ref(versand) и кнопка ИИ у USP/SEO — мелкими срезами; волна 4 K1, T6 от верхушки.
