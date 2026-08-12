# План GK-15 «Демо catering в структуре референса» (2026-08-12)

Запрос владельца: «на основе доработки засеять демо кейтеринга как у исследуемого
варианта» (goodkarma-catering.de; структура — gap-анализ §1). Все нужные фичи уже
в платформе (AF-волна + GK-1..14) — инкремент ЧИСТО контентно-демо + один
generic-механизм кита.

## Референс ↔ демо (что добавляем)

Референс-главная: hero → рейтинг 4.9★/40+ с аватар-рядом → сетка 6 категорий →
3 столпа → отзывы → цифры «200+ Events / 50.000+ Gerichte / 10.830+ Gäste» →
цитата основателя → форма → newsletter в футере. Сервис-лендинги: «20–1000
Gäste», «ab 25 € p.P.», 3 пакета Klassik/Plus/Premium (Fingerfood).

| Референс | Демо-механизм |
|---|---|
| Цифры-полоса | C-блок `stats` (GK-4) на главной |
| Цитата основателя | C-блок `image_text` c данными пресета «Gründer-Zitat» (GK-7) |
| Newsletter-блок | C-блок `newsletter` (GK-8) в конце главной |
| Аватар-ряд/звёзды отзывов | photo/stars в testimonials (GK-6, 4-кортежи) |
| Рейтинг Google 4.9★/40+ | сид кэша GK-11 (демо-фикция, как отзывы) |
| Соцссылки в футере | Tenant-соцполя (GK-9) — БЕЗОПАСНО: только корневые URL instagram.com/facebook.com (чужие реальные аккаунты линковать нельзя) |
| 6 категорий услуг | +3 категории (Hochzeit/Business&Seminar/Private&Messe) |
| Пакеты Klassik/Plus/Premium | +2 товара Fingerfood-Paket Plus/Premium |
| «ab N Personen» | уже сделано GK-14 + у новых позиций сразу |

## Решения

1. **Generic-механизм**: `DemoKit.home_blocks` — [{after, key, data, visual}];
   вставка в `_kit_sections` по образцу spacers (id `demo-block-<i>`), ДО
   spacer-цикла. Любой кит сможет нести C-блоки главной (принцип владельца
   «свободно добавлять в другие архетипы, индивидуально наполнять»).
2. **Tenant-поля**: `DemoKit.socials` (whitelist 5 полей) + `DemoKit.google_rating`
   {"rating","count"} → кэш-поля GK-11 + updated_at=now (place_id НЕ задаём —
   beat демо не трогает, API не зовётся). Пишутся в существующем блоке
   update_fields apply_kit.
3. **Индексы promotions_spec (0–3) не двигать**: новые товары Fingerfood — ПОСЛЕ
   существующих; новые категории — между Fingerfood и Getränke (created_products
   растёт хвостом, первые 4 индекса стабильны; Getränke уезжает в конец — ок).
4. **i18n**: 3 новых имени категории × 4 словаря demo_i18n (walker переводит
   Category). Названия/описания позиций — не переводим (политика DL); тексты
   stats/founder/newsletter — вне walker, «по спросу» (как описания).

## Тесты

Расширить catering-тест test_demo_kits: 6 категорий; в site_config.sections
после normalize есть блоки stats/newsletter/image_text (данные пережили
_clean_cblock_data); соцполя и google-кэш засеяны. test_demo_menus — без правок
(меню кита не меняется). Прогон: demo_kits + demo_menus + golden.

## Верификация

Локальный `seed_demo_tenants --kit catering --recreate` + curl-маркеры главной
(stats-цифры, цитата, newsletter-форма, Google-строка в trust, 6 категорий).
