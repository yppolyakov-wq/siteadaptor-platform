"""Branchen-Landingpages: eine öffentliche Feature-Seite je Archetyp.

`/branchen/<slug>/` beschreibt, was die Plattform für DIESE Branche kann. Inhalt =
generisches Modul-Raster (deterministisch aus `core.modules.REGISTRY`, gegroundet)
+ archetyp-spezifische Highlights (kuratiert, deutsch). Basissprache = Deutsch
(msgid); Übersetzungen en/ru/tr/uk kommen per .po nach (i18n-ready).

Slugs = Tenant.BUSINESS_TYPES ohne "other" (neutraler Typ hat keine eigene Branche).
"""

from django.utils.translation import gettext_lazy as _

from apps.core import modules

# Deutsche Kurznamen der Branche (für Überschriften/Index); Modell-Label ist "Bakery /
# Bäckerei" (zweisprachig) — hier die reine DE-Anzeige.
DISPLAY_NAME = {
    "bakery": _("Bäckereien"),
    "butcher": _("Metzgereien"),
    "grocery": _("Lebensmittelgeschäfte"),
    "clothing": _("Modegeschäfte"),
    "restaurant": _("Restaurants"),
    "cafe": _("Cafés"),
    "retail": _("Einzelhandel"),
    "online_shop": _("Online-Shops"),
    "tour_operator": _("Touren-Anbieter"),
    "hotel": _("Hotels & Pensionen"),
    "friseur": _("Friseursalons"),
    "handwerker": _("Handwerksbetriebe"),
    "werkstatt": _("KFZ-Werkstätten"),
    "events": _("Veranstalter"),
}

# Reihenfolge = Modell-Reihenfolge (ohne "other").
SLUGS = tuple(DISPLAY_NAME.keys())

# Recherchiert & adversarial verifiziert (Workflow 2026-07-13): jedes Highlight
# ist ein real existierendes Feature (Verifikation gegen den Code; erfundene
# Behauptungen wurden verworfen). Deutsch als msgid — Übersetzungen per .po.
CONTENT: dict[str, dict] = {
    "bakery": {
        "headline": _("Deine Bäckerei online: vorbestellen, abholen, frisch verkaufen"),
        "intro": _(
            "Deine eigene Bäckerei-Website mit Sortiment, Vorbestellung und Abholung ohne Warteschlange. Kundschaft bestellt Brot, Brötchen und Torten bequem online vor und holt zur Wunschzeit an der Theke ab. Allergene sind rechtssicher gekennzeichnet, Reste rettest du mit Anti-Food-Waste-Aktionen, und Stammkunden bindest du per digitaler Stempelkarte."
        ),
        "seo_title": _("Bäckerei-Website: vorbestellen, abholen, Allergene"),
        "seo_desc": _(
            "Website für deine Bäckerei: Sortiment online, Click & Collect mit Abholzeit, LMIV-Allergene, Anti-Food-Waste-Aktionen und digitale Stempelkarte für Stammkunden."
        ),
        "highlights": [
            {
                "icon": "🥜",
                "title": _("Allergene & Zusatzstoffe"),
                "text": _(
                    "Zu jedem Produkt kennzeichnest du die 14 EU-Allergene nach LMIV und die kennzeichnungspflichtigen Zusatzstoffe — automatisch sichtbar auf der Produktkarte."
                ),
            },
            {
                "icon": "♻️",
                "title": _("Anti-Food-Waste-Tüte"),
                "text": _(
                    "Übrige Backwaren am Abend verkaufst du als Überraschungstüte zum halben Preis — inklusive Streichpreis und optional erst per Klick aufgedeckt."
                ),
            },
            {
                "icon": "⚖️",
                "title": _("Grundpreis nach PAngV"),
                "text": _(
                    "Verkaufst du Brot nach Gewicht, rechnet die Seite den gesetzlich nötigen Grundpreis (z. B. €/kg) aus Menge und Einheit automatisch aus."
                ),
            },
            {
                "icon": "🎟️",
                "title": _("Limitierte Ware sichern"),
                "text": _(
                    "Torten oder kleine Chargen wie Bienenstich lässt du online reservieren — die Mengengrenze verhindert Überverkauf, sodass niemand vor leerer Theke steht."
                ),
            },
            {
                "icon": "🔁",
                "title": _("Wochenangebote automatisch"),
                "text": _(
                    "Wiederkehrende Aktionen wie das Brot der Woche oder das Abend-Angebot ab 17 Uhr planst du einmal — mit Countdown laufen sie täglich oder wöchentlich von selbst."
                ),
            },
        ],
    },
    "butcher": {
        "headline": _("Deine Metzgerei online: Fleisch vorbestellen & Partyservice anfragen"),
        "intro": _(
            "Verkaufe Fleisch, Wurst und Grillpakete online — deine Kunden bestellen vor und holen frisch an der Theke ab. Für Feste stellen Gäste eine Partyservice-Anfrage und bekommen von dir ein Angebot per Klick. Frischetheke mit Grundpreis pro Kilo, Herkunft der Höfe und Allergen-Angaben — rechtssicher und ohne Technik-Stress."
        ),
        "seo_title": _("Website für Metzgereien — Vorbestellung & Partyservice"),
        "seo_desc": _(
            "Eigene Website für deine Metzgerei: Grillpakete vorbestellen, Partyservice mit Angebot, Frischetheke mit Grundpreis pro Kilo, Herkunft und Allergen-Angaben."
        ),
        "highlights": [
            {
                "icon": "⚖️",
                "title": _("Grundpreis pro Kilo"),
                "text": _(
                    "Verkaufe an der Frischetheke nach Gewicht — der Grundpreis pro Kilo wird automatisch und PAngV-konform ausgewiesen."
                ),
            },
            {
                "icon": "🔥",
                "title": _("Grillpakete vorbestellen"),
                "text": _(
                    "Lass Grillpakete und Platten fürs Wochenende online sichern — mit begrenzter Stückzahl pro Woche, damit du dich nie überbuchst."
                ),
            },
            {
                "icon": "🎉",
                "title": _("Partyservice & Angebote"),
                "text": _(
                    "Gäste fragen Buffets und kalte Platten an, du schickst ein unverbindliches Angebot — der Kunde nimmt es online an oder lehnt es ab."
                ),
            },
            {
                "icon": "🏷️",
                "title": _("Allergene-Kennzeichnung"),
                "text": _(
                    "Kennzeichne Allergene und Zusatzstoffe bei Wurst, Salaten und Feinkost direkt am Produkt — LMIV-konform ausgewiesen."
                ),
            },
            {
                "icon": "📍",
                "title": _("Herkunft pro Produkt"),
                "text": _(
                    "Zeig bei jedem Produkt, von welchem Hof das Fleisch kommt — Regionalität, die deine Kunden direkt sehen."
                ),
            },
            {
                "icon": "🎟️",
                "title": _("Theken-Stempelkarte"),
                "text": _(
                    "Belohne Stammkunden mit einer digitalen Stempelkarte — zum Beispiel 10 Stempel für 1× Bratwurst gratis."
                ),
            },
        ],
    },
    "grocery": {
        "headline": _("Dein Lebensmittelmarkt online: Wochenangebote, die verkaufen"),
        "intro": _(
            "Mach aus deinem Lebensmittelgeschäft einen digitalen Aktionsmarkt — mit eigenem Sortiment, allen Angebotsarten und Click & Collect auf einer Mini-Website unter deiner Adresse. Von Prozent-Rabatt über Festpreis bis Überraschungstüte legst du jede Aktion in Minuten an, gebündelt in Gruppen wie Wochenangebote oder Räumung. Deine Kundschaft reserviert online, holt im Laden ab und sammelt mit Stempelkarte und Gutschein-Codes."
        ),
        "seo_title": _("Website für Lebensmittelmarkt: Aktionen & Click&Collect"),
        "seo_desc": _(
            "Eigene Website für deinen Lebensmittelmarkt: Wochenangebote, Festpreise, Überraschungstüten gegen Food-Waste, limitierte Aktionen, Click & Collect & Stempelkarte."
        ),
        "highlights": [
            {
                "icon": "🏷️",
                "title": _("Alle Aktionsarten"),
                "text": _(
                    "Prozent-Rabatt, neuer Festpreis, limitierte Menge, Countdown oder wiederkehrend — jede Angebotsart ist anlegbar und lässt sich in Gruppen wie Wochenangebote, Dauertiefpreis, Räumung und Anti-Food-Waste bündeln und filtern."
                ),
            },
            {
                "icon": "🔖",
                "title": _("Festpreis mit Streichpreis"),
                "text": _(
                    "Statt Prozenten ein fixer Aktionspreis mit durchgestrichenem Originalpreis — z. B. Brot 0,99 € statt 1,99 € — sauber als alter/neuer Preis ausgewiesen."
                ),
            },
            {
                "icon": "🔢",
                "title": _("Limitierte Mengen"),
                "text": _(
                    "Aktionen mit begrenzter Stückzahl («Nur noch X») lassen Kundinnen und Kunden online reservieren — eine Datenbank-Sperre verhindert Doppelverkäufe (Anti-Oversell)."
                ),
            },
            {
                "icon": "⏳",
                "title": _("Countdown & Wiederkehrend"),
                "text": _(
                    "Zeitlich begrenzte Aktionen mit sichtbarem Countdown und automatisch wiederkehrende Angebote täglich oder wöchentlich — z. B. Abend-Brötchen jeden Tag −50 %."
                ),
            },
            {
                "icon": "🥗",
                "title": _("Allergene & Zusatzstoffe"),
                "text": _(
                    "Kennzeichne Lebensmittel gesetzeskonform mit den Allergenen und Zusatzstoff-Klassen — direkt an Brot, Brötchen & Co. sichtbar für deine Kundschaft."
                ),
            },
        ],
    },
    "clothing": {
        "headline": _("Dein Mode-Shop mit Größen, Versand und Sale — online in Minuten"),
        "intro": _(
            "Verkaufe deine Mode online mit echten Größen und eigenem Lagerbestand pro Variante — ausverkaufte Größen sperren sich im Bestellformular von selbst. Deine Kundschaft bestellt bequem im Warenkorb, du versendest deutschlandweit und legst selbst fest, ab welchem Betrag der Versand kostenlos ist. Sale-Aktionen, Style-Karte und Produktbewertungen schaltest du mit wenigen Klicks dazu."
        ),
        "seo_title": _("Online-Shop für Mode: Größen, Versand & Sale-Aktionen"),
        "seo_desc": _(
            "Erstelle deinen Mode-Shop mit Größen und Bestand pro Variante, deutschlandweitem Versand mit Gratis-Schwelle, Sale-Aktionen, Style-Karte und Bewertungen."
        ),
        "highlights": [
            {
                "icon": "👗",
                "title": _("Größen & Bestand pro Größe"),
                "text": _(
                    "Lege je Artikel Größen an (S–XL oder Zahlengrößen wie 36–42) mit eigenem Lagerbestand — ausverkaufte Größen sind im Bestellformular gesperrt, der Preis zeigt automatisch „ab X €“."
                ),
            },
            {
                "icon": "🚚",
                "title": _("Versand mit Gratis-Schwelle"),
                "text": _(
                    "Deutschlandweiter Versand mit fester Versandpauschale, die ab einem von dir gesetzten Bestellwert (z. B. 80 €) automatisch auf kostenlos springt."
                ),
            },
            {
                "icon": "🔥",
                "title": _("Sale mit Rabattstil & Countdown"),
                "text": _(
                    "Schlussverkauf und Style-der-Woche als Prozent-Rabatt, durchgestrichener alter Preis oder Festpreis — jeweils mit ablaufendem Countdown."
                ),
            },
            {
                "icon": "🧭",
                "title": _("Sortiment & Sale-Menü"),
                "text": _(
                    "Gliedere dein Sortiment in Damen, Herren und Accessoires; ein Menüpunkt vom Typ „Sale“ verlinkt direkt auf die laufende Rabatt-Gruppe."
                ),
            },
            {
                "icon": "💝",
                "title": _("Style-Karte & Neukunden-Code"),
                "text": _(
                    "Binde Stammkundschaft mit einer Stempelkarte (z. B. Style-Karte, 10 Stempel = 10 €-Gutschein) und einem Rabattcode für Neukunden."
                ),
            },
        ],
    },
    "restaurant": {
        "headline": _("Deine Restaurant-Website: Speisekarte, Tischreservierung & Lieferung"),
        "intro": _(
            "Bring deine Karte online und nimm Gäste dort ab, wo sie suchen. Deine Website zeigt die digitale Speisekarte mit Fotos, Preisen und Allergenen, lässt Gäste in Sekunden einen Tisch reservieren und nimmt Bestellungen zur Lieferung oder Abholung entgegen. Extras, Beilagen und Kombo-Angebote klicken sich Gäste selbst zusammen – ohne Provision einer Lieferplattform."
        ),
        "seo_title": _("Restaurant-Website: Speisekarte & Tischreservierung"),
        "seo_desc": _(
            "Eigene Restaurant-Website mit digitaler Speisekarte, Allergenen, Tischreservierung, Lieferung & Abholung sowie Tickets für Events und Catering-Anfragen."
        ),
        "highlights": [
            {
                "icon": "🍽️",
                "title": _("Digitale Speisekarte"),
                "text": _(
                    "Gerichte nach Kategorien (Vorspeisen, Hauptgerichte, Getränke, Desserts) mit Foto, Preis und Größenvarianten wie klein/groß – jederzeit selbst änderbar."
                ),
            },
            {
                "icon": "⚠️",
                "title": _("Allergene & Zusatzstoffe"),
                "text": _(
                    "Jedes Gericht kennzeichnest du LMIV-konform mit Allergenen (Gluten, Milch, Fisch …) und Zusatzstoffen – auf der Karte für Gäste sichtbar."
                ),
            },
            {
                "icon": "🍕",
                "title": _("Extras & Beilagen zum Klicken"),
                "text": _(
                    "Gäste stellen Pizza-Beläge, Beilage und Garstufe selbst zusammen – über Auswahlgruppen mit Mindest-/Höchstzahl und Aufpreis pro Option."
                ),
            },
            {
                "icon": "🪑",
                "title": _("Tischreservierung nach Gästezahl"),
                "text": _(
                    "Gäste reservieren online einen Tisch mit Personenzahl; das System rechnet die Plätze zusammen und verhindert Überbuchung des Saals."
                ),
            },
            {
                "icon": "🛵",
                "title": _("Lieferung & Abholung mit PLZ-Zonen"),
                "text": _(
                    "Nimm Bestellungen zur Lieferung oder Abholung an – mit Mindestbestellwert, Liefergebühr je PLZ-Zone und kostenfrei-ab-Grenze, ohne Plattform-Provision."
                ),
            },
            {
                "icon": "🎟️",
                "title": _("Events & Catering-Anfragen"),
                "text": _(
                    "Verkaufe Tickets für Weinabend, Kochkurs oder Brunch und nimm Catering-Anfragen mit unverbindlichem Angebot direkt über die Seite entgegen."
                ),
            },
        ],
    },
    "cafe": {
        "headline": _("Die Website für dein Café — Karte, Tischreservierung & Kaffeepass"),
        "intro": _(
            "Mit der Plattform baust du in wenigen Minuten die eigene Website für dein Café — mit digitaler Karte, Online-Tischreservierung und Kaffeepass. Gäste sichern sich einen Tisch fürs Frühstück, bestellen Kuchen zum Mitnehmen und sammeln Stempel für den Gratis-Kaffee. Allergene und Zusatzstoffe stehen dabei rechtssicher an jeder Position der Karte."
        ),
        "seo_title": _("Café-Website: Karte, Tisch reservieren & Kaffeepass"),
        "seo_desc": _(
            "Website für dein Café: Speisekarte mit Allergenen, Online-Tischreservierung, Kaffeepass-Stempelkarte, Happy-Hour-Aktionen und Bestellung zum Mitnehmen."
        ),
        "highlights": [
            {
                "icon": "📅",
                "title": _("Tisch online reservieren"),
                "text": _(
                    "Gäste buchen per Wunschzeit einen Tisch — mit Personenzahl und Kapazitätsgrenze, auch fürs Wochenendfrühstück."
                ),
            },
            {
                "icon": "⚠️",
                "title": _("Allergene & Zusatzstoffe"),
                "text": _(
                    "Jede Karten-Position trägt LMIV-Allergene und Zusatzstoff-Kennzeichnung — rechtssicher direkt an Kaffee, Frühstück und Kuchen."
                ),
            },
            {
                "icon": "☕",
                "title": _("Kaffeepass-Stempelkarte"),
                "text": _(
                    "Digitale Stempelkarte für Stammgäste: bei jedem Kaffee ein Stempel, der siebte Kaffee geht aufs Haus."
                ),
            },
            {
                "icon": "🍲",
                "title": _("Mittagstisch mit Kontingent"),
                "text": _(
                    "Wechselnden Mittagstisch freitags zum Sonderpreis anbieten — reservierbar mit begrenzter Stückzahl, ohne Überbuchung."
                ),
            },
            {
                "icon": "⏳",
                "title": _("Happy-Hour & Countdown"),
                "text": _(
                    "Kuchen des Tages ab 16 Uhr rabattieren oder Tages-Aktionen mit sichtbarem Countdown laufen lassen."
                ),
            },
            {
                "icon": "🧺",
                "title": _("Zum Mitnehmen bestellen"),
                "text": _(
                    "Kuchen und Kaffee vorbestellen und abholen — Click & Collect mit Warenkorb direkt auf der Café-Seite."
                ),
            },
        ],
    },
    "retail": {
        "headline": _("Online-Shop für deinen Einzelhandel – mit Versand & Abholung"),
        "intro": _(
            "Bring dein komplettes Sortiment online – mit Varianten, Grundpreisen und Beständen, so wie es das deutsche Preisrecht verlangt. Deine Kundinnen und Kunden bestellen bequem, holen kostenlos im Laden ab oder lassen sich nach PLZ-Zone beliefern. Und du behältst Warenwert, Meldebestände und Bestellvorschläge jederzeit im Blick."
        ),
        "seo_title": _("Online-Shop für den Einzelhandel | Versand & Abholung"),
        "seo_desc": _(
            "Bring deinen Einzelhandel online: Sortiment mit Varianten, Grundpreis nach PAngV, Bestandsführung, Versand nach PLZ-Zone und Click & Collect."
        ),
        "highlights": [
            {
                "icon": "🧩",
                "title": _("Varianten & Bestand"),
                "text": _(
                    "Führe Größen, Mengen oder Sorten als Varianten mit eigenem Preis, Bestand und EAN – die Restmengen zählen bei jeder Bestellung automatisch runter."
                ),
            },
            {
                "icon": "⚖️",
                "title": _("Grundpreis automatisch"),
                "text": _(
                    "Bei Gewichts- und Volumenware berechnet der Shop den Grundpreis (€/kg, €/l) automatisch – rechtssicher nach PAngV, ohne Handrechnerei."
                ),
            },
            {
                "icon": "🚚",
                "title": _("Versand & Abholung"),
                "text": _(
                    "Lege je PLZ-Zone eigene Versandkosten, Mindestbestellwert und Gratis-Grenze fest – oder biete kostenlose Abholung per Click & Collect im Laden an."
                ),
            },
            {
                "icon": "📦",
                "title": _("Lager im Griff"),
                "text": _(
                    "Warenwert, Marge, Meldebestände und Bestellvorschläge auf einen Blick – die Buchungen laufen als lückenloses Lager-Leger mit."
                ),
            },
            {
                "icon": "🏷️",
                "title": _("EAN-Scan & Inventur"),
                "text": _(
                    "Artikel per SKU oder EAN scannen, Bestände über eine Zählliste inventarisieren und Schwund oder Bruch als Korrektur mit Grund erfassen."
                ),
            },
            {
                "icon": "🛡️",
                "title": _("Vertrauensleiste & Recht"),
                "text": _(
                    "Zeige Versandkosten, 14-Tage-Widerruf und sichere Zahlung als Vertrauensleiste direkt unter dem Titelbild – Trust für neue Käufer."
                ),
            },
        ],
    },
    "online_shop": {
        "headline": _("Dein Online-Shop — verkaufen und versenden, ganz ohne Ladenlokal"),
        "intro": _(
            "Verkaufe deine Produkte online und liefere sie nach Hause oder biete kostenlose Abholung an — auch ohne physisches Geschäft. Du pflegst Sortiment, Varianten und Preise selbst, kassierst per Stripe, Vorkasse oder bei Abholung und behältst deinen Lagerbestand im Blick. Rechtssichere Angaben wie Grundpreis nach PAngV und Widerrufsfrist sind von Anfang an dabei."
        ),
        "seo_title": _("Online-Shop erstellen: verkaufen & versenden | DACH"),
        "seo_desc": _(
            "Baue deinen Online-Shop mit Varianten, Grundpreis nach PAngV, PLZ-Versand, Zahlungsmix (Stripe/Vorkasse) und Lagerbestand — für DACH-Kleinbetriebe."
        ),
        "highlights": [
            {
                "icon": "🚚",
                "title": _("Versand & PLZ-Zonen"),
                "text": _(
                    "Lege pro PLZ-Bereich eigene Versandkosten, Freigrenze und Mindestbestellwert fest — Lieferung oder kostenlose Abholung."
                ),
            },
            {
                "icon": "👕",
                "title": _("Varianten & Größen"),
                "text": _(
                    "Biete Produkte in Größen oder Farben an — jede Variante mit eigenem Preis und eigenem Bestand."
                ),
            },
            {
                "icon": "⚖️",
                "title": _("Grundpreis nach PAngV"),
                "text": _(
                    "Der Preis pro Kilogramm oder Liter wird automatisch berechnet und rechtssicher auf jedem Artikel angezeigt."
                ),
            },
            {
                "icon": "💳",
                "title": _("Zahlungsmix für DACH"),
                "text": _(
                    "Kunden zahlen online per Stripe, per Vorkasse-Überweisung oder bei Abholung — du wählst, was du anbietest."
                ),
            },
            {
                "icon": "📦",
                "title": _("Bestand & Nachbestellung"),
                "text": _(
                    "Führe ein Lagerbuch mit Warenwert und erhalte Bestellvorschläge, sobald Artikel zur Neige gehen."
                ),
            },
            {
                "icon": "🔎",
                "title": _("GTIN & Google-Sichtbarkeit"),
                "text": _(
                    "Hinterlege GTIN/EAN je Artikel; deine Seite trägt automatisch die OnlineStore-Auszeichnung für Google."
                ),
            },
        ],
    },
    "tour_operator": {
        "headline": _("Touren & Ausflüge online buchbar — mit Tickets und QR-Check-in"),
        "intro": _(
            "Verkaufe öffentliche Stadtführungen als buchbare Zeitslots und datierte Tagesausflüge als Event-Tickets — beides auf deiner eigenen Website unter deiner Adresse. Kleine Gruppen bleiben dank Kapazitätsgrenze und Anti-Überbuchung geschützt, Gäste zahlen online oder per Anzahlung und bekommen ihr QR-Ticket direkt aufs Handy. Gästeführer-Profile, Bewertungen und ein Programm-Ablauf zu jeder Tour gehören dazu."
        ),
        "seo_title": _("Website für Touren & Ausflüge | Buchung & Tickets"),
        "seo_desc": _(
            "Eigene Website für Touranbieter: öffentliche Führungen als Zeitslots buchen, Ausflüge als Event-Tickets verkaufen, Anzahlung online, QR-Ticket aufs Handy."
        ),
        "highlights": [
            {
                "icon": "🧭",
                "title": _("Touren als Zeitslots"),
                "text": _(
                    "Öffentliche Führungen buchen Gäste als Zeitslot am Treffpunkt; die Gruppengröße zählt gegen die Kapazität (z. B. max. 16 Plätze), Überbuchung ist ausgeschlossen."
                ),
            },
            {
                "icon": "🎟️",
                "title": _("Tickets mit Preisstufen"),
                "text": _(
                    "Datierte Ausflüge und Weinproben verkaufst du als Events mit bezahlten Tickets und Preisstufen wie Frühbucher und Standard."
                ),
            },
            {
                "icon": "💳",
                "title": _("Anzahlung online"),
                "text": _(
                    "Pro Ausflug legst du eine Anzahlung fest (z. B. 20 %) — Gäste zahlen online an, der Rest wird vor Ort fällig."
                ),
            },
            {
                "icon": "📱",
                "title": _("QR-Ticket & Check-in"),
                "text": _(
                    "Nach der Buchung erhalten Gäste ein QR-Ticket per E-Mail; am Treffpunkt scannst du es zum Einchecken der Teilnehmer."
                ),
            },
            {
                "icon": "🗺️",
                "title": _("Programm-Ablauf pro Tour"),
                "text": _(
                    "Zu jeder Tour zeigst du einen Ablaufplan mit Uhrzeiten und Stationen direkt auf der Detailseite."
                ),
            },
            {
                "icon": "👤",
                "title": _("Gästeführer-Profile"),
                "text": _(
                    "Stelle deine lizenzierten Gästeführer mit Foto, Sprachen und eigener Profilseite vor."
                ),
            },
        ],
    },
    "hotel": {
        "headline": _("Deine Hotel-Website mit Online-Zimmerbuchung nach Datum"),
        "intro": _(
            "Von der Zimmerbuchung nach Datum bis zur Kurtaxe: Deine Pension oder dein Hotel bekommt eine eigene Website mit Verfügbarkeitskalender, Ratenplänen und Online-Checkin. Gäste prüfen die Verfügbarkeit in Sekunden und buchen ohne Konto — überbuchungssicher für jedes Zimmer."
        ),
        "seo_title": _("Hotel-Website mit Zimmerbuchung & Belegungskalender"),
        "seo_desc": _(
            "Website für dein Hotel oder deine Pension: Zimmerbuchung nach Datum, Verfügbarkeitskalender, Tarife, Kurtaxe und Online-Checkin — überbuchungssicher."
        ),
        "highlights": [
            {
                "icon": "🛏️",
                "title": _("Buchung nach Datum"),
                "text": _(
                    "Deine Gäste wählen An- und Abreise, sehen freie Zimmer im Verfügbarkeitskalender und buchen bei Bedarf mehrere Zimmer auf einmal — jedes Zimmer überbuchungssicher."
                ),
            },
            {
                "icon": "💶",
                "title": _("Tarife & Verpflegung"),
                "text": _(
                    "Biete pro Zimmer mehrere Ratenpläne an — Basistarif, mit Frühstück, Halbpension oder Sparpreis — jeweils mit eigener Stornoregel und Anzahlung von 0, 30 oder 100 %."
                ),
            },
            {
                "icon": "📉",
                "title": _("Automatische Preisstaffeln"),
                "text": _(
                    "Frühbucher-, Last-Minute- und Langzeitrabatte sowie Saisonpreise greifen automatisch — mit mehreren Stufen je Regel, ganz ohne manuelles Nachrechnen."
                ),
            },
            {
                "icon": "🧾",
                "title": _("Kurtaxe automatisch"),
                "text": _(
                    "Die Kurtaxe wird pro Erwachsenem und Nacht automatisch berechnet und im Gesamtpreis ausgewiesen — Kinder auf Wunsch beitragsfrei."
                ),
            },
            {
                "icon": "✅",
                "title": _("Online-Checkin & Meldeschein"),
                "text": _(
                    "Gäste füllen den digitalen Meldeschein schon vor der Anreise aus — Bundesmeldegesetz-konform gespeichert und nach einem Jahr automatisch gelöscht."
                ),
            },
        ],
    },
    "friseur": {
        "headline": _("Die Website für deinen Friseursalon — Termine online, ganz einfach"),
        "intro": _(
            "Du bekommst eine eigene Salon-Website, auf der deine Kundinnen und Kunden ihren Wunschtermin in 30 Sekunden buchen — nach Leistung, Dauer und Uhrzeit. Stylisten-Auswahl, automatische Erinnerungen, Treuekarte und verifizierte Bewertungen sind von Anfang an dabei. Deine Pflegeprodukte verkaufst du gleich online mit."
        ),
        "seo_title": _("Friseur-Website mit Online-Terminbuchung | Salon-Software"),
        "seo_desc": _(
            "Eigene Website für deinen Friseursalon: Online-Termine nach Leistung, Stylisten-Auswahl, Erinnerungen, Treuekarte, Bewertungen und Produktverkauf."
        ),
        "highlights": [
            {
                "icon": "💇",
                "title": _("Termin nach Leistung"),
                "text": _(
                    "Kunden wählen Schnitt, Farbe oder Styling mit fester Dauer und Preis und buchen direkt einen freien Slot — ohne Anruf, ohne Konto."
                ),
            },
            {
                "icon": "👩‍🎨",
                "title": _("Stylisten-Auswahl"),
                "text": _(
                    "Jeder Mitarbeiter hat eigene Arbeitszeiten, Profil und Foto — Gäste buchen gezielt bei Lea, Jonas oder wem sie vertrauen."
                ),
            },
            {
                "icon": "🔔",
                "title": _("Automatische Erinnerung"),
                "text": _(
                    "Vor dem Termin geht automatisch eine Erinnerung raus — das senkt No-Shows, ganz ohne manuelles Nachhaken."
                ),
            },
            {
                "icon": "🎫",
                "title": _("Treuekarte & Mehrfachkarten"),
                "text": _(
                    "Digitale Stempelkarte für Stammkunden plus Guthaben-Karten wie die 10er-Karte Waschen & Föhnen mit Nächten-/Credit-Abzug."
                ),
            },
            {
                "icon": "➕",
                "title": _("Zusatzleistungen buchen"),
                "text": _(
                    "Gäste ergänzen ihren Termin um Extras wie Haarkur Intensiv oder Kopfmassage — der Aufpreis fließt automatisch in die Summe."
                ),
            },
            {
                "icon": "⭐",
                "title": _("Bewertungen pro Leistung"),
                "text": _(
                    "Nach dem Besuch lädt eine E-Mail zur Bewertung ein; echte Bewertungen pro Leistung stehen verifiziert auf der Detailseite."
                ),
            },
        ],
    },
    "handwerker": {
        "headline": _("Die Handwerker-Website: Anfragen, Angebote & Aufträge online"),
        "intro": _(
            "Als Handwerksbetrieb baust du hier deine eigene Website — ganz ohne Technikwissen. Kunden schildern ihr Vorhaben online, du antwortest mit einem klaren Kostenvoranschlag zum Festpreis. Von der Anfrage über das Angebot bis zur Rechnung wickelst du jeden Auftrag digital ab."
        ),
        "seo_title": _("Handwerker-Website mit Angebot & Auftrag online"),
        "seo_desc": _(
            "Website für Handwerksbetriebe: Kunden fordern online ein Angebot an, du erstellst Kostenvoranschläge zum Festpreis, kassierst Anzahlungen und verwaltest Aufträge."
        ),
        "highlights": [
            {
                "icon": "🧰",
                "title": _("Angebot anfordern"),
                "text": _(
                    "Interessenten schildern ihr Vorhaben über ein Online-Formular — mit Fotos und Baustellen-Adresse. Jede Anfrage landet direkt in deinem Auftrags-Cockpit."
                ),
            },
            {
                "icon": "📋",
                "title": _("Kostenvoranschlag mit Positionen"),
                "text": _(
                    "Erstelle Angebote mit einzelnen Positionen, Mengen, Einzelpreisen und MwSt — durchgängig von der Anfrage über den Auftrag bis zur fertigen Rechnung."
                ),
            },
            {
                "icon": "✅",
                "title": _("Angebot online freigeben"),
                "text": _(
                    "Kunden öffnen ihr Angebot über einen privaten Link und nehmen es an oder lehnen es ab — mit hinterlegtem Gültigkeitsdatum."
                ),
            },
            {
                "icon": "💳",
                "title": _("Anzahlung online kassieren"),
                "text": _(
                    "Optional zahlt der Kunde bei der Angebotsannahme eine Anzahlung per Stripe — die Zahlung bestätigt den Auftrag automatisch."
                ),
            },
            {
                "icon": "🔧",
                "title": _("Festpreis-Leistungen"),
                "text": _(
                    "Zeige feste Leistungen mit Festpreis und kostenloser Vor-Ort-Beratung, die Besucher direkt anfragen können."
                ),
            },
            {
                "icon": "📍",
                "title": _("Servicegebiet & Notdienst"),
                "text": _(
                    "Hinterlege dein Einzugsgebiet per Postleitzahl plus Öffnungszeiten und Notdienst — so sieht jeder Besucher sofort, ob du für ihn arbeitest."
                ),
            },
        ],
    },
    "werkstatt": {
        "headline": _("Deine KFZ-Werkstatt online: Termin & Kostenvoranschlag"),
        "intro": _(
            "Deine eigene Website für die KFZ-Werkstatt: Kunden buchen Termine online, fordern unverbindliche Kostenvoranschläge mit Fahrzeugangabe an und verfolgen den Reparaturstatus. Angebote nimmst du an oder lehnst sie ab, Ersatzteile verkaufst du gleich mit. Alles ohne Papierkram, direkt auf deiner eigenen Subdomain."
        ),
        "seo_title": _("KFZ-Werkstatt-Website: Termin & Kostenvoranschlag online"),
        "seo_desc": _(
            "Website für deine KFZ-Werkstatt: Kunden buchen Termine online, fordern Kostenvoranschläge mit Fahrzeugdaten an und verfolgen den Reparaturstatus."
        ),
        "highlights": [
            {
                "icon": "🧾",
                "title": _("Kostenvoranschlag online"),
                "text": _(
                    "Kunden schildern ihr Anliegen, du erstellst ein Angebot mit Positionen und MwSt. — angenommen oder abgelehnt wird direkt online über einen Link."
                ),
            },
            {
                "icon": "🚗",
                "title": _("Fahrzeug erfassen"),
                "text": _(
                    "Die Anfrage nimmt Kennzeichen sowie HSN/TSN auf, damit dein Angebot von Anfang an zum richtigen Modell passt."
                ),
            },
            {
                "icon": "🔧",
                "title": _("Reparatur-Status"),
                "text": _(
                    "Kunden verfolgen ihren Auftrag über einen öffentlichen Zeitstrahl: Anfrage → Angebot → Beauftragt → Erledigt → Abgerechnet."
                ),
            },
            {
                "icon": "📅",
                "title": _("Termin mit Hebebühne"),
                "text": _(
                    "Kunden wählen Leistung und freien Slot; ein eigener Status „Teile bestellt“ hält den Werkstatt-Termin reserviert, bis das Auto in die Bühne kommt."
                ),
            },
            {
                "icon": "🔎",
                "title": _("Bei Google als KFZ-Betrieb"),
                "text": _(
                    "Deine Angebots-Seite trägt schema.org-AutoRepair-Auszeichnung, damit Suchmaschinen dich als KFZ-Werkstatt erkennen."
                ),
            },
            {
                "icon": "🛢️",
                "title": _("Teile & Zubehör"),
                "text": _(
                    "Motoröl, Bremsbeläge oder Wischerblätter verkaufst du direkt mit — Kunden bestellen online und holen in der Werkstatt ab."
                ),
            },
        ],
    },
    "events": {
        "headline": _("Website für Veranstalter: Tickets verkaufen, Plätze sicher füllen"),
        "intro": _(
            "Deine eigene Event-Seite für Retreats, Workshops, Kurse und Konzerte — Besucher wählen einen Termin und buchen direkt online, mit Bezahlung und QR-Ticket per E-Mail. Jedes Event hat ein festes Platzkontingent, das Doppelbuchungen verhindert, dazu Teilnehmerliste, Warteliste und Anmeldedaten an einem Ort. Von der Frühbucher-Staffel bis zur Anzahlung stellst du alles selbst ein — ohne Provision pro Ticket."
        ),
        "seo_title": _("Website für Veranstalter & Events — Tickets online verkaufen"),
        "seo_desc": _(
            "Eigene Event-Website für Retreats, Workshops & Kurse: bezahlte Tickets mit QR-Code, Platzkontingent, Frühbucher-Preise, Anzahlung, Warteliste & Online-Events."
        ),
        "highlights": [
            {
                "icon": "🎟️",
                "title": _("Bezahlte Tickets mit Platzgarantie"),
                "text": _(
                    "Besucher kaufen Tickets online und erhalten ein QR-Ticket per E-Mail; ein festes Platzkontingent pro Event verhindert Überbuchung automatisch."
                ),
            },
            {
                "icon": "💶",
                "title": _("Preisstaffeln & Frühbucher"),
                "text": _(
                    "Pro Event mehrere Preise anlegen — Frühbucher, Standard oder Mehrbett — jeweils optional mit eigenem Kontingent."
                ),
            },
            {
                "icon": "🧾",
                "title": _("Anzahlung & Ratenzahlung"),
                "text": _(
                    "Teure Retreats mit Anzahlung in Prozent buchbar (Rest vor Ort) oder in Monatsraten bis zum Veranstaltungstag."
                ),
            },
            {
                "icon": "📋",
                "title": _("Teilnehmerliste & Warteliste"),
                "text": _(
                    "Strukturierte Anmeldeanfrage (Ernährung, Erfahrung, Notfallkontakt) landet direkt am Ticket; bei ausgebuchten Events tragen sich Gäste in die Warteliste ein und werden bei frei werdenden Plätzen benachrichtigt."
                ),
            },
            {
                "icon": "💻",
                "title": _("Online-Events (Zoom & Co.)"),
                "text": _(
                    "Als Online-Event markierte Termine blenden Adresse und Karte aus — den Zugangslink bekommt der Teilnehmer erst nach der Buchung, damit er nicht öffentlich durchsickert."
                ),
            },
            {
                "icon": "✍️",
                "title": _("Haftungsausschluss & flexible Stornierung"),
                "text": _(
                    "Bei Bedarf unterschreiben Gäste einen Haftungsausschluss bei der Buchung; die Stornoregel wählst du je Event — kostenlose Selbststornierung bis X Tage vorher mit Online-Rückerstattung oder nicht erstattbar."
                ),
            },
        ],
    },
}


def is_valid(slug: str) -> bool:
    return slug in DISPLAY_NAME


def _module_features(slug: str) -> list[dict]:
    """Empfohlene Module dieses Archetyps als Feature-Karten (Icon/Name/Beschreibung)
    — deterministisch aus dem Modul-Register (Quelle der Wahrheit, deutsch)."""
    feats = []
    for m in modules.REGISTRY:
        if m.core:
            continue
        if slug in m.recommended_for:
            feats.append({"icon": m.icon, "label": m.label_de, "desc": m.description_de})
    return feats


def _demo_url(request, slug: str) -> str:
    """Live-Demo-Link des Archetyps (nur wenn geseedet) — Wiederverwendung der
    Onboarding-Logik, damit keine toten Links erscheinen."""
    from . import onboarding

    for card in onboarding.business_type_cards(request):
        if card["value"] == slug:
            return card["demo_url"]
    return ""


def page_context(request, slug: str) -> dict:
    """Voller Kontext der Branchenseite."""
    from django.conf import settings

    from .models import Tenant

    label = dict(Tenant.BUSINESS_TYPES).get(slug, slug)
    content = CONTENT.get(slug, {})
    icon = _meta().get(slug, ("✨", ""))[0]
    langs = [
        {"code": c, "label": c.upper()}
        for c in getattr(settings, "CABINET_LANGUAGES", [settings.LANGUAGE_CODE])
    ]
    return {
        "slug": slug,
        "label": str(label),
        "display_name": DISPLAY_NAME.get(slug, label),
        "icon": icon,
        "headline": content.get("headline"),
        "intro": content.get("intro"),
        "highlights": content.get("highlights", []),
        "features": _module_features(slug),
        "demo_url": _demo_url(request, slug),
        "seo_title": content.get("seo_title"),
        "seo_desc": content.get("seo_desc"),
        "ui_languages": langs,
    }


def index_cards(request) -> list[dict]:
    """Alle Branchen für die Übersicht /branchen/."""
    meta = _meta()
    return [
        {
            "slug": s,
            "icon": meta.get(s, ("✨", ""))[0],
            "name": DISPLAY_NAME[s],
            "blurb": meta.get(s, ("", ""))[1],
        }
        for s in SLUGS
    ]


def _meta() -> dict:
    from .onboarding import BUSINESS_TYPE_META

    return BUSINESS_TYPE_META
