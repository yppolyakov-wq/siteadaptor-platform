# Шрифты витрины (DS-1, 2026-08-12)

Self-hosted WOFF2 — без внешних CDN на витрине (GDPR DE). Файлы взяты из
пакетов [Fontsource](https://fontsource.org/) (`cdn.jsdelivr.net/fontsource/fonts/…`),
сабсеты latin / latin-ext / cyrillic (демо-локали de/en/tr/ru/uk).

| Файл | Гарнитура | Вес | Лицензия |
|---|---|---|---|
| playfair-display-{latin,latin-ext,cyrillic}-600.woff2 | Playfair Display (Claus Eggers Sørensen) | 600 | OFL 1.1 |
| nunito-{latin,latin-ext,cyrillic}-800.woff2 | Nunito (Vernon Adams et al.) | 800 | OFL 1.1 |
| barlow-condensed-{latin,latin-ext}-700.woff2 | Barlow Condensed (Jeremy Tribby) | 700 | OFL 1.1 |
| bricolage-grotesque-{latin,latin-ext}-700.woff2 | Bricolage Grotesque (Mathieu Triay) | 700 | OFL 1.1 |
| space-grotesk-{latin,latin-ext}-700.woff2 | Space Grotesk (Florian Karsten) | 700 | OFL 1.1 |
| schibsted-grotesk-{latin,latin-ext}-700.woff2 | Schibsted Grotesk (Schibsted) | 700 | OFL 1.1 |

Четыре нижних семейства (DL-1, 2026-09-01) взяты напрямую с fonts.gstatic.com
(официальная раздача Google Fonts, статические инстансы weight 700);
кириллических сабсетов у них нет — стеки в `FONTS` несут системный фолбэк.

`@font-face` с unicode-range — в `static/src/app.css` (собирается в
`static/css/app.css`). Браузер грузит файл лениво, только когда семейство
реально используется Look'ом (`FONTS` в `apps/tenants/siteconfig.py`).
