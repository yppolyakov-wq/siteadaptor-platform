"""Страница сравнения: та же карточка сегодня и после доработки — ЦЕЛИКОМ.

Повод: сверка карточек всех архетипов с макетом (2026-08-26) дала девять расхождений.
Ни одно не требует нового дизайна — всё уже стоит в утверждённом макете от 25.08,
реализация просто не догнала. Поэтому здесь не набор фрагментов, а те же самые
страницы в двух состояниях: слева карточка, как её видит владелец в кабинете сегодня,
справа — она же по макету.

«Сегодняшняя» версия строится из ТОЙ ЖЕ карточки (deepcopy) — меняются только те места,
которые реально отличаются, и суммы пересчитаны так, чтобы арифметика сходилась.

Запуск: python3 docs/design/deal-card-2026-08-25/_delta.py
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _generate import CARDS, IC_CAL, SideCard, render  # noqa: E402

DIR = os.path.dirname(os.path.abspath(__file__))


def as_today(card):
    """Снимает пометки «neu: Feld nötig» — на карточке «сегодня» их быть не может."""
    card.variant = "heute"
    card.ext_new = False
    card.totals_new = False
    card.invoice_new = False
    card.head_badge = ""
    return card


def by_file(name):
    for c in CARDS:
        if c.file == name:
            return c
    raise KeyError(name)


def line_by_title(card, needle):
    for ln in card.lines:
        if needle in ln.title:
            return ln
    raise KeyError(needle)


def hotel_heute():
    """Бронь номера: без базы Kurtaxe, без скидки в строке, без карточки «Aufenthalt».

    Суммы: строки дают 489,00 € (проживание идёт по цене ДО скидки — так сегодня
    считает deal_lines), скидка уходит отдельной строкой −38,70 €, итог тот же 450,30 €.
    """
    c = as_today(copy.deepcopy(by_file("Hotel.dc.html")))
    c.file = "HotelHeute.dc.html"

    zimmer = line_by_title(c, "Doppelzimmer")
    zimmer.unit = "129,00 €"
    zimmer.total = "387,00 €"
    zimmer.strike = ""
    zimmer.disc_note = ""

    kurtaxe = line_by_title(c, "Kurtaxe")
    kurtaxe.unit = "—"
    kurtaxe.qty = "—"

    c.totals = [
        ("Zwischensumme", "489,00 €"),
        ("Rabatt auf die Buchung", "−38,70 €"),
        ('davon Kurtaxe <span style="color: #B3B8C2">ohne MwSt.</span>', "15,00 €"),
        ("Netto (steuerpflichtig)", "405,41 €"),
        ("MwSt. 7 %", "27,50 €"),
        ("MwSt. 19 %", "2,39 €"),
    ]
    c.totals_new = False
    # Сегодня выбор области ничего не меняет в показе: скидка в любом случае уходит
    # отдельной строкой в суммы — подпись под редактором должна говорить именно это.
    c.disc_scope = "order"
    c.disc_value = "38,70 €"
    c.disc_reason = "Frühbucher"
    c.customer_sub = ""
    c.side_cards = []
    c.height = 1000
    return c


def hofladen_heute():
    """Заказ: без денежного бейджа в голове, «Offen» без названия способа, клиент без сегмента."""
    c = as_today(copy.deepcopy(by_file("Hofladen.dc.html")))
    c.file = "HofladenHeute.dc.html"
    c.pay_pill = None
    c.pay_status = "Offen"
    c.pay_color = "#6A7180"
    c.pay_note = "52,80 €"
    c.pay_method = ""
    c.customer_sub = ""
    c.height = 1020
    return c


def friseur_heute():
    """Запись: без строки «Erinnerung», календарь — плоский список всех записей дня."""
    c = as_today(copy.deepcopy(by_file("Friseur.dc.html")))
    c.file = "FriseurHeute.dc.html"
    c.customer_sub = ""
    c.calendar = None
    c.side_cards = [
        SideCard(
            IC_CAL,
            "Termin verschieben",
            ["Neues Datum und Uhrzeit wählen"],
            "",
        ),
        SideCard(
            IC_CAL,
            "Kalender",
            [
                "12:00–13:00 · Lea — Familie Klein",
                "14:00–15:15 · Mara — Lena Kraft",
                "19:00–20:00 · Lea — Sara Hoff",
            ],
            "",
        ),
    ]
    c.height = 1000
    return c


HEUTE = [hotel_heute, hofladen_heute, friseur_heute]


# Пары для страницы сравнения. Артборды канваса уникальны по имени файла, а
# Hotel/Hofladen/Friseur уже заняты страницей «Архетипы», поэтому версия «по макету»
# кладётся рядом отдельным файлом — это точная копия той же карточки.
PAIRS = [
    (hotel_heute, "Hotel.dc.html", "HotelNeu.dc.html"),
    (hofladen_heute, "Hofladen.dc.html", "HofladenNeu.dc.html"),
    (friseur_heute, "Friseur.dc.html", "FriseurNeu.dc.html"),
]


def main():
    written = 0
    for build, src, neu in PAIRS:
        heute = build()
        with open(os.path.join(DIR, heute.file), "w", encoding="utf-8") as fh:
            fh.write(render(heute))
        entwurf = copy.deepcopy(by_file(src))
        entwurf.file = neu
        with open(os.path.join(DIR, neu), "w", encoding="utf-8") as fh:
            fh.write(render(entwurf))
        written += 2
        print(f"{heute.file:24} ↔ {neu}")
    print(f"\n{written} артбордов пары «сегодня ↔ по макету» записаны в {DIR}")


if __name__ == "__main__":
    main()
