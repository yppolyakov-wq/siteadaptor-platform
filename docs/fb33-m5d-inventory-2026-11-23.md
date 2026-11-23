<!-- Снимок вывода scripts/fb33_m5d_inventory.py на верхушке стопки 10 (905f15b), стенд-БД с 5 китами (shop, restaurant-demo, friseur, hotel, retreat), 2026-11-23. Повтор: DB_NAME=<стенд-БД> uv run python scripts/fb33_m5d_inventory.py --json <файл> -->

# FB-33 M5d-0: блоки без окна

**Итог: 47 видов без окна / 44 с окном** (только без окна — 41, смешанных — 6); строк: без окна 242, с окном 628; мест (кит, хост, ref) без окна — 242, разных (код без id, ref) — 81, разных (тип страницы, ref) — 52 (так считает стенд владельца); пропущено 0.

## По виду блока

| key | без окна | с окном | страниц | киты | группы | вкладки | подпись |
|---|---:|---:|---:|---|---|---|---|
| `accommodation` | 4 | 0 | 4 | restaurant-demo, retreat | G1 |  | Unterkunft |
| `amenities` | 4 | 0 | 4 | hotel, retreat | G1 |  | Ausstattung |
| `anprobe` | 9 | 0 | 9 | friseur, hotel, restaurant-demo, retreat, shop | G1 |  | In der Anprobe zurücklegen |
| `article` | 3 | 0 | 3 | friseur, hotel, retreat | G1 |  | Text |
| `attributes` | 7 | 0 | 7 | friseur, hotel, restaurant-demo, retreat | G1 |  | Details |
| `bring` | 4 | 0 | 4 | restaurant-demo, retreat | G1 |  | Was Sie mitbringen sollten |
| `calendar` | 2 | 0 | 2 | restaurant-demo, retreat | G2 |  | Retreat-Kalender |
| `card` | 5 | 0 | 5 | friseur, hotel, restaurant-demo, retreat, shop | G1 |  | So finden Sie uns |
| `certifications` | 4 | 0 | 4 | restaurant-demo, retreat | G1 |  | Zertifizierungen |
| `config` | 1 | 0 | 1 | restaurant-demo | G1 |  | Kombi |
| `costs` | 4 | 0 | 4 | friseur, restaurant-demo, retreat, shop | G3 |  | Versandkosten |
| `description` | 20 | 0 | 20 | friseur, hotel, restaurant-demo, retreat, shop | G1 |  | Beschreibung |
| `examples` | 1 | 0 | 1 | restaurant-demo | G1 |  | Beispiele unserer Arbeit |
| `food` | 4 | 0 | 4 | restaurant-demo, retreat | G1 |  | Essen |
| `for_whom` | 4 | 0 | 4 | restaurant-demo, retreat | G1 |  | Für wen |
| `hosts` | 4 | 0 | 4 | restaurant-demo, retreat | G1 |  | Gastgeber |
| `idea` | 4 | 0 | 4 | restaurant-demo, retreat | G1 |  | Die Idee |
| `includes` | 4 | 0 | 4 | restaurant-demo, retreat | G1 |  | Was ist enthalten? |
| `info` | 9 | 0 | 9 | friseur, hotel, restaurant-demo, retreat, shop | G1 |  | Produktinformationen (Herkunft/Zutaten/Allergene) |
| `instore` | 9 | 0 | 9 | friseur, hotel, restaurant-demo, retreat, shop | G1 |  | Im Geschäft erhältlich |
| `items` | 4 | 0 | 4 | friseur, restaurant-demo, retreat, shop | G4 |  | Positionen |
| `more` | 3 | 0 | 3 | friseur, hotel, retreat | G1 |  | Weitere Beiträge |
| `more_dates` | 4 | 0 | 4 | restaurant-demo, retreat | G1 |  | Weitere Termine / Weitere Termine · nur Veranstaltungen |
| `pagetext` | 9 | 0 | 9 | friseur, hotel, restaurant-demo, retreat, shop | G3 |  | Text |
| `plans` | 1 | 0 | 1 | friseur | G2 |  | Mehrfachkarten |
| `price` | 4 | 0 | 4 | restaurant-demo, retreat | G1 |  | Preis |
| `private_tour` | 2 | 0 | 2 | restaurant-demo, retreat | G1 |  | Individuelle Reise anfragen · nur Touren |
| `program` | 4 | 0 | 4 | restaurant-demo, retreat | G1 |  | Zeitplan |
| `programs` | 3 | 0 | 3 | friseur, restaurant-demo, shop | G2 |  | Treueprogramm |
| `question` | 9 | 0 | 9 | friseur, hotel, restaurant-demo, retreat, shop | G1 |  | Frage stellen |
| `recent` | 9 | 0 | 9 | friseur, hotel, restaurant-demo, retreat, shop | G1 |  | Zuletzt angesehen |
| `recommend` | 5 | 0 | 5 | friseur, hotel, restaurant-demo, retreat, shop | G4 |  | Empfehlungen |
| `share` | 5 | 0 | 5 | friseur, hotel, restaurant-demo, retreat, shop | G1 |  | Teilen und QR-Code |
| `similar` | 4 | 0 | 4 | hotel, retreat | G1 |  | Ähnliche Zimmer |
| `sizes` | 9 | 0 | 9 | friseur, hotel, restaurant-demo, retreat, shop | G1 |  | Größentabelle |
| `slots` | 4 | 0 | 4 | friseur, hotel, restaurant-demo, retreat | G2 |  | Termin buchen |
| `teacherlist` | 1 | 0 | 1 | retreat | G2 |  | Lehrer |
| `venue` | 4 | 0 | 4 | restaurant-demo, retreat | G1 |  | Veranstaltungsort |
| `video` | 7 | 0 | 7 | friseur, hotel, restaurant-demo, retreat | G1 |  | Video-Beratung |
| `waitlist` | 9 | 0 | 9 | friseur, hotel, restaurant-demo, retreat, shop | G1 |  | Warteliste |
| `wizard` | 1 | 0 | 1 | friseur | G2 |  | Finder |
| `__page` | 0 | 148 | 148 | friseur, hotel, restaurant-demo, retreat, shop | G1, G2, G3, G4, — | seite, texte |  |
| `about` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | wie | Über uns |
| `anfrage` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | felder, wie | Anfrage |
| `archetypes` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | wie | Unser Angebot |
| `before_after` | 4 | 5 | 9 | friseur, hotel, restaurant-demo, retreat, shop | G1, — | wie | Vorher & nachher |
| `blog` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | was, wie | Neuigkeiten |
| `categories` | 0 | 15 | 15 | friseur, hotel, restaurant-demo, retreat, shop | — | was, wie | Kategorien |
| `combos` | 0 | 2 | 2 | restaurant-demo | — | wie | Sets & Menüs |
| `contact` | 0 | 10 | 10 | friseur, hotel, restaurant-demo, retreat, shop | G3, — | wie | Kontakt & Öffnungszeiten |
| `cta` | 0 | 6 | 6 | friseur, hotel, restaurant-demo, retreat, shop | G1, — | wie | Aufruf zum Handeln / Sie planen eine Veranstaltung? |
| `events` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | karte, was, wie | Veranstaltungen |
| `faq` | 0 | 16 | 16 | friseur, hotel, restaurant-demo, retreat, shop | G1, — | texte, wie | FAQ / Häufig gestellte Fragen |
| `faq_ref` | 0 | 1 | 1 | hotel | G1 | texte, wie | FAQ anzeigen |
| `finder` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | wie | Finder |
| `form` | 5 | 6 | 11 | friseur, hotel, restaurant-demo, retreat, shop | G2, G4 | felder | Anfrage-Formular / Bestellformular / Kontaktformular |
| `gallery` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | wie | Fotogalerie |
| `groups` | 4 | 18 | 22 | friseur, hotel, restaurant-demo, retreat, shop | G1, — | wie | Angebotsgruppen / Bereiche / Gruppen und Unternehmen |
| `hero` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | seite, was | Begrüßungsbanner |
| `image_text` | 0 | 1 | 1 | shop | G3 | texte, wie | Bild + Text |
| `kauf` | 0 | 24 | 24 | friseur, hotel, restaurant-demo, retreat, shop | G1 | texte | Buchung / Kaufen |
| `list` | 0 | 14 | 9 | friseur, hotel, retreat, shop | G3, — | karte, was, wie | Liste |
| `main` | 0 | 99 | 99 | friseur, hotel, restaurant-demo, retreat, shop | — | wie | Aktionen / Bewertungen / Blog |
| `next` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | G4 | texte | Was passiert jetzt |
| `offer` | 0 | 10 | 10 | friseur, hotel, restaurant-demo, retreat, shop | G1, — | wie | Angebot |
| `page_head` | 0 | 81 | 81 | friseur, hotel, restaurant-demo, retreat, shop | — | wie | Banner · Fotos der Seite / Banner · Kopf der Gruppe |
| `process` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | wie | So funktioniert es |
| `products` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | karte, was, wie | Produkte |
| `promotions` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | karte, was, wie | Aktuelle Angebote |
| `quick_links` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | was, wie | Schnellzugriff |
| `related` | 10 | 5 | 15 | friseur, hotel, restaurant-demo, retreat, shop | G1 | seite | Weitere Aktionen / Weitere Menüs aus dieser Kategorie / Ähnliche Produkte |
| `reviews` | 0 | 26 | 26 | friseur, hotel, restaurant-demo, retreat, shop | G1, — | wie | Kundenbewertungen |
| `services` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | karte, was, wie | Leistungen & Preise |
| `site_search` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | wie | Suche |
| `spacer` | 0 | 1 | 1 | retreat | — | wie | Abstand |
| `stay_rooms` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | karte, was, wie | Zimmer (Aufenthalte) |
| `stay_search` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | wie | Buchungssuche (Aufenthalte) |
| `summary` | 5 | 4 | 9 | friseur, hotel, restaurant-demo, retreat, shop | G4 | felder, texte | Bestätigung / Summe und Bestellbutton |
| `team` | 0 | 12 | 12 | friseur, hotel, restaurant-demo, retreat, shop | G1, — | wie | Team / Unser Team |
| `testimonials` | 0 | 9 | 9 | friseur, hotel, restaurant-demo, retreat, shop | G1, — | wie | Kundenstimmen |
| `text` | 0 | 2 | 1 | shop | G4 | texte, wie | Text |
| `tours` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | karte, was, wie | Reisen |
| `trust` | 0 | 14 | 14 | friseur, hotel, restaurant-demo, retreat, shop | G1, — | wie | Vertrauen und Referenzen / Vertrauensleiste |
| `upsell` | 7 | 4 | 11 | friseur, hotel, restaurant-demo, retreat, shop | G1, G4 | seite | Passt gut dazu |
| `usp_bar` | 0 | 5 | 5 | friseur, hotel, restaurant-demo, retreat, shop | — | texte, wie | Vertrauensleiste |

## Группы плана M5d

| группа | строк без окна | строк с окном | виды без окна | виды с окном |
|---|---:|---:|---|---|
| G1 (детали объектов) | 198 | 109 | accommodation, amenities, anprobe, article, attributes, before_after, bring, card, certifications, config, description, examples, food, for_whom, groups, hosts, idea, includes, info, instore, more, more_dates, price, private_tour, program, question, recent, related, share, similar, sizes, upsell, venue, video, waitlist | __page, cta, faq, faq_ref, kauf, offer, related, reviews, team, testimonials, trust |
| G2 (страницы-формы одной строкой) | 17 | 17 | calendar, form, plans, programs, slots, teacherlist, wizard | __page, form |
| G3 (текстовые страницы) | 13 | 16 | costs, pagetext | __page, contact, image_text, list |
| G4 (корзина и подтверждение) | 14 | 23 | items, recommend, summary | __page, form, next, summary, text, upsell |
| — (главная, листинги, категории (вне M5d)) | 0 | 463 |  | __page, about, anfrage, archetypes, before_after, blog, categories, combos, contact, cta, events, faq, finder, gallery, groups, hero, list, main, offer, page_head, process, products, promotions, quick_links, reviews, services, site_search, spacer, stay_rooms, stay_search, team, testimonials, tours, trust, usp_bar |

## Пропущено

нет
