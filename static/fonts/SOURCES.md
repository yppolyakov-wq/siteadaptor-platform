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

## DL-13 (2026-09-02) — шесть новых Look-семейств

Взяты с fonts.gstatic.com через CSS API Google Fonts (статические инстансы), сабсеты
latin / latin-ext (+ cyrillic, где есть), все — OFL 1.1.

| Файл | Гарнитура | Вес | Look |
|---|---|---|---|
| archivo-{latin,latin-ext}-700.woff2 | Archivo (Omnibus-Type) | 700 | monochrom |
| archivo-black-{latin,latin-ext}-400.woff2 | Archivo Black (Omnibus-Type) | 400 | bauhaus |
| quicksand-{latin,latin-ext}-700.woff2 | Quicksand (Andrew Paglinawan) | 700 | pastell |
| alfa-slab-one-{latin,latin-ext}-400.woff2 | Alfa Slab One (JM Solé) | 400 | retro |
| cormorant-garamond-{latin,latin-ext,cyrillic}-600.woff2 | Cormorant Garamond (Christian Thalmann) | 600 | nobel |
| manrope-{latin,latin-ext,cyrillic}-800.woff2 | Manrope (Mikhail Sharanda) | 800 | foto |
