# Магазин одежды (кит `mode` / Boutique) — гэп-анализ и план (2026-07-30)

Запрос владельца: «Нужен магазин одежды — разведка: что ещё добавить, какой нужен
функционал». Две разведки: код (кит CLOTHING + платформа) и рынок DACH (право,
must-have, механики бутика). Ниже — свод и очередь.

## 1. Что уже есть (код)
Кит «Studio Nordwind» (`mode`): 12 товаров в 3 категориях, размерные варианты с
per-size остатком (anti-oversell, select_for_update), 1 распроданный размер, 3
Sale-акции, доставка flat 4,90/frei ab 80, Style-Karte лояльность, меню
Damen/Herren/Accessoires/Sale. Платформа: поиск+фасеты (цена/наличие/рейтинг/бейдж),
JSON-LD, §312j-кнопка, PAngV-ноты, Widerruf-флоу+returned-статус, AGB per-locale,
Stripe/Vorkasse, CRM/кампании/win-back/gift/лояльность/publishing, «Продано N».

## 2. Главные гэпы (код ↔ рынок)
1. **Warteliste по размеру НЕ реализована** — waitlist существует только у акций
   (Promotion) и событий; тексты демо/FAQ/лендинга обещают её у товара → главное
   расхождение «маркетинг ↔ код» (roadmap-запись «waitlist есть» — неточна).
2. **Цвет × размер (multi-axis) + фото на вариант** — D3, отложен; варианты
   одноосевые (label). Для реального бутика — блокер входа.
3. **Фасета «размер» (и цвет/бренд) нет** на листинге — в одежде важнее цены.
4. **Größentabelle** (таблица размеров) — фичи нет.
5. **Textilkennzeichnung (EU 1007/2011)**: состав ткани ОБЯЗАН быть на карточке
   до кнопки заказа (юр-риск №1 для одежды) — структурированного поля нет.
6. **§11 PAngV для Sale**: зачёркнутая цена = низшая за 30 дней — истории цены нет
   (частый повод абманунгов у бутиков).
7. **Click&Reserve «отложить в примерочную»** (резерв 24–48 ч без оплаты, без
   Widerruf) — киллер-механика бутика против сетей; сейчас только корзина/pickup.
8. Первый экран `mode` — без слайдера/плиток, promotions-first раскладка,
   включённая «Unsere Bereiche» (владелец считает непрактичной).
9. Мелочь UX: «Noch X € bis Gratisversand» в корзине; Lieferzeit-строка;
   страница Versand & Zahlung; lookbook (Collection не привязан к Product);
   wishlist; PayPal/Klarna и DHL-API — external-gated.

## 3. Очередь (предложение)
**Волна M0 — «тот же набор» (без новых фич, СЕЙЧАС):** hero-слайдер (3 слайда:
Kollektion/Neuheiten/Sale) + плитки направлений `hero_widget="mode"`
(🔥 Sale с живой акцией / 👗 Sortiment / 🆕 Neuheiten / 🎁 Geschenkgutschein),
`enable_archetypes_section=False`; пресет корзины «Mit Empfehlungen».

**Волна M1 — право + честный Sale (дёшево, снимает юр-риски):**
M1-1 поле «Material/Zusammensetzung» на Product (+ вывод на карточке над CTA,
демо-заполнение); M1-2 Pflegehinweise (уход) опционально; M1-3 §11 PAngV — история
цены (30-дневный минимум) для зачёркнутой цены Sale-акций/compare_at.

**Волна M2 — размер как ось UX:** M2-1 Warteliste per-size на товаре («Größe M —
benachrichtigen») + авто-письмо при приёмке (связка с леджером); M2-2 фасет
«Größe» на листинге (по variant.label, только available); M2-3 Größentabelle
(переиспользуемые таблицы per категория, модалка на карточке).

**Волна M3 — Click&Reserve:** резерв в примерочную без оплаты (TTL 48ч,
reserve-движок промо-акций как база), кнопка №1 на карточке бутика;
канбан-стадия «Anprobe».

**Волна M4 (за отдельным решением / крупное):** D3 цвет×размер + фото варианта;
lookbook (Collection→Product); wishlist; «Noch X € bis Gratisversand»; RMA-флоу.
**External-gated:** PayPal/Klarna, DHL API, Instagram Shopping.

Право-памятки в онбординг (LUCID/Verpackung, PPWR 08.2026) — чек-лист, не код.

Источники: разведка кода (агент, 2026-07-30, пути в отчёте) + рыночный анализ
(IT-Recht Kanzlei/Händlerbund/Protected Shops по Textilkennzeichnung; §11 PAngV;
Verpackungsgesetz/PPWR).
