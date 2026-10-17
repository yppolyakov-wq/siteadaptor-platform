"""T-8.27 «Импорт с сайта клиента» (план docs/t8-27-site-import-plan-2026-10-17.md).

Пайплайн: согласие → обход (`crawl`, транспорт `core.ssrf.safe_fetch`) → разбор
структурированных данных (`structured`) [→ ИИ, T-8.27e] → черновик (SiteImportRun/
SiteImportItem) → экран «Prüfen & veröffentlichen» → применение в каталог. Тела страниц
не храним — только извлечённое."""
