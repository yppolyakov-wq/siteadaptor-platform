# PIMG — настоящие фото на месте заглушек демо (план, 2026-11-04)

**Решение владельца:** «все — настоящие фото» (CC0/PDM). Иллюстрации (SVG от Claude) —
пилот отклонён («ужасный»). AI-фото — не делаем.

## Объём
`manage.py demo_photo_report` на 2026-11-04: покрытие 1189/1576 (75 %), без фото **387**
мест: 158 у бизнесов Золингена (`sg-*`, видны на портале), 79 `online_shop`, 74 `outlet`,
13 Pranasy, остальное — по 1–8 у китов T-8.22. Поисковые запросы (EN, 2–3 на ключ, порядок
отчёта) — `docs/pimg-photo-queries-2026-11-04.txt`, формат `stem:q1|q2|q3` = вход
`scripts/demo_photo_sheet.py --from-file`.

## Блокер — ключ Openverse
Аноним: 200 запросов/день, 20/мин. С 2026-11-04 API к тому же отдаёт 500 на `page_size>1`.
StockSnap — Cloudflare-челлендж, Wikimedia Commons — 429 с адреса сессии.
Владелец регистрирует приложение (`POST /v1/auth_tokens/register/`, подтверждает почту) и
кладёт `OPENVERSE_CLIENT_ID` / `OPENVERSE_CLIENT_SECRET` в секреты окружения. Скрипты
(`scripts/openverse_auth.py`) берут Bearer-токен сами; без переменных — аноним.

## Порядок (новая сессия с ключом)
1. Пробный запрос: `python scripts/demo_photo_fetch.py search puzzle --limit 12`.
2. Пачками по ~20 ключей: `python scripts/demo_photo_sheet.py --out <scratch> --from-file <пачка>`
   → контактный лист на ключ → просмотр глазами (правила `static/demo/photos/README.md`: без
   людей/лиц, водяных знаков, текста, чужого предмета; у вегана — без мяса/рыбы).
3. Принятый кадр: `python scripts/demo_photo_fetch.py get <url> <stem> --size product|hero`
   + строка в `SOURCES.md`. Нет честного кадра — остаётся заглушка (чужое фото хуже).
4. Приоритет: `sg-*` (портал) → `online_shop`/`outlet` → прочее. Pranasy — уже 4 раунда
   поиска (2026-08-26), ожидать мало.
5. Замки: дедуп md5, `demo_photo_report`; после мержа — `seed_demo_tenants --recreate`
   затронутых китов + `sync_aggregator`.
