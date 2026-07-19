# Демо «по новой идеологии» + тест-гид — план (2026-07-19, запрос владельца)

Запрос: «нужен тестовый вариант где проверить все новые функции, на всех
архетипах нужно сделать всё по новой идеологии». Разведка (Explore): ни один
из 14 китов не показывает новые фичи волн 2026-07-18..19 (Look/theme, presence,
is_video, page_presets, контакт/секц-стили, spacer, orders_view, discount_style,
card_style, inbox-фичи LS-3/4/6, win-back). Кабинетные фичи (Studio/хоум/
Marketing-центр/переключатель заказов) доступны через логин демо-владельца
(<slug>@example.de / demo-12345678), но данных для них местами нет.

## §1 Принципы

- Каждая новая фича видна хотя бы на 1-2 демо; правки — ТОЧЕЧНО по китам
  (golden-локи test_demo_kits пер-китовые — обновлять только затронутые).
- Точка расширения одна: `apply_kit` (cfg-dict перед normalize + хвост после
  tenant.save) + новые поля DemoKit; сеинг остаётся одноразовым (--recreate).
- presence/is_video гейтятся whatsapp_number — ставить парой.

## §2 Раскладка «фича → кит» (v1)

| Фича | Кит(ы) | Как |
|---|---|---|
| ST-1 Look/theme=dark | mode→`nacht`, friseur→`warm` | поле `look` + apply_look после save |
| ST-7c card_style | mode→`overlay`, cafe→`compact` | поле `card_style` → site_defaults |
| LS-1 видео-услуга + номер | friseur (Farbberatung), werkstatt (Kostenvoranschlag) | `whatsapp_number` на ките + `is_video` в спеке услуги |
| LS-2 presence «Jetzt erreichbar» | friseur, werkstatt | cfg `presence={"mode":"on"}` |
| ST-2 page_presets | shop: cart→vertrauen + info→geschichte; bakery: info→team | apply_page_preset в cfg |
| ST-2c контакт-стиль | restaurant→map_first | поле `section_styles` → merge в _kit_sections |
| ST-7b стили секций | restaurant: reviews=quotes, about=accent; cafe: cta=cards, usp_bar=cards | то же |
| ST-7a spacer «Groß» | retreat: 1 C-блок между секциями | доп. секция в списке |
| ST-5b orders_view | werkstatt→"kanban" (дефолт был бы calendar) | cfg-ключ |
| UE2 discount_style | aktionsmarkt: пронумеровать акциям percent/badge/strikethrough/festpreis/countdown | promotions_spec += discount_style |
| UB3-2 collections | shop, mode | по аналогии с friseur |
| LS-3 Offer + LS-6 high-тред + LS-4 подпись | friseur: НОВЫЙ `_seed_kit_inbox` (тред клиента + staff-ответ + Offer open; второй тред high «Etwas stimmt nicht?») | новый хелпер |
| B4/LS-5 win-back | cafe: CouponCampaign kind=auto_winback active | рядом с NewsletterCampaign |

## §3 Тест-гид

`docs/demo-test-guide-2026-07-19.md`: таблица «функция → домен → страница/клик»
по всем 15 доменам (14 витрин + hotels-портал), с логином владельца для
кабинетных фич (Studio, хоум-виджеты, Marketing-центр, Teilen, доска/календарь/
лента, Angebote-карточки, CRM-карточки, статус-менеджер, Finder-настройки).
База хоста — TENANT_DOMAIN_BASE (siteadaptor.de на проде).

## §4 Ops (владелец)

После мержа: `python manage.py seed_demo_tenants --recreate` (полный ~15-20
мин; точечно `--kit friseur --recreate` и т.д.). Демо-пароль прежний.

## §5 Риски

- Пер-кит golden-локи test_demo_kits — синхронные правки только затронутых
  ассертов (restaurant/cafe/mode/shop/friseur/werkstatt/retreat/aktionsmarkt/
  bakery).
- Идемпотентность не требуется (схема дропается), но НЕ ломать существующий
  однопроходный путь.
- inbox-сеинг: не слать письма (notify гасится дедупом? — сеять напрямую
  моделями Conversation/Message/Offer, БЕЗ enqueue-хуков).

## §6 Инкременты

1. Поля DemoKit + простые cfg-фичи (look/card_style/presence/whatsapp/is_video/
   orders_view/section_styles/spacer/page_presets/discount_style/collections)
   + правки затронутых кит-тестов.
2. `_seed_kit_inbox` (friseur) + win-back (cafe) + тесты.
3. Тест-гид doc + build-log/CLAUDE.md + пометка ops.
