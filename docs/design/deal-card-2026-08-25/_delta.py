"""Артборд «Umsetzungsstand» — что утверждённый макет обещает и чего нет в кабинете.

Повод: сверка карточек всех архетипов с макетом (2026-08-26) дала 10 подтверждённых
расхождений. Ни одно из них не требует НОВОГО дизайна — все они про то, что
реализация не догнала макет от 2026-08-25. Поэтому артборд не переизобретает
карточку, а показывает дельту: слева фрагмент утверждённого макета, справа —
то, что владелец видит сегодня.

Фрагменты рисуются ТЕМИ ЖЕ функциями, что и карточки (_generate), иначе «до/после»
разъедется со стилем. Запуск: python3 docs/design/deal-card-2026-08-25/_delta.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _generate import (  # noqa: E402
    ACCENT,
    ACCENT_DARK,
    ACCENT_SOFT,
    BODY,
    BORDER,
    CANVAS,
    CARD_SHADOW,
    FAINT,
    HEAD,
    IC_CAL,
    IC_CHAT,
    INK,
    LINE,
    MUTED,
    NEW,
    NEW_SOFT,
    OK,
    OK_SOFT,
    TAIL,
    WARN,
    WARN_SOFT,
    Line,
    SideCard,
    icon,
    pill,
    render_calendar,
    render_line,
    render_side_card,
)

DIR = os.path.dirname(os.path.abspath(__file__))

# Три вида работы. Цвет фиолетовый в этом канвасе уже означает «нужно новое поле
# в БД» (легенда на артборде «Струкtur»), поэтому семантику не меняем.
WORK_RENDER = ("nur Anzeige", OK, OK_SOFT)
WORK_QUERY = ("Anzeige + Abfrage", ACCENT_DARK, ACCENT_SOFT)
WORK_DECIDE = ("Entscheidung nötig", NEW, NEW_SOFT)


def col_head():
    return (
        f'<div style="display: grid; grid-template-columns: 34px minmax(0, 1fr) 92px 118px 74px 104px; '
        f"gap: 10px; padding: 6px 0; border-bottom: 1px solid {LINE}; font-size: 10.5px; color: {MUTED}; "
        f'font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em">'
        f'<div>Nr.</div><div>Position</div><div style="text-align: right">MwSt.</div>'
        f'<div style="text-align: right">Einzel</div><div style="text-align: right">Menge</div>'
        f'<div style="text-align: right">Summe</div></div>'
    )


def lines_block(lines):
    for i, ln in enumerate(lines, start=1):
        ln.index = str(i)
    return col_head() + "".join(render_line(ln) for ln in lines)


def head_block(number, pay_pill=None, meta=""):
    pill_html = f"          {pill(pay_pill[0], pay_pill[1], pay_pill[2])}\n" if pay_pill else ""
    return f"""<div style="display: flex; flex-direction: column; gap: 5px">
        <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap">
          <div style="font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums">{number}</div>
{pill_html}        </div>
        <div style="font-size: 12px; color: {MUTED}">{meta}</div>
      </div>"""


def pay_block(status, color, note, method):
    method_html = (
        f'<div style="font-size: 12.5px; color: {BODY}">{method}</div>'
        if method
        else f'<div style="font-size: 12.5px; color: {FAINT}">— keine Zahlart genannt —</div>'
    )
    return f"""<div style="display: flex; flex-direction: column; gap: 6px">
        <div style="display: flex; align-items: center; gap: 8px">
          <span style="width: 9px; height: 9px; border-radius: 99px; background: {color}"></span>
          <div style="font-size: 14px; font-weight: 600">{status}</div>
        </div>
        <div style="font-size: 12.5px; color: {MUTED}">{note}</div>
        {method_html}
      </div>"""


def customer_block(initials, name, sub):
    sub_html = (
        f'<div style="font-size: 12.5px; color: {MUTED}">{sub}</div>'
        if sub
        else f'<div style="font-size: 12.5px; color: {FAINT}">— keine Angaben zum Kunden —</div>'
    )
    return f"""<div style="display: flex; align-items: center; gap: 12px">
        <div style="width: 40px; height: 40px; border-radius: 99px; background: {ACCENT_SOFT}; color: {ACCENT_DARK}; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 700">{initials}</div>
        <div style="flex-grow: 1; min-width: 0">
          <div style="font-size: 15px; font-weight: 700; color: {ACCENT}">{name}</div>
          {sub_html}
        </div>
        {icon(IC_CHAT, MUTED, 17)}
      </div>"""


def disc_editor(mode_percent, value, effect):
    """Редактор скидки: с переключателем «% | €» и без него."""
    if mode_percent:
        toggle = f"""<div style="display: flex; align-items: center; gap: 3px; padding: 3px; border-radius: 99px; background: {CANVAS}">
            <div style="height: 24px; padding: 0 10px; border-radius: 99px; background: #FFFFFF; color: {INK}; display: flex; align-items: center; font-size: 12px; font-weight: 700; box-shadow: 0 2px 6px rgba(22, 24, 29, 0.06)">%</div>
            <div style="height: 24px; padding: 0 10px; border-radius: 99px; color: {MUTED}; display: flex; align-items: center; font-size: 12px; font-weight: 600">€</div>
          </div>"""
    else:
        toggle = f'<div style="font-size: 12px; color: {FAINT}">nur EUR</div>'
    return f"""<div style="display: flex; flex-direction: column; gap: 8px">
        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap">
          <div style="font-size: 13px; font-weight: 700">Rabatt</div>
          <div style="height: 30px; width: 88px; border: 1px solid {BORDER}; border-radius: 10px; display: flex; align-items: center; padding: 0 10px; font-size: 13px; font-variant-numeric: tabular-nums; background: #FFFFFF">{value}</div>
          {toggle}
          <div style="height: 30px; padding: 0 12px; border-radius: 99px; background: {CANVAS}; color: {BODY}; display: flex; align-items: center; font-size: 12.5px; font-weight: 600">Anwenden</div>
        </div>
        <div style="font-size: 12px; color: {MUTED}">{effect}</div>
      </div>"""


def day_list_flat():
    """Дневной список без фильтра по мастеру и без шкалы — то, что в кабинете сегодня."""
    rows = ""
    for t, who in [
        ("12:00–13:00", "Lea — Familie Klein"),
        ("14:00–15:15", "Mara — Lena Kraft"),
        ("19:00–20:00", "Lea — Sara Hoff"),
    ]:
        rows += (
            f'<div style="display: flex; gap: 10px; font-size: 13px; padding: 6px 0; '
            f'border-bottom: 1px solid {LINE}">'
            f'<div style="color: {MUTED}; font-variant-numeric: tabular-nums; min-width: 92px">{t}</div>'
            f"<div style=\"color: {BODY}\">{who}</div></div>"
        )
    return f"""<div style="display: flex; flex-direction: column; gap: 6px">
        <div style="font-size: 14px; font-weight: 700">Kalender</div>
        {rows}
      </div>"""


# --- содержание дельты ----------------------------------------------------------
# (номер, заголовок, архетип, вид работы, фрагмент «макет», фрагмент «сегодня»,
#  подпись слева, подпись справа)
ROWS = [
    (
        "1",
        "Kurtaxe: Einzelpreis und Menge",
        "Hotel · Buchung",
        WORK_RENDER,
        lines_block([Line("6×", "Kurtaxe", "ohne MwSt.", "—", "2,50 €", "15,00 €")]),
        lines_block([Line("—", "Kurtaxe", "ohne MwSt.", "—", "—", "3,00 €")]),
        "2,50 € je Person und Nacht × 6 — die Summe ist nachrechenbar.",
        "Nur die Summe. Woraus sie entsteht, ist nicht zu sehen.",
    ),
    (
        "2",
        "Rabatt in der Position sichtbar",
        "Hotel · Buchung",
        WORK_RENDER,
        lines_block(
            [
                Line(
                    "3 Nächte",
                    "Doppelzimmer Seeblick",
                    "pro Nacht",
                    "7 %",
                    "116,10 €",
                    "348,30 €",
                    strike="129,00 €",
                    disc_note="Rabatt −10 % · Frühbucher",
                )
            ]
        ),
        lines_block(
            [Line("3 Nächte", "Doppelzimmer Seeblick", "pro Nacht", "7 %", "129,00 €", "387,00 €")]
        ),
        "Bereich «Position»: durchgestrichener alter Preis direkt in der Zeile.",
        "Gleiche Zeile für «Position» und «ganze Buchung» — die Auswahl ändert optisch nichts.",
    ),
    (
        "3",
        "Rabatt in Prozent",
        "alle Verkaufsarten",
        WORK_DECIDE,
        disc_editor(True, "10 %", "10 % auf die Übernachtung — in der Position verrechnet"),
        disc_editor(False, "38,70 €", "Prozent muss der Betreiber selbst ausrechnen"),
        "Umschalter «% | €»: eingegeben wird, was der Betreiber im Kopf hat.",
        "Nur Euro. «10 % auf den Warenkorb» wird zur Kopfrechnung.",
    ),
    (
        "4",
        "Offene Zahlung im Kopf der Karte",
        "Hofladen · Bestellung",
        WORK_RENDER,
        head_block(
            "#O-9PL4XC",
            ("Vorkasse offen", WARN, WARN_SOFT),
            "Eingegangen 23.08. 18:05 · Abholung Mi 27.08.",
        ),
        head_block("#O-9PL4XC", None, "Eingegangen 23.08. 18:05 · Abholung Mi 27.08."),
        "Geld zuerst: offene Vorkasse steht neben der Nummer.",
        "Kein Geldsignal — nur der Bearbeitungsstatus «Neu» weiter unten.",
    ),
    (
        "5",
        "Zahlart statt «Offen»",
        "Hofladen · Bestellung",
        WORK_RENDER,
        pay_block(
            "Vorkasse offen",
            WARN,
            "Überweisung 52,80 € · Verwendungszweck O-9PL4XC",
            "Vorkasse · Bankverbindung im Bestätigungs-Mail",
        ),
        pay_block("Offen", MUTED, "52,80 €", ""),
        "Der Betreiber weiß, worauf er wartet — und wo die Bankdaten stehen.",
        "«Offen» sagt nicht, ob Vorkasse, Barzahlung oder Online erwartet wird.",
    ),
    (
        "6",
        "Kunde: Segment und Wiederkehr",
        "Hofladen · Bestellung",
        WORK_QUERY,
        customer_block("MK", "Miriam Kley", "Abo-Kundin · jede Woche"),
        customer_block("MK", "Miriam Kley", ""),
        "Stammkunde ist sofort erkennbar — die Daten liegen bereits im CRM.",
        "Erstkäufer und Stammkunde sehen gleich aus.",
    ),
    (
        "7",
        "Karte «Aufenthalt» in der Schiene",
        "Hotel · Buchung",
        WORK_RENDER,
        render_side_card(
            SideCard(
                IC_CAL,
                "Aufenthalt",
                [
                    ("Zimmer", "204 · Seeblick"),
                    ("Anreise", "Fr 12.09. ab 15:00"),
                    ("Meldeschein", "ausgefüllt"),
                ],
                "Zimmer wechseln →",
            )
        ),
        f'<div style="background: #FFFFFF; border-radius: 20px; box-shadow: {CARD_SHADOW}; padding: 16px 18px; '
        f'display: flex; flex-direction: column; gap: 8px">'
        f'<div style="font-size: 13.5px; color: {FAINT}">— keine Karte —</div>'
        f'<div style="font-size: 12.5px; color: {BODY}">Zimmer nur als Kürzel im Kopf; wechseln geht erst '
        f'nach dem Aufklappen von «✏️ Buchung bearbeiten».</div></div>',
        "Zimmer, Anreise, Meldeschein und ein direkter Weg zum Zimmerwechsel.",
        "Der Zimmerwechsel ist zwei Klicks tief in einem Formular versteckt.",
    ),
    (
        "8",
        "Erinnerung an den Kunden",
        "Friseur · Termin",
        WORK_RENDER,
        render_side_card(
            SideCard(
                IC_CAL,
                "Termin",
                [
                    ("Wann", "Do 04.09. · 14:00"),
                    ("Wer", "Mara · Stuhl 2"),
                    ("Erinnerung", "gesendet 03.09."),
                ],
                "Verschieben →",
            )
        ),
        render_side_card(
            SideCard(
                IC_CAL,
                "Termin verschieben",
                ["Neues Datum und Uhrzeit wählen"],
                "",
            )
        ),
        "Der Betreiber sieht, ob die Erinnerung raus ist — das Feld existiert bereits.",
        "Nur das Verschiebe-Formular. Ob erinnert wurde, steht nirgends.",
    ),
    (
        "9",
        "Tagesplan des Mitarbeiters",
        "Friseur · Termin",
        WORK_QUERY,
        render_calendar(
            {
                "title": "Tagesplan · Mara, Stuhl 2",
                "period": "Do 04.09.",
                "cells": [
                    {"label": "9", "state": "free"},
                    {"label": "10", "state": "busy"},
                    {"label": "11", "state": "busy"},
                    {"label": "12", "state": "free"},
                    {"label": "13", "state": "free"},
                    {"label": "14", "state": "this"},
                    {"label": "15", "state": "this"},
                    {"label": "16", "state": "busy"},
                    {"label": "17", "state": "free"},
                    {"label": "18", "state": "free"},
                ],
                "this_label": "dieser Termin",
                "note": "14:00–15:15 · 75 Min. inkl. Kur",
                "link": "Tagesplan öffnen →",
            }
        ),
        day_list_flat(),
        "Stundenskala nur für Mara und Stuhl 2, dieser Termin hervorgehoben.",
        "Liste aller Termine des Salons — das Fenster um diesen Termin ist nicht ablesbar.",
    ),
]


def render_row(num, title, arche, work, left, right, left_note, right_note):
    label, color, bg = work
    return f"""    <div style="background: #FFFFFF; border-radius: 20px; box-shadow: {CARD_SHADOW}; padding: 16px 20px 18px; display: flex; flex-direction: column; gap: 12px">
      <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap">
        <div style="width: 26px; height: 26px; border-radius: 99px; background: {CANVAS}; color: {MUTED}; display: flex; align-items: center; justify-content: center; font-size: 12.5px; font-weight: 700">{num}</div>
        <div style="font-size: 16px; font-weight: 700">{title}</div>
        <div style="font-size: 12.5px; color: {MUTED}">{arche}</div>
        <div style="flex-grow: 1"></div>
        {pill(label, color, bg)}
      </div>
      <div style="display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 18px; align-items: start">
        <div style="display: flex; flex-direction: column; gap: 8px; min-width: 0">
          <div style="font-size: 11px; font-weight: 700; color: {OK}; text-transform: uppercase; letter-spacing: 0.04em">Genehmigter Entwurf</div>
          <div style="background: {CANVAS}; border-radius: 14px; padding: 12px 14px; min-width: 0">{left}</div>
          <div style="font-size: 12.5px; color: {BODY}">{left_note}</div>
        </div>
        <div style="display: flex; flex-direction: column; gap: 8px; min-width: 0">
          <div style="font-size: 11px; font-weight: 700; color: {WARN}; text-transform: uppercase; letter-spacing: 0.04em">Kabinett heute</div>
          <div style="background: {CANVAS}; border-radius: 14px; padding: 12px 14px; min-width: 0">{right}</div>
          <div style="font-size: 12.5px; color: {BODY}">{right_note}</div>
        </div>
      </div>
    </div>
"""


def render_delta():
    rows = "".join(render_row(*r) for r in ROWS)
    legend = (
        f'<div style="display: flex; align-items: center; gap: 16px; flex-wrap: wrap; font-size: 12.5px; color: {BODY}">'
        f'<span style="display: flex; align-items: center; gap: 6px">{pill(*WORK_RENDER)} Felder sind da — es fehlt nur die Anzeige</span>'
        f'<span style="display: flex; align-items: center; gap: 6px">{pill(*WORK_QUERY)} Anzeige plus eine zusätzliche Abfrage</span>'
        f'<span style="display: flex; align-items: center; gap: 6px">{pill(*WORK_DECIDE)} offene Frage an den Eigentümer</span>'
        f"</div>"
    )
    return f"""{HEAD}<div style="width: 1460px; background: {CANVAS}; color: {INK}; box-sizing: border-box; padding: 26px 28px 30px; display: flex; flex-direction: column; gap: 14px">

  <div style="display: flex; flex-direction: column; gap: 8px">
    <div style="font-size: 26px; font-weight: 700">Umsetzungsstand der Verkaufskarte</div>
    <div style="font-size: 14px; color: {BODY}; max-width: 900px; line-height: 1.55">
      Der Abgleich aller Archetypen mit dem am 25.08. genehmigten Entwurf hat neun offene Punkte ergeben.
      Keiner davon ist ein neuer Entwurf: Alles unten steht bereits im genehmigten Layout — die Umsetzung ist
      an diesen Stellen noch nicht nachgezogen. Links der Entwurf, rechts die Karte, wie sie heute im Kabinett aussieht.
    </div>
    {legend}
  </div>

{rows}
  <div style="background: #FFFFFF; border-radius: 20px; box-shadow: {CARD_SHADOW}; padding: 16px 20px; display: flex; flex-direction: column; gap: 8px">
    <div style="font-size: 15px; font-weight: 700">Was die Umsetzung kostet</div>
    <div style="font-size: 13.5px; color: {BODY}; line-height: 1.6">
      Sieben der neun Punkte sind reine Anzeige oder Anzeige plus eine Abfrage — die Daten liegen bereits in der
      Datenbank: <span style="color: {INK}; font-weight: 600">adults · nights</span> für die Kurtaxe,
      <span style="color: {INK}; font-weight: 600">discount_scope</span> für den Rabatt in der Zeile,
      <span style="color: {INK}; font-weight: 600">payment_method</span> für die Zahlart,
      <span style="color: {INK}; font-weight: 600">room</span> für den Aufenthalt,
      <span style="color: {INK}; font-weight: 600">reminder_sent_at</span> für die Erinnerung.
      Keine Migration nötig.
    </div>
    <div style="font-size: 13.5px; color: {BODY}; line-height: 1.6">
      Offen ist ein Punkt: Der Prozentsatz eines Rabatts wird heute nirgends gespeichert — gespeichert werden nur Cent.
      Entweder ein zusätzliches Feld je Verkaufsart (additive Migration, der Prozentsatz überlebt spätere Änderungen
      der Positionen), oder Prozent nur als Eingabehilfe ohne Speicherung (keine Migration, nach dem Speichern steht
      wieder ein Eurobetrag da).
    </div>
  </div>

</div>
{TAIL}"""


def main():
    path = os.path.join(DIR, "Umsetzung.dc.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_delta())
    print(f"Umsetzung.dc.html записан ({len(ROWS)} пунктов) в {DIR}")


if __name__ == "__main__":
    main()
