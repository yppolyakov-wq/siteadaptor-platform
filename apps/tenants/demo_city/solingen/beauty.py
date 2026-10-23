"""Раздел «Beauty & Pflege» — демо-бизнесы Золингена (DCC).

Тексты массажа/косметики — без лечебных обещаний (HWG § 3): описываем процедуру,
не результат для здоровья.
"""

from ..spec import Biz, Item, Offer, Shelf, Svc

SECTION = "beauty-pflege"

MESSERSCHARF = Biz(
    key="sg_messerscharf",
    label="Barbershop Messerscharf",
    btype="friseur",
    category="friseur",
    district="ohligs-aufderhoehe-merscheid",
    street="Bahnhofsgasse",
    house="19",
    lat="51.1640",
    lng="7.0080",
    phone="+49 221 4710130",
    accent="#111827",
    hero_photo="barber-man",
    tagline="Herrenhaarschnitt, Bartpflege und Rasur mit dem Messer — ohne Wartezeit per Termin.",
    about=(
        "Barbershop am Bahnhof Ohligs: vier Stühle, Termin online, Walk-in wenn frei. "
        "Klassische Schnitte, Fade, Bart in Form und die heiße Rasur mit Kompresse."
    ),
    hours="studio",
    usp=("termin", "schnell", "zahlung"),
    services=(
        Svc("Herrenhaarschnitt", 30, "24.00", "Waschen, Schneiden, Styling.", "haircut"),
        Svc(
            "Haarschnitt + Bart",
            45,
            "34.00",
            "Schnitt und Bartkontur mit Rasiermesser.",
            "sg-bartpflege",
        ),
        Svc("Heiße Rasur", 30, "22.00", "Kompresse, Schaum, Messer, Aftershave.", "sg-rasur"),
        Svc(
            "Kinderhaarschnitt (bis 12)",
            20,
            "16.00",
            "Schnell und geduldig — mit Lolli.",
            "sg-kinderhaarschnitt",
        ),
    ),
    offers=(
        Offer(
            "Montags: Schnitt + Bart 29 €",
            "Statt 34 € — nur montags, nur per Termin.",
            price="29.00",
            was="34.00",
            ends="week",
            response="show",
            photo="barber-man",
            group="Diese Woche",
        ),
        Offer(
            "Vater & Sohn 36 €",
            "Herrenhaarschnitt plus Kinderhaarschnitt zusammen.",
            price="36.00",
            ends="none",
            response="show",
            photo="sg-kinderhaarschnitt",
            group="Dauerhaft",
        ),
    ),
)

ROSENBLATT = Biz(
    key="sg_rosenblatt",
    label="Kosmetikstudio Rosenblatt",
    btype="other",
    category="kosmetik",
    district="mitte",
    street="Am Klingenhof",
    house="9",
    lat="51.1735",
    lng="7.0920",
    phone="+49 221 4710131",
    accent="#be185d",
    hero_photo="sg-kosmetikstudio",
    tagline="Gesichtsbehandlungen, Wimpern und Augenbrauen — in Ruhe, mit Zeit.",
    about=(
        "Studio mit zwei Kabinen in der Innenstadt. Wir arbeiten mit Naturkosmetik aus "
        "Deutschland, nehmen uns pro Termin 60 bis 90 Minuten und beraten ehrlich."
    ),
    hours="studio",
    usp=("termin", "bio", "ruhe"),
    services=(
        Svc(
            "Klassische Gesichtsbehandlung",
            60,
            "69.00",
            "Reinigung, Peeling, Maske, Pflege.",
            "sg-gesichtsbehandlung",
        ),
        Svc(
            "Augenbrauen zupfen & färben",
            30,
            "24.00",
            "Form und Farbe passend zum Typ.",
            "sg-augenbrauen",
        ),
        Svc(
            "Wimpernlifting", 60, "59.00", "Mit Färbung, hält sechs bis acht Wochen.", "sg-wimpern"
        ),
        Svc(
            "Rücken-Peeling & Pflege",
            45,
            "49.00",
            "Für glatte Haut vor dem Sommer.",
            "sg-ruecken-pflege",
        ),
    ),
    offers=(
        Offer(
            "Neukunden: Gesichtsbehandlung 59 €",
            "Beim ersten Termin 10 € gespart.",
            price="59.00",
            was="69.00",
            ends="14d",
            response="show",
            photo="sg-gesichtsbehandlung",
            group="Neu bei uns",
            tags=("bio",),
        ),
    ),
)

PERLMUTT = Biz(
    key="sg_perlmutt",
    label="Nagelstudio Perlmutt",
    btype="other",
    category="naegel",
    district="wald",
    street="Heidestraße",
    house="7",
    lat="51.1780",
    lng="7.0600",
    phone="+49 221 4710132",
    accent="#db2777",
    hero_photo="sg-nagelstudio",
    tagline="Maniküre, Gel und Pediküre — mit veganen Lacken und sauberer Technik.",
    about=(
        "Drei Arbeitsplätze in Wald, Termine bis 20 Uhr. Wir sterilisieren jedes Werkzeug "
        "im Autoklav, arbeiten ohne Acrylgeruch und zeigen Ihnen die Farbe vorher am Nagel."
    ),
    hours="studio",
    usp=("termin", "qualitaet", "zahlung"),
    services=(
        Svc(
            "Maniküre mit Lack",
            45,
            "29.00",
            "Feilen, Nagelhaut, Pflege, Farbe nach Wahl.",
            "sg-manikuere",
        ),
        Svc(
            "Gel-Neumodellage", 90, "55.00", "Natürliche Länge oder Verlängerung.", "sg-gel-naegel"
        ),
        Svc("Pediküre", 60, "39.00", "Fußbad, Hornhaut, Pflege, Lack.", "sg-pedikuere"),
        Svc("Auffüllen Gel", 60, "39.00", "Alle drei bis vier Wochen.", "sg-gel-auffuellen"),
    ),
    offers=(
        Offer(
            "Mani + Pedi 59 €",
            "Beide Behandlungen in einem Termin — spart 9 €.",
            price="59.00",
            was="68.00",
            ends="week",
            response="show",
            photo="sg-manikuere",
            group="Diese Woche",
        ),
    ),
)

RUHEPOL = Biz(
    key="sg_ruhepol",
    label="Massagepraxis Ruhepol",
    btype="other",
    category="massage",
    district="burg-hoehscheid",
    street="Am Hang",
    house="12",
    lat="51.1520",
    lng="7.0800",
    phone="+49 221 4710133",
    accent="#0f766e",
    hero_photo="sg-massage",
    tagline="Wellness-Massagen zum Abschalten — Rücken, Ganzkörper, Hot Stone.",
    about=(
        "Praxis für Wohlfühlmassagen in Höhscheid: warme Räume, leise Musik, kein Zeitdruck. "
        "Wellness, keine Therapie — bei Beschwerden fragen Sie bitte Ihre Ärztin."
    ),
    hours="praxis",
    usp=("ruhe", "termin", "parken"),
    services=(
        Svc(
            "Rückenmassage",
            30,
            "35.00",
            "Nacken, Schultern, Rücken — mit warmem Öl.",
            "sg-ruecken-massage",
        ),
        Svc("Ganzkörpermassage", 60, "65.00", "Von Kopf bis Fuß, Druck nach Wunsch.", "sg-massage"),
        Svc("Hot-Stone-Massage", 75, "79.00", "Mit warmen Basaltsteinen.", "sg-hot-stone"),
    ),
    offers=(
        Offer(
            "Gutschein Ganzkörpermassage 59 €",
            "Zum Verschenken — ein Jahr gültig.",
            price="59.00",
            ends="none",
            response="show",
            photo="sg-massage",
            group="Dauerhaft",
        ),
        Offer(
            "Feierabend-Rücken 29 €",
            "Mo–Mi ab 17 Uhr — 30 Minuten Rückenmassage.",
            price="29.00",
            was="35.00",
            ends="week",
            response="show",
            photo="sg-ruecken-massage",
            group="Diese Woche",
        ),
    ),
)

SCHAUMKRONE = Biz(
    key="sg_schaumkrone",
    label="Seifenmanufaktur Schaumkrone",
    btype="retail",
    category="pflegeprodukte",
    district="graefrath",
    street="Tuchmacherweg",
    house="2",
    lat="51.2060",
    lng="7.0600",
    phone="+49 221 4710134",
    accent="#0891b2",
    hero_photo="pflege-bad-uebersicht",
    tagline="Seifen, feste Shampoos und Öle — von Hand gerührt in Gräfrath.",
    about=(
        "Kleine Siederei mit Laden: kaltgerührte Seifen aus Pflanzenölen, feste Shampoos ohne "
        "Plastik, Bartöl und Körperöl. Alles vegan, Düfte aus ätherischen Ölen."
    ),
    hours="laden",
    usp=("handarbeit", "vegan", "nachhaltig"),
    shelves=(
        Shelf(
            "Seifen & Pflege",
            "seifen-pflege",
            "pflegeprodukte",
            (
                Item(
                    "Seife Kohle & Minze",
                    "6.90",
                    "Für fettige Haut, 100 g.",
                    "seife-kohle-minze",
                    diets=("vegan",),
                    unit="100g",
                    content="1",
                ),
                Item(
                    "Seife Salzluft",
                    "6.50",
                    "Mit Meersalz, 100 g.",
                    "seife-salzluft-stueck",
                    diets=("vegan",),
                    unit="100g",
                    content="1",
                ),
                Item(
                    "Festes Shampoo Regen",
                    "9.90",
                    "Für normales Haar, ersetzt zwei Flaschen.",
                    "shampoo-regen-fest",
                    diets=("vegan",),
                    unit="100g",
                    content="0.6",
                ),
                Item(
                    "Bartöl Kiefer",
                    "14.90",
                    "Jojoba und Argan, 30 ml.",
                    "bartoel-kiefer-flakon",
                    diets=("vegan",),
                    unit="100ml",
                    content="0.3",
                ),
                Item(
                    "Körperöl Leinen",
                    "16.90",
                    "Mandel und Leinöl, 100 ml.",
                    "koerperlotion-leinen-flasche",
                    diets=("vegan",),
                    unit="100ml",
                    content="1",
                ),
            ),
        ),
    ),
    offers=(
        Offer(
            "3 Seifen 17,90 €",
            "Freie Auswahl aus allen Sorten — statt 20,30 €.",
            price="17.90",
            was="20.30",
            ends="week",
            response="show",
            photo="seife-dusche-stueck",
            group="Diese Woche",
            tags=("vegan", "nachhaltig"),
        ),
        Offer(
            "Siedekurs am Samstag",
            "Zwei Stunden, eigene Seife mit nach Hause — 6 Plätze.",
            price="45.00",
            ends="14d",
            response="inquire",
            photo="sg-seife-sieden",
            group="Saison",
        ),
    ),
)

BUSINESSES = (MESSERSCHARF, ROSENBLATT, PERLMUTT, RUHEPOL, SCHAUMKRONE)
