# Шрифты витрины (DS-1, 2026-08-12)

Self-hosted WOFF2 — без внешних CDN на витрине (GDPR DE). Файлы взяты из
пакетов [Fontsource](https://fontsource.org/) (`cdn.jsdelivr.net/fontsource/fonts/…`),
сабсеты latin / latin-ext / cyrillic (демо-локали de/en/tr/ru/uk).

| Файл | Гарнитура | Вес | Лицензия |
|---|---|---|---|
| playfair-display-{latin,latin-ext,cyrillic}-600.woff2 | Playfair Display (Claus Eggers Sørensen) | 600 | OFL 1.1 |
| nunito-{latin,latin-ext,cyrillic}-800.woff2 | Nunito (Vernon Adams et al.) | 800 | OFL 1.1 |

`@font-face` с unicode-range — в `static/src/app.css` (собирается в
`static/css/app.css`). Браузер грузит файл лениво, только когда семейство
реально используется Look'ом (`FONTS` в `apps/tenants/siteconfig.py`).
