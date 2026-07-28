# T-1 (возобновление): массовый de.po — план

**Дата:** 2026-07-28 · **Статус:** очередь владельца «делай все», п.3.
Предыстория: T1-b (2026-07-11) создал de.po (2477 записей, DeepL+QA), но
активацию откатили — англ. тест-ассерты падали в DE-рендере + локале-
зависимость golden-тестов (предсказание `legal-lang-package-plan §2`).
Коммиты `93e19cf`/`1c8be62` сохранены для cherry-pick. Без миграций.

## Что изменилось с тех пор (разблокировки)

- `.mo` можно собирать ЛОКАЛЬНО через polib (msgfmt в среде нет — раньше
  DE-рендер нельзя было воспроизвести локально, теперь можно → цикл фиксов
  ассертов не зависит от CI).
- CI и Dockerfile уже компилируют ВСЕ `locale/*/django.po` (фикс T1-b) —
  активация = просто наличие файла.

## Инкременты

1. **Черри-пик**: `locale/de/LC_MESSAGES/django.po` из `93e19cf` + патчи
   12 тест-файлов (EN→DE ассерты) из обоих коммитов (3-way, файлы могли
   уехать).
2. **Дозаполнение** 567 msgid, появившихся после 2026-07-11: немецкие
   msgid → identity; английские → перевод (вручную, батчами; НЕ DeepL —
   урок коротких строк).
3. **Локальный DE-прогон**: собрать .mo polib'ом → broad pytest → чинить
   всплывшие EN-ассерты (правка на немецкий текст) и локале-зависимые
   golden'ы (если normalize materializ. переведённые строки — фиксировать
   локаль в тесте override'ом, НЕ менять golden).
4. Гейты → push → CI → merge. Прод получает немецкий кабинет/витрину при
   следующей пересборке образа; правки перевода — rosetta (T1-c).

## Риски

- Смешанная msgid-база: полный каталог ломает ровно те ассерты, что
  цитируют англ. строки, — чиним по факту прогона (в этом суть трека).
- de-плюрали: у German nplurals=2 — DeepL-наследие проверено T1-b QA.

## Состояние на середину работ (2026-07-28, для продолжения)

- В worktree (НЕ закоммичено): `locale/de/LC_MESSAGES/django.po` (3044 записи =
  черри-пик 93e19cf + identity-544 + 79 ручных DE-переводов + 4 фидбэк-msgid);
  German-ассерт-патчи в `apps/catalog/tests/test_storefront.py` и
  `apps/stays/tests/test_public.py` (в ветке они ОТКАЧЕНЫ фиксапом `1ba9d22`
  — вернуть в коммит T-1); локальный `locale/de/…/django.mo` собран polib
  (gitignored; пересборка: polib save_as_mofile).
- Кластер 1 (catalog+tenants+core, DE-активен) дал ~19 уникальных падений
  (список ниже), НО прогон был загрязнён параллельными прогонами → перед
  фиксами ПЕРЕПРОВЕРИТЬ каждый последовательно. Кластеры 2 (stays/booking/
  orders/events) и 3 (промо/crm/account/aggregator/прочее) ещё не гонялись.
- Падения к разбору: test_home_builder(named_version), test_hub_tabs (5),
  test_media_registry, test_modules (2), test_sellable_card (3),
  test_ui_mode(simple_hides), test_normalize_golden (3 — предсказанная
  локале-зависимость: НЕ перегенерировать golden, а фиксировать локаль в
  тесте/normalize), test_services_section (2), test_sitetemplates(hero_widget).
- Правило: ассерты с англ. текстом в DE-рендере → менять на немецкий текст
  ЛИБО убирать зависимость от локали (id/классы вместо строк) — что чище.

## Прогресс (2026-07-28, продолжение)

- Кластер 1 (catalog+tenants+core) ПОЛНОСТЬЮ ЗЕЛЁНЫЙ под DE. Сделано:
  (1) normalize стал локале-стабильным (`translation.override(None)` вокруг
  `_normalize_impl` в siteconfig.py — golden целы, хранимый конфиг не зависит
  от языка запроса); (2) de.po QA-фиксы DeepL-коротышей: Board/Tickets
  identity, Book→Buchen, Stay→Übernachtung, Kontakte identity,
  Messages→Nachrichten, `%(m)s min`→identity (было «Ich habe»!), Set/Min;
  (3) EN→DE ассерты обновлены в: test_sellable_card (insgesamt, bis zu,
  / Nacht, mindestens 2), test_media_registry (unbenutzt), test_ui_mode
  (Derzeit: Experte), test_home_builder (Version speichern),
  test_sitetemplates (Verfügbarkeit prüfen), test_modules (Empfehlungen für
  Ihr Unternehmen, untypisch), test_hub_tabs — БЕЗ правок (после словаря).
- ОСТАЛОСЬ: прогнать кластер 2 (stays/booking/orders/events) и кластер 3
  (promotions/crm/account/aggregator/jobs/collections/finance/inventory/
  loyalty/imports/notifications/telegram/reviews/partners + billing без
  test_tasks) ПОСЛЕДОВАТЕЛЬНО (не параллелить — общая тест-БД!), чинить
  той же методикой; затем один коммит T-1: de.po + все тест-правки +
  normalize-фикс + build-log; push → CI → merge.

## Кластер 2 (stays/booking/orders/events): 20 падений к разбору

test_belegungsplan(ohne_zimmer chip) · test_buybox_parity stays(unavailable
reason) · test_occupancy_pricing(units add/delete — вероятно «Dynamic prices»
→ «Dynamische Preise») · test_restrictions(detail reason) · test_stay_flow_b
(datebar/calendar_first/rate_cards ×3) · booking: buybox_parity(hint) +
test_public(slots/group_slots/search_sort/upsell ×4) + service_reviews(order
parity) + services(next_free) · orders: delivery(cart options) · events:
index_parity ×3 + storefront ×2 (cover cards, online event).
Методика та же: немецкие строки в ассертах (сверяться с de.po значениями).
Затем кластер 3: promotions/crm/account/aggregator/jobs/collections/finance/
inventory/loyalty/imports/notifications/telegram/reviews/partners/core-остаток
(billing без test_tasks). После зелёного: git add de.po + все тест-правки +
build-log → push → CI → merge. НЕ параллелить прогоны (общая тест-БД).
