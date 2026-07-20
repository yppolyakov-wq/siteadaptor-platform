# Тест-гид: все новые функции на демо (2026-07-19)

После деплоя и `python manage.py seed_demo_tenants --recreate` (полный ~15-20
мин; точечно: `--kit friseur --recreate`). База хостов — `siteadaptor.de`.
**Кабинет каждого демо:** `https://<host>/dashboard/` · логин
`<slug>@example.de` · пароль `demo-12345678` (печатается командой сеинга).

## Витрина (без логина)

| Функция | Где смотреть |
|---|---|
| ST-1 тёмный Look (nacht) | `mode.` — тёмная витрина, шрифт/акцент семейства |
| ST-1 warm-Look | `friseur.` — тёплая палитра/шрифт |
| ST-7c карточки «Text auf Foto» | `mode.` — грид товаров: имя+цена на градиенте поверх фото |
| ST-7c карточки «Kompakte Zeile» | `cafe.` — товары строками-прайсом (фото слева) |
| LS-2 «Jetzt erreichbar» | `friseur.` — зелёная пилюля снизу → WhatsApp |
| LS-1 видео-услуга | `friseur.` → Leistungen → «Strähnen / Highlights» → секция «Per Video zeigen lassen»; фильтр-чип `?video=1` на /termin/ |
| ST-2 пресеты страниц | `shop.` → /warenkorb/ (блоки «Gut zu wissen»/«Fragen?» + кросс-селл) и /ueber-uns/ («Unsere Geschichte»); `baeckerei.` → /ueber-uns/ («Team & Werte») |
| ST-2c контакт-стиль map_first | `restaurant-demo.` — главная, секция контактов: карта СВЕРХУ |
| ST-7b стили секций | `restaurant-demo.` (отзывы-цитаты, about с акцент-рамкой) · `cafe.` (CTA-карточки, USP-рамки) |
| ST-7a spacer «Groß» | `retreat.` — увеличенный воздух после галереи |
| UE2 стили скидок (4 вида) | `aktionsmarkt.` — акции: badge / countdown / festpreis / strikethrough |
| FD-1/2 Finder | `baeckerei.` и `friseur.` — /finder/ + CTA-секция главной |
| LS-6 problem-CTA | подтверждение любой брони/заказа — «⚠️ Etwas stimmt nicht?» |
| LS-4 бейдж времени ответа | `friseur.` → /nachricht/ (после resolved-тредов) |

## Кабинет (логин демо-владельца)

| Функция | Где смотреть |
|---|---|
| ST-4a хоум «что сегодня» | `/dashboard/` любого демо — виджеты Umsatz/спарклайн/Puls + 5 хабов |
| ST-3 Studio | «Website» → редактор: рейка Look/Seiten/Blöcke/Medien, page-лента снизу |
| ST-1b галерея Look'ов | мастер `/dashboard/setup/?step=stil` и fieldset «✨ Look» в билдере |
| ST-7c селект «Kartenform» | билдер → область Тема → «Kartenform» (живой предпросмотр) |
| ST-2 пикеры пресетов страниц | билдер → page-лента → «О нас»/корзина → карточки «Page template» |
| ST-5a Angebote-карточки | `/dashboard/angebote/` — грид с фото |
| ST-5b Канбан⇄Календарь⇄Лента | `werkstatt.` — /dashboard/board/ (выбран Kanban вместо календаря); сегмент-контрол на доске/списке/календарях |
| ST-5c CRM-карточки | `/crm/` — карточки с аватаром/тегами/LTV |
| ST-6 Marketing-центр | `/dashboard/marketing/` — карточки ROI + обзор напоминаний + панель результатов |
| ST-6b «Teilen» | список акций → «📣 Teilen» → статусы каналов + «Jetzt überall veröffentlichen» |
| LS-3 Sofort-Angebot | `friseur.` → /dashboard/inbox/ — тред «Balayage…» с карточкой Angebot (и публичная ссылка /o/…) |
| LS-6 «Прямая линия» | `friseur.` — high-тред «Problem: Termin» (красная полоса на доске, ⚡-бейдж SLA) |
| B4/LS-5 win-back | `cafe.` → Marketing → Kampagnen — активная «Wir vermissen Sie» (и строка в обзоре напоминаний) |
| FB-3/FB-4 статусы | `hotel.`/`aktionsmarkt.`/`werkstatt.` — /dashboard/status-manager/ + кастом-статусы на доске |
| Склад-2 (партии/MHD/закупки) | `baeckerei.`/`metzgerei.` — /dashboard/stock/ + /dashboard/purchasing/ |
| UD4-2 каналы уведомлений | `/dashboard/settings/notifications/` — матрица + Care-Zyklus |

Не покрыто демо (по архитектуре): подборки для товаров (M2M только услуги/
номера), LS-1 у отеля (нет booking-услуг), полный прогон писем (демо не шлёт).

Полный список доменов: restaurant-demo, pranasy, hotel (+hotels-портал),
aktionsmarkt, baeckerei, metzgerei, cafe, mode, touren, friseur, werkstatt,
handwerker, retreat, shop — все `.siteadaptor.de`.
