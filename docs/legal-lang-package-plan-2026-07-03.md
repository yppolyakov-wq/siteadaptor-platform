# Правовой-языковой пакет: L4 + L5 + E-2-остаток (план, 2026-07-03)

Порядок владельца («Так и делай»). Разведка агентом, факты сверены. Полный
отчёт — в транскрипте; здесь выжимка и слайсы.

## 1. Ключевые факты

- **L4 не начат:** `locale/` пуст (.po/.mo нет); LANGUAGES = DE+EN (S-3);
  LocaleMiddleware/cookie-переключатель/active_locales (L1/L2) работают.
  Msgid-объём: витрина 765, кабинет 501, всего по templates 2488 + 48 в apps.
  **Письма: 0 trans-тегов** (DE-хардкод), `translation.activate()` нигде не
  вызывается — локаль получателя не учитывается.
- **L5:** модели LegalDoc НЕТ; `/agb/` нет; правовое — плоские DE-TextField на
  Tenant с генерёнными фолбэками (`impressum_text()` и т.п.); демо-киты право
  НЕ засевают (пустые поля → фолбэк «Bitte anpassen»).
- **E-2:** §312j-кнопка и stays-PAngV сделаны; на product_detail/cart НЕТ нот
  «inkl. MwSt. / zzgl. Versand»; `Lieferzeit` на товаре нет; Zusatzstoffe/
  E-Nummern отсутствуют полностью (Allergene есть — паттерн `food.py`).

## 2. ⚠️ Грабля L4-хрома (решение при внедрении)

Msgid'ы шаблонов — английские; DE-витрина сейчас показывает msgid как есть,
и **сотни тест-ассертов проверяют английские строки в DE-рендере** («Only 2
left», «Goes well with this»…). Появление `de.po` с переводами сломает их
массово. Варианты: (а) массовая правка ассертов на немецкий, (б) тестовый
рантайм на en (ломает DE-числа «7,50» в других ассертах). Оба — большие.
**Вывод: массовый de.po хрома — ОТДЕЛЬНЫЙ трек с решением владельца**; в
пакете делаем инфраструктуру + письма (безопасно и ценно).

## 3. Слайсы пакета

- **1 (E-2 PAngV, S, без миграций):** ноты на product_detail (под ценой:
  «inkl. MwSt.» + «zzgl. Versandkosten» при delivery_enabled со ссылкой на
  тариф) и cart (у Total). Паттерн — как stays «incl. VAT».
- **2 (E-2 Zusatzstoffe, S, миграция catalog):** `Product.additives`
  (JSONField-коды) + справочник E-Nummern в `food.py` (паттерн ALLERGENS) +
  рендер рядом с Allergene + поле формы товара. LMIV/PAngV-комплаенс Gastro.
- **3 (L5 LegalDoc, M, миграция):** TENANT-модель
  `LegalDoc(kind ∈ impressum|datenschutz|widerruf|agb, locale, text)`
  (unique kind+locale). Резолвер `legal_text(tenant, kind, locale)`:
  LegalDoc[locale] → LegalDoc[default_locale] → плоское Tenant-поле →
  существующий генерённый фолбэк. Роут `/agb/` (страница видна только при
  наличии текста), `LEGAL_SECTIONS += agb`, кабинет «Recht»
  (/dashboard/recht/: 4 kind × активные локали), засев демо-китов
  (Impressum/Datenschutz/Widerruf из генераторов + AGB-заготовка по типу
  бизнеса — честные DE-тексты вместо placeholder).
- **4 (L4-письма, M, без миграций):** trans-теги в `templates/emails/*`
  (DE-текст = msgid, рендер DE не меняется → замки писем целы) +
  `translation.override(locale)` в `_render` нотификаций (локаль получателя:
  из брони/заказа, фолбэк default_locale тенанта) + `locale/en/.../django.po`
  с переводами ПИСЕМ + `compilemessages` в deploy.sh и CI-шаг. Массовый
  de.po хрома — вне пакета (§2).

## 4. Замки/тесты

PAngV-ноты: рендер-тесты detail/cart (+ «один способ = прежняя форма» цел);
Zusatzstoffe: модель/лейблы/рендер; LegalDoc: резолвер-цепочка фолбэков,
/agb/ 404-без-текста, кабинет CRUD, засев китов; письма: DE-байт-в-байт
(msgid=текст), EN-рендер с override, existing notification-тесты.
