"""Раздел «Tiere & Tierbedarf» — демо-бизнесы Золингена (DCC)."""

from ..spec import Biz, Offer, Svc

SECTION = "tiere"

WUSCHELKOPF = Biz(
    key="sg_wuschelkopf",
    label="Hundesalon Wuschelkopf",
    btype="other",
    category="grooming",
    district="ohligs-aufderhoehe-merscheid",
    street="Lerchenstraße",
    house="14",
    lat="51.1620",
    lng="7.0150",
    phone="+49 212 5551401",
    accent="#0f766e",
    hero_photo="sg-tiere-hundesalon",
    tagline="Baden, Schneiden, Krallenpflege — in Ruhe und ohne Fließband.",
    about=(
        "Kleiner Salon in Ohligs mit zwei Pflegeplätzen. Jeder Hund bekommt seinen Termin "
        "allein, ängstliche Tiere lernen den Salon erst beim Schnuppertermin kennen."
    ),
    hours="studio",
    usp=("termin", "ruhe", "parken"),
    services=(
        Svc(
            "Komplettpflege kleiner Hund",
            90,
            "49.00",
            "Baden, Föhnen, Schneiden, Krallen und Ohren — bis 10 kg.",
            "sg-tiere-hundesalon",
        ),
        Svc(
            "Komplettpflege großer Hund",
            150,
            "79.00",
            "Baden, Föhnen, Schneiden, Krallen und Ohren — ab 25 kg.",
            "sg-tiere-hund-gross",
        ),
        Svc("Krallen schneiden", 15, "12.00", "Auch ohne Termin, wenn ein Platz frei ist.", ""),
        Svc(
            "Schnuppertermin",
            30,
            "0.00",
            "Für ängstliche Hunde: Salon kennenlernen, ohne Pflege.",
            "",
        ),
    ),
    offers=(
        Offer(
            "Welpen-Erstpflege 29 €",
            "Erster Salonbesuch für Welpen bis 6 Monate — sanft und kurz.",
            price="29.00",
            was="49.00",
            ends="14d",
            response="show",
            photo="sg-tiere-welpe",
            group="Neu bei uns",
        ),
    ),
)

BUSINESSES = (WUSCHELKOPF,)
