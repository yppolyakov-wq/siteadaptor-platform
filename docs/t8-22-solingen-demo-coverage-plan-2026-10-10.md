# T-8.22 «Демо под все 15 разделов каталога Золингена» (2026-10-10)

Пункт 10 этапа 3 `t8-roadmap-2026-10-10.md`. Запрос владельца (10.10): «для категорий нужно
добавить демо-данных и демо-компаний». Цель — портал `solingen.<base>` и будущая главная
«Entdecke Solingen» (T-8.19) показывают все 15 разделов справочника T-8.13a на живых примерах.

## 0. Факты

- Портал Золингена показывает только листинги с `city="Solingen"`. Полные демо-киты живут в
  других городах (Hilden, Köln, Hamburg, Düsseldorf, Essen) — в Золингене их нет.
- В Золингене 7 лёгких демо T-8.1/T-8.16 (`profile="aktionen"`): только акции и карточка
  предприятия, товаров нет (каталог выключен, T-8.11 их товары и не выкладывает).
- Значит, вкладка «Produkte» портала Золингена сейчас пустая, а разделы Elektronik, Kinder &
  Familie, Tiere, Kunst & Geschenke, Auto & Mobilität, Haus & Garten, Dienstleistungen,
  Gesundheit & Fitness, Handwerk не представлены ни одним бизнесом.

## 1. Решение

Новые демо-бизнесы Золингена **ступени 2–3** (сайт с каталогом/услугами, не «Nur Aktionen»),
по одному на недостающий раздел; распределены по пяти районам. Каждый — небольшой, но
настоящий: 5–8 позиций с фото (или тематической заглушкой), ценой, категорией, 1–2 акции,
часы, адрес, координаты, «Über uns»; переводы en/ru/uk/tr через словари `demo_i18n_<loc>.json`.

| Кит | Раздел | Тип | Район | Содержимое |
|---|---|---|---|---|
| `klingenwerk` | Kunst & Geschenke (lokale Produkte, Handgemachtes) | retail | Mitte | Solinger Messer, Scheren, Schleifservice |
| `handy_doktor` | Elektronik & Technik | retail | Ohligs | Smartphones (refurbished), Zubehör, Display-Reparatur (услуга) |
| `spielkiste` | Kinder & Familie | retail | Gräfrath | Spielzeug aus Holz, Babybedarf |
| `pfotenglueck` | Tiere & Tierbedarf | retail | Wald | Futter, Zubehör, Hundesalon (услуга) |
| `rad_und_tat` | Auto & Mobilität | retail | Burg/Höhscheid | Fahrräder, Zubehör, Inspektion (услуга) |
| `wohnwerk` | Haus & Garten | retail | Burg/Höhscheid | Deko, Leuchten, Pflanzen |
| `feinkost_markt` | Lebensmittel & Getränke | grocery | Mitte | Feinkost, Getränke, Obst & Gemüse |
| `schuhhaus` | Mode & Accessoires | clothing | Ohligs | Schuhe, Taschen |
| `bergisch_fit` | Gesundheit & Fitness | other | Wald | Kurse и Probetraining (услуги) |
| `lichtblick` | Dienstleistungen | other | Mitte | Fotostudio: Passfotos, Bewerbung, Familien-Shooting (услуги) |
| `elektro_schmitz` | Handwerk & Reparatur | handwerker | Gräfrath | услуги + заявка |

Разделы «Essen & Gastronomie», «Beauty & Pflege», «Reisen & Übernachten», «Freizeit &
Erlebnisse» уже представлены лёгкими демо (кафе, салон, пансион) акциями и карточкой
предприятия; товары в них не обязательны. «Freizeit» дополнит событие у `bergisch_fit`.

Категории кита явно сопоставлены (`city_category` у категорий кита — новое поле спеки),
подсказка по названию — запасной путь. Демо выходят на портал только при `show_demo`
(T-8.15), бейдж «Demo» на карточках.

**Основная категория бизнеса** (⚠️ `tenants/0036`): `Tenant.city_category` — для услуг и
карточки предприятия, когда тип бизнеса ничего не говорит («Sonstiges» → фитнес, фотостудия);
поле «Hauptkategorie im Stadtkatalog» в «Mein Geschäft», у кита — `business_city_category`.
Раздел «Freizeit & Erlebnisse» — событие «Bastelnachmittag für Kinder» у `spielkiste`.

## 2. Замки

- каждый из 15 разделов справочника представлен хотя бы одним листингом бизнеса из Золингена
  после засева всех китов Золингена (кроме сознательно «только акции» разделов — они
  представлены карточкой предприятия);
- у каждого нового кита: город Solingen, район из реестра, координаты, ≥ 5 позиций, у всех
  позиций есть категория города;
- демо-словари: у новых строк есть перевод на 4 языка (гейт `scripts/demo_i18n_gap.py --kit`).

## 3. Вне объёма

Реальные фото CC0 для новых китов (сейчас — тематические заглушки резолвера; отдельной
фото-волной по спросу), главная «Entdecke Solingen» (T-8.19).
