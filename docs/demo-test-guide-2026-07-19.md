# Тест-гид: маршрут проверки новых функций на демо (обновлён 2026-07-31)

Структура — «по остановкам» (демо-сайтам), а не по функциям: идёшь по сайтам
по порядку и на каждом проверяешь короткий список. Так же оформлен
владельческий чеклист-артефакт (галочки) — та же структура, что здесь.

## Шаг 0 — подготовка (без этого демо выглядят по-старому)

Новая идеология попадает на демо только при пересеве. На сервере:

```bash
cd ~/projects/siteadaptor-platform && ./scripts/deploy.sh single
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  --profile single run --rm web \
  python manage.py seed_demo_tenants --recreate   # ~15-20 мин; точечно: --kit friseur --recreate
```

**Проверка языков (волна i18n, 2026-07-31):** переключатель 🗣 в шапке кабинета —
de/en/tr/ru/uk; смотреть статусы заказов, вкладки доски, справочники (аллергены,
единицы, типы бизнеса), подсказки форм и кнопки — немецкого текста в чужом языке
быть не должно. Витрина переключается своим селектором (языки включаются в
`/dashboard/settings/languages/`). Письма уходят на языке тенанта; PDF/счета
намеренно остаются немецкими (решение по ним — за владельцем).

Кабинет любого демо: `https://<host>/dashboard/` · логин `<slug>@example.de` ·
пароль `demo-12345678` (печатается командой сидинга). База хостов —
`siteadaptor.de`.

## Стоп 1 · friseur. — самая насыщенная (~15 мин)

Витрина: тёплый Look (ST-1) · зелёная пилюля «Jetzt erreichbar» → WhatsApp
(LS-2) · услуга «Strähnen / Highlights» с секцией «Per Video zeigen lassen» +
чип «Video» на /termin/ (LS-1) · `/finder/` 2–3 вопроса → 3 предложения +
CTA-секция главной (FD-1/2).

Кабинет: новый хоум — виджеты Umsatz/спарклайн/Puls + плитки хабов (ST-4a) ·
плоский сайдбар 7 пунктов Übersicht·Verkäufe·Angebote·Marketing·Integrationen·
Website·Einstellungen (ST-4b) · Studio-редактор: рейка Look/Seiten/Blöcke/
Medien + лента страниц + правый инспектор (ST-3) · «✨ Look» и «Kartenform» в
области Темы, живой предпросмотр (ST-1b/7c) · инбокс: тред «Balayage…» с
карточкой Sofort-Angebot и ссылкой /o/… (LS-3) + high-тред «Problem: Termin»,
красная полоса на доске (LS-6) · Marketing → Finder: редактор «Eigene Fragen»
+ «Branchen-Vorlage laden» (FD-3) · `/dashboard/marketing/` Marketing-центр +
«📣 Teilen» в списке акций (ST-6) · `/dashboard/angebote/` карточный грид
(ST-5a) · `/crm/` карточки с LTV (ST-5c).

## Стоп 2 · cafe.

Компакт-карточки-прайс (ST-7c) · стили секций CTA/USP (ST-7b) · Marketing →
Kampagnen: активный win-back «Wir vermissen Sie» (B4/LS-5) · Einstellungen →
Benachrichtigungen: вкладка Care-Zyklus (LS-5).

## Стоп 3 · mode. — волна бутика M0–M4 (обновлено 2026-07-31)

Тёмный Look «Nacht» по умолчанию (ST-1) · overlay-карточки «текст на фото»
(ST-7c).

Витрина (после `--kit clothing --recreate`):
- **Первый экран** (M0): слайдер 3 кадра + плитки Sale/Sortiment/Neuheiten/Gutschein.
- **Товар «Sommerkleid Nordlicht»** (M4-A): в селекторе — «S · Blau», «M · Sand»…
  (размер × цвет); при смене варианта **меняется главное фото** (Blau и Sand —
  разные снимки). Ниже — Material/Pflege (M1) и, если размер распродан,
  Warteliste (M2).
- **Каталог** `/sortiment/`: селект «Größe» смешивает оси (S/M/L/XL у платья и
  футболки) и старые label-размеры (36–42, 48–52 у джинсов/чино) — клик по
  любому что-то находит (M4-A, замок на смешанный каталог).
- **Merkzettel** (M4-C): сердечко на карточке и на детали → счётчик в шапке →
  страница `/merkzettel/`. Ничего не пишется в БД (сессия), аккаунт не нужен.
- **Lookbook** (M4-B): `/lookbook/herbst-looks/` — галерея образа + товары;
  чип «Herbst-Looks» в фасетах каталога.
- **Корзина** (M4-D): строка «Noch X € bis kostenlosem Versand» при выбранной
  доставке (порог 80 €).
- **Anprobe** (M3): «In der Anprobe reservieren» → бронь с TTL и письмом.
- **§11 PAngV** (M1): у товара со скидкой — «Niedrigster Preis der letzten 30 Tage».

## Стоп 4 · baeckerei. + metzgerei. — склад

`/finder/` пекарни (FD-1) · Lager: партии Chargen/MHD, бейджи, Verderb
(Склад-2 E1) · Einkauf: Lieferant/BE-заказ/приёмка/«Aus Bestellvorschlägen»
(E3) · baeckerei `/ueber-uns/` шаблон «Team & Werte» (ST-2).

## Стоп 5 · точечные: shop. / restaurant-demo. / retreat. / aktionsmarkt.

shop `/warenkorb/` пресет корзины + кросс-селл (ST-2) · restaurant-demo:
контакты «карта сверху», отзывы-цитаты, about с рамкой (ST-2c/7b) · retreat:
spacer «Groß» после галереи (ST-7a) · aktionsmarkt: 4 стиля скидок badge/
countdown/Festpreis/strikethrough (UE2) + status-manager кастом-статусов (FB-3).

## Стоп 6 · werkstatt. + hotel.

werkstatt: сегмент Канбан⇄Календарь⇄Лента на Verkäufe, выбран Kanban (ST-5b) ·
hotel: карточка брони гость/даты/суммы/Meldeschein + кнопки статуса (FB-11).

## Стоп 7 · платформа siteadaptor.de

`/entdecken/finder/` — 2 вопроса → 3 предложения, платные с «★ Anzeige»,
порядок органический (FD-4) · CTA-блок входа на `/entdecken/` · `/branchen/`
14 лендингов архетипов.

## Чего на демо НЕ видно — и это нормально

- **«Verkauft N diese Woche»** — честный порог ≥5 продаж за 7 дней; демо
  свежих продаж не сеет → бейдж появится только у живого бизнеса.
- **Письма** — демо не шлёт (console-бэкенд без RESEND_API_KEY). Problem-CTA
  «⚠️ Etwas stimmt nicht?» проверяется страницей подтверждения тестовой брони.
- **LS-1 у отеля** — нет booking-услуг по записи.
- **Секции-справочники на страницах (UC2-3b)** — проверяется действием:
  редактор → лента страниц → /ueber-uns/ → «+» → «FAQ anzeigen».
- ~~Подборки (Collections) для товаров~~ — с M4-B товары тоже входят в
  подборки (`/lookbook/<slug>/` + чип фасета); строка устарела 2026-07-31.

Если чего-то не видно в кабинете: тумблер Einfach/Experte в шапке (Простой
прячет продвинутое) и не включён ли «Klassische Ansicht» (Funktionen).

Полный список демо-хостов: restaurant-demo, pranasy, hotel (+hotels-портал),
aktionsmarkt, baeckerei, metzgerei, cafe, mode, touren, friseur, werkstatt,
handwerker, retreat, shop — все `.siteadaptor.de`.
