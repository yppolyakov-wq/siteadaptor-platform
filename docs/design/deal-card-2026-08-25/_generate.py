"""Генератор артбордов «карточка сделки» по архетипам (ТЗ владельца 2026-08-25).

Один шаблон + данные на каждый архетип → 15 файлов .dc.html в одном стиле
(«Karten & Luft»). Запуск: python3 docs/design/deal-card-2026-08-25/_generate.py

Правки дизайна делаем ЗДЕСЬ и перегенерируем, иначе карточки разъедутся.
"""

import os
from dataclasses import dataclass, field

DIR = os.path.dirname(os.path.abspath(__file__))

# --- токены утверждённого стиля -------------------------------------------------
INK = "#16181D"
MUTED = "#6A7180"
FAINT = "#9BA0AB"
LINE = "#F0F1F4"
BORDER = "#E7E9EE"
BODY = "#444A56"
CANVAS = "#F2F4F7"
CARD_SHADOW = "0 6px 18px rgba(22, 24, 29, 0.05)"
ACCENT = "#4F46E5"
ACCENT_DARK = "#4338CA"
ACCENT_SOFT = "#EEF0FF"
OK = "#0A8A5F"
OK_SOFT = "#F0FBF6"
WARN = "#C77414"
WARN_SOFT = "#FDF6EC"
NEW = "#7A5AF8"
NEW_SOFT = "#F1EEFE"

HEAD = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&amp;display=swap">
  <style>
    body { margin: 0; font-family: 'Instrument Sans', system-ui, sans-serif; }
    a { color: #4F46E5; } a:hover { color: #4338CA; }
  </style>
</helmet>
"""
TAIL = "</x-dc>\n</body>\n</html>\n"


def badge_new(text="neu: Feld nötig"):
    return (
        f'<span style="font-size: 10.5px; font-weight: 600; color: {NEW}; background: {NEW_SOFT}; '
        f'border-radius: 99px; padding: 3px 8px; white-space: nowrap">{text}</span>'
    )


def pill(text, color, bg):
    return (
        f'<span style="font-size: 11px; font-weight: 600; color: {color}; background: {bg}; '
        f'border-radius: 99px; padding: 4px 10px; white-space: nowrap">{text}</span>'
    )


def icon(path, stroke=MUTED, size=17, width="1.8"):
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{stroke}" '
        f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round">{path}</svg>'
    )


IC_CHEVRON_DOWN = '<path d="M6 9l6 6 6-6"></path>'
IC_CHEVRON_RIGHT = '<path d="M9 5l7 7-7 7"></path>'
IC_PLUS = '<path d="M12 6v12M6 12h12"></path>'
IC_DOC = '<path d="M7 3h7l5 5v13H7z"></path><path d="M14 3v5h5"></path><path d="M10 13h6M10 17h4"></path>'
IC_CHAT = '<path d="M20 12a7.5 7.5 0 0 1-10.9 6.7L4 20l1.4-4.8A7.5 7.5 0 1 1 20 12z"></path>'
IC_PENCIL = '<path d="M4 17.5L14 5l3 2.5L8 19l-4.5 1z"></path>'
IC_TRUCK = (
    '<path d="M3 7h11v9H3z"></path><path d="M14 10h4l3 3v3h-7z"></path>'
    '<circle cx="7" cy="18" r="1.8"></circle><circle cx="17" cy="18" r="1.8"></circle>'
)
IC_LINK = '<path d="M9 7h6a4 4 0 0 1 0 8h-2"></path><path d="M15 17H9a4 4 0 0 1 0-8h2"></path>'
IC_CAL = (
    '<rect x="4" y="6" width="16" height="14" rx="2"></rect><path d="M4 10h16M8 4v4M16 4v4"></path>'
)


@dataclass
class Line:
    qty: str
    title: str
    note: str = ""
    vat: str = ""
    unit: str = ""
    total: str = ""
    negative: bool = False


@dataclass
class SideCard:
    icon: str
    title: str
    rows: list  # список (label, value) или строк
    link: str = ""


@dataclass
class Card:
    file: str
    archetype: str  # подпись типа бизнеса (для крошек)
    business: str
    crumbs: str
    kind_label: str  # «Bestellung», «Buchung», …
    number: str
    ext_number: str
    ext_new: bool  # нужен ли бейдж «neu: Feld nötig» у внешнего номера
    status: str
    status_color: str
    status_next: str
    meta: str  # строка под номером
    pay_pill: str  # (текст, цвет, фон) или None
    lines: list
    totals: list  # [(label, value, bold?)]
    net_first: bool
    totals_new: bool  # бейдж «neu» у блока итогов
    total_label: str
    total_value: str
    pay_status: str
    pay_color: str
    pay_note: str
    pay_method: str
    invoice_label: str
    invoice_new: bool
    invoice_langs: tuple
    invoice_note: str
    customer_name: str
    customer_initials: str
    customer_sub: str
    customer_mail: str
    customer_phone: str
    contact_label: str
    side_cards: list = field(default_factory=list)
    delivery: dict = None
    height: int = 1080
    head_badge: str = ""


def render_line(ln):
    color = OK if ln.negative else INK
    note = (
        f' <span style="color: {MUTED}; font-size: 12.5px">· {ln.note}</span>' if ln.note else ""
    )
    return f"""        <div style="display: grid; grid-template-columns: 54px minmax(0, 1fr) 92px 104px 104px; gap: 10px; padding: 11px 0; border-bottom: 1px solid {LINE}; align-items: center; font-size: 14px">
          <div style="font-variant-numeric: tabular-nums; color: {MUTED}">{ln.qty}</div>
          <div>{ln.title}{note}</div>
          <div style="text-align: right; color: {MUTED}; font-variant-numeric: tabular-nums">{ln.vat}</div>
          <div style="text-align: right; font-variant-numeric: tabular-nums">{ln.unit}</div>
          <div style="text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; color: {color}">{ln.total}</div>
        </div>
"""


def render_side_card(sc):
    rows = ""
    for r in sc.rows:
        if isinstance(r, tuple):
            rows += f"""          <div style="display: flex; align-items: baseline; gap: 8px; font-size: 13.5px">
            <div style="color: {MUTED}; min-width: 96px">{r[0]}</div>
            <div style="flex-grow: 1; color: {BODY}">{r[1]}</div>
          </div>
"""
        else:
            rows += f'          <div style="font-size: 13.5px; color: {BODY}">{r}</div>\n'
    link = (
        f'          <div style="font-size: 13px; color: {ACCENT}; font-weight: 600; padding-top: 2px">{sc.link}</div>\n'
        if sc.link
        else ""
    )
    return f"""      <div style="background: #FFFFFF; border-radius: 20px; box-shadow: {CARD_SHADOW}; padding: 16px 18px; display: flex; flex-direction: column; gap: 8px">
        <div style="display: flex; align-items: center; gap: 10px">
          {icon(sc.icon)}
          <div style="font-size: 15px; font-weight: 700">{sc.title}</div>
        </div>
{rows}{link}      </div>
"""


def render(card: Card) -> str:
    lines_html = "".join(render_line(ln) for ln in card.lines)

    totals_html = ""
    for label, value in card.totals:
        totals_html += f"""          <div style="display: flex; align-items: center; font-size: 14px">
            <div style="flex-grow: 1; color: {MUTED}">{label}</div>
            <div style="font-variant-numeric: tabular-nums">{value}</div>
          </div>
"""

    langs = ""
    for i, lg in enumerate(card.invoice_langs):
        if i == 0:
            langs += f'                <div style="height: 30px; padding: 0 12px; border-radius: 99px; background: #FFFFFF; color: {INK}; display: flex; align-items: center; font-size: 12.5px; font-weight: 700; box-shadow: 0 2px 6px rgba(22, 24, 29, 0.06)">{lg}</div>\n'
        else:
            langs += f'                <div style="height: 30px; padding: 0 12px; border-radius: 99px; color: {MUTED}; display: flex; align-items: center; font-size: 12.5px; font-weight: 600">{lg}</div>\n'

    delivery_html = ""
    if card.delivery:
        d = card.delivery
        delivery_html = f"""      <div style="background: #FFFFFF; border-radius: 20px; box-shadow: {CARD_SHADOW}; padding: 16px 18px; display: flex; flex-direction: column; gap: 12px">
        <div style="display: flex; align-items: center; gap: 10px">
          {icon(IC_TRUCK)}
          <div style="font-size: 15px; font-weight: 700; flex-grow: 1">{d["title"]}</div>
          {pill(d["state"], d["state_color"], d["state_bg"])}
        </div>
        <div style="font-size: 13.5px; color: {BODY}; line-height: 1.5">{d["address"]}</div>
        <div style="display: flex; flex-direction: column; gap: 6px">
          <div style="font-size: 12px; color: {MUTED}; font-weight: 600">{d["field_label"]}</div>
          <div style="height: 38px; border: 1px solid {BORDER}; border-radius: 10px; display: flex; align-items: center; padding: 0 10px; font-size: 13.5px; color: {FAINT}">{d["field_hint"]}</div>
        </div>
        <div style="height: 38px; border-radius: 99px; background: {CANVAS}; color: {BODY}; display: flex; align-items: center; justify-content: center; gap: 8px; font-size: 13px; font-weight: 600">
          {icon(IC_DOC, BODY, 16, "1.9")}
          {d["doc"]}
        </div>
      </div>
"""

    side_html = "".join(render_side_card(sc) for sc in card.side_cards)
    head_badge = f"            {badge_new(card.head_badge)}\n" if card.head_badge else ""
    ext_badge = f"            {badge_new()}\n" if card.ext_new else ""
    totals_badge = f"            {badge_new()}\n" if card.totals_new else ""
    invoice_badge = f"              {badge_new()}\n" if card.invoice_new else ""
    pay_pill_html = (
        f"            {pill(card.pay_pill[0], card.pay_pill[1], card.pay_pill[2])}\n"
        if card.pay_pill
        else ""
    )
    total_style = "font-size: 21px" if not card.net_first else "font-size: 21px"

    return f"""{HEAD}<div style="width: 1180px; height: {card.height}px; background: {CANVAS}; color: {INK}; box-sizing: border-box; padding: 20px 24px; display: flex; flex-direction: column; gap: 14px; overflow: hidden">

  <div style="display: flex; align-items: center; gap: 10px">
    <div style="font-size: 13px; color: {MUTED}">{card.business}</div>
    {icon(IC_CHEVRON_RIGHT, "#B3B8C2", 14, "2")}
    <div style="font-size: 13px; color: {MUTED}">{card.crumbs}</div>
  </div>

  <div style="display: grid; grid-template-columns: minmax(0, 1fr) 380px; gap: 16px; align-items: start">

    <div style="display: flex; flex-direction: column; gap: 14px; min-width: 0">

      <div style="background: #FFFFFF; border-radius: 20px; box-shadow: {CARD_SHADOW}; padding: 18px 20px; display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 20px; align-items: start">
        <div style="display: flex; flex-direction: column; gap: 8px; min-width: 0">
          <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap">
            <div style="font-size: 26px; font-weight: 700; font-variant-numeric: tabular-nums">{card.number}</div>
{pay_pill_html}{head_badge}          </div>
          <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap">
            <span style="font-size: 12.5px; color: {MUTED}">Externe Nr.</span>
            <div style="height: 34px; min-width: 180px; border: 1px solid {BORDER}; border-radius: 10px; display: flex; align-items: center; padding: 0 10px; font-size: 13.5px; font-variant-numeric: tabular-nums; background: #FFFFFF">{card.ext_number}</div>
            <div style="height: 34px; padding: 0 12px; border-radius: 10px; background: {CANVAS}; color: {BODY}; display: flex; align-items: center; font-size: 13px; font-weight: 600">Speichern</div>
{ext_badge}          </div>
          <div style="font-size: 12.5px; color: {MUTED}">{card.meta}</div>
        </div>

        <div style="display: flex; flex-direction: column; gap: 8px">
          <div style="font-size: 12px; color: {MUTED}; font-weight: 600">Status · {card.kind_label}</div>
          <div style="height: 44px; border: 1px solid {BORDER}; border-radius: 12px; display: flex; align-items: center; gap: 10px; padding: 0 12px; background: #FFFFFF">
            <span style="width: 9px; height: 9px; border-radius: 99px; background: {card.status_color}"></span>
            <span style="flex-grow: 1; font-size: 14.5px; font-weight: 600">{card.status}</span>
            {icon(IC_CHEVRON_DOWN, MUTED, 16, "2")}
          </div>
          <div style="font-size: 12px; color: {MUTED}">Nächster Schritt: {card.status_next}</div>
        </div>
      </div>

      <div style="background: #FFFFFF; border-radius: 20px; box-shadow: {CARD_SHADOW}; padding: 16px 20px 18px; display: flex; flex-direction: column; gap: 4px">
        <div style="display: flex; align-items: center; gap: 10px; padding-bottom: 8px">
          <div style="font-size: 15px; font-weight: 700; flex-grow: 1">Positionen</div>
          <div style="height: 32px; padding: 0 12px; border-radius: 99px; background: {CANVAS}; color: {BODY}; display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600">
            {icon(IC_PLUS, BODY, 15, "2")}
            Position
          </div>
        </div>

        <div style="display: grid; grid-template-columns: 54px minmax(0, 1fr) 92px 104px 104px; gap: 10px; padding: 8px 0; border-bottom: 1px solid {LINE}; font-size: 11.5px; color: {MUTED}; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em">
          <div>Menge</div><div>Position</div><div style="text-align: right">MwSt.</div><div style="text-align: right">Einzel</div><div style="text-align: right">Summe</div>
        </div>

{lines_html}
        <div style="margin-top: 10px; padding-top: 12px; border-top: 1px solid {BORDER}; display: flex; flex-direction: column; gap: 7px">
          <div style="display: flex; align-items: center; gap: 8px; padding-bottom: 2px">
            <div style="font-size: 12px; color: {MUTED}; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; flex-grow: 1">Summen</div>
{totals_badge}          </div>
{totals_html}          <div style="display: flex; align-items: center; padding-top: 8px; border-top: 1px solid {LINE}">
            <div style="flex-grow: 1; font-size: 15.5px; font-weight: 700">{card.total_label}</div>
            <div style="{total_style}; font-weight: 700; font-variant-numeric: tabular-nums">{card.total_value}</div>
          </div>
        </div>
      </div>

      <div style="background: #FFFFFF; border-radius: 20px; box-shadow: {CARD_SHADOW}; padding: 16px 20px 18px; display: flex; flex-direction: column; gap: 14px">
        <div style="display: flex; align-items: center; gap: 10px">
          <div style="font-size: 15px; font-weight: 700; flex-grow: 1">Zahlung</div>
          <div style="font-size: 12.5px; color: {MUTED}">{card.pay_method}</div>
        </div>

        <div style="display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 16px; align-items: start">
          <div style="display: flex; flex-direction: column; gap: 6px">
            <div style="font-size: 12px; color: {MUTED}; font-weight: 600">Zahlungsstatus</div>
            <div style="height: 44px; border: 1px solid {BORDER}; border-radius: 12px; display: flex; align-items: center; gap: 10px; padding: 0 12px">
              <span style="width: 9px; height: 9px; border-radius: 99px; background: {card.pay_color}"></span>
              <span style="flex-grow: 1; font-size: 14.5px; font-weight: 600">{card.pay_status}</span>
              {icon(IC_CHEVRON_DOWN, MUTED, 16, "2")}
            </div>
            <div style="font-size: 12px; color: {MUTED}">{card.pay_note}</div>
          </div>

          <div style="display: flex; flex-direction: column; gap: 8px">
            <div style="font-size: 12px; color: {MUTED}; font-weight: 600">Rechnung</div>
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap">
              <div style="height: 38px; padding: 0 14px; border-radius: 99px; background: {ACCENT}; color: #FFFFFF; display: flex; align-items: center; gap: 8px; font-size: 13.5px; font-weight: 600">
                {icon(IC_DOC, "#FFFFFF", 16, "1.9")}
                {card.invoice_label}
              </div>
              <div style="display: flex; align-items: center; gap: 4px; padding: 3px; border-radius: 99px; background: {CANVAS}">
{langs}              </div>
{invoice_badge}            </div>
            <div style="font-size: 12px; color: {MUTED}">{card.invoice_note}</div>
          </div>
        </div>
      </div>

    </div>

    <div style="display: flex; flex-direction: column; gap: 14px; min-width: 0">

      <div style="background: #FFFFFF; border-radius: 20px; box-shadow: {CARD_SHADOW}; padding: 16px 18px; display: flex; flex-direction: column; gap: 12px">
        <div style="display: flex; align-items: center; gap: 12px">
          <div style="width: 44px; height: 44px; border-radius: 99px; background: {ACCENT_SOFT}; color: {ACCENT_DARK}; display: flex; align-items: center; justify-content: center; font-size: 15px; font-weight: 700">{card.customer_initials}</div>
          <div style="flex-grow: 1; min-width: 0">
            <div style="font-size: 15.5px; font-weight: 700; color: {ACCENT}">{card.customer_name}</div>
            <div style="font-size: 12.5px; color: {MUTED}">{card.customer_sub}</div>
          </div>
        </div>
        <div style="display: flex; flex-direction: column; gap: 3px; font-size: 13.5px">
          <div style="color: {BODY}">{card.customer_mail}</div>
          <div style="color: {BODY}">{card.customer_phone}</div>
        </div>
        <div style="display: flex; gap: 8px">
          <div style="flex-grow: 1; height: 40px; border-radius: 99px; background: {ACCENT}; color: #FFFFFF; display: flex; align-items: center; justify-content: center; gap: 8px; font-size: 13.5px; font-weight: 600">
            {icon(IC_CHAT, "#FFFFFF", 17, "1.9")}
            {card.contact_label}
          </div>
          <div style="width: 40px; height: 40px; border-radius: 99px; background: {CANVAS}; display: flex; align-items: center; justify-content: center">
            {icon(IC_PENCIL, BODY, 17, "1.9")}
          </div>
        </div>
      </div>

{side_html}{delivery_html}
      <div style="background: #FFFFFF; border-radius: 20px; box-shadow: {CARD_SHADOW}; padding: 14px 18px; display: flex; align-items: center; gap: 10px">
        {icon(IC_LINK)}
        <div style="flex-grow: 1; font-size: 13.5px">Verknüpfte Leistungen</div>
        <div style="font-size: 13px; color: {ACCENT}; font-weight: 600">Verknüpfen</div>
      </div>

    </div>
  </div>
</div>
{TAIL}"""


# --- данные архетипов -----------------------------------------------------------

CARDS = [
    Card(
        file="Main.dc.html",
        archetype="bakery",
        business="Backhaus Krume · Bäckerei",
        crumbs="Verkäufe › Bestellungen",
        kind_label="Bestellung",
        number="#O-4F2K1B",
        ext_number="—",
        ext_new=False,
        status="Abholbereit",
        status_color=WARN,
        status_next="Abgeholt · Storniert",
        meta="Eingegangen 21.08. 06:40 · Abholung heute 15:30 · Kanal: Website",
        pay_pill=("Bezahlt", OK, OK_SOFT),
        lines=[
            Line("2×", "Roggen-Sauerteig 1 kg", "Art.-Nr. BR-101", "7 %", "4,20 €", "8,40 €"),
            Line("12×", "Brötchen gemischt", "", "7 %", "0,55 €", "6,60 €"),
            Line("1×", "Butterkuchen-Blech", "vorbestellt", "7 %", "14,50 €", "14,50 €"),
            Line("1×", "Kaffeebohnen 500 g", "", "19 %", "9,80 €", "9,80 €"),
        ],
        totals=[
            ("Netto", "35,79 €"),
            ("MwSt. 7 % <span style=\"color: #B3B8C2\">auf 29,50 €</span>", "1,93 €"),
            ("MwSt. 19 % <span style=\"color: #B3B8C2\">auf 9,80 €</span>", "1,56 €"),
        ],
        net_first=False,
        totals_new=False,
        total_label="Gesamt (brutto)",
        total_value="39,30 €",
        pay_status="Bezahlt",
        pay_color=OK,
        pay_note="Offen: 0,00 € von 39,30 €",
        pay_method="Online-Zahlung · 21.08. 06:41",
        invoice_label="Rechnung erstellen",
        invoice_new=False,
        invoice_langs=("DE", "EN", "TR"),
        invoice_note="Noch keine Rechnung · Beleg auf Wunsch",
        customer_name="Anna Mahler",
        customer_initials="AM",
        customer_sub="Stammkundin · 14 Bestellungen · 268 €",
        customer_mail="anna.mahler@example.de",
        customer_phone="+49 170 8823 114",
        contact_label="Kundin kontaktieren",
        side_cards=[
            SideCard(
                IC_CAL,
                "Abholung",
                [("Wann", "heute · 15:30 Uhr"), ("Wo", "Theke Hauptstraße 4")],
                "Abholzeit ändern →",
            )
        ],
        height=1020,
    ),
    Card(
        file="Metzgerei.dc.html",
        archetype="butcher",
        business="Metzgerei Bergmann · Metzgerei",
        crumbs="Verkäufe › Bestellungen",
        kind_label="Bestellung",
        number="#O-8HR3TP",
        ext_number="—",
        ext_new=False,
        status="In Vorbereitung",
        status_color=ACCENT,
        status_next="Abholbereit · Storniert",
        meta="Vorbestellung 22.08. · Abholung Sa 24.08. 09:00 · Kanal: Telefon",
        pay_pill=("Zahlung bei Abholung", MUTED, CANVAS),
        lines=[
            Line("2,4 kg", "Rinderbraten am Stück", "Theke, gewogen", "7 %", "24,90 €/kg", "59,76 €"),
            Line("1×", "Grillplatte „Bergmann“", "für 6 Personen", "7 %", "42,00 €", "42,00 €"),
            Line("6×", "Bratwurst grob", "", "7 %", "1,80 €", "10,80 €"),
        ],
        totals=[
            ("Netto", "104,26 €"),
            ("MwSt. 7 %", "7,30 €"),
        ],
        net_first=False,
        totals_new=False,
        total_label="Gesamt (brutto)",
        total_value="112,56 €",
        pay_status="Offen",
        pay_color=WARN,
        pay_note="Zahlung bei Abholung · 112,56 €",
        pay_method="Vor Ort · Karte oder bar",
        invoice_label="Rechnung erstellen",
        invoice_new=False,
        invoice_langs=("DE", "EN"),
        invoice_note="Kunde bittet um Rechnung auf die Firma",
        customer_name="Thomas Wenzel",
        customer_initials="TW",
        customer_sub="Firmenkunde · 9 Bestellungen · 1.240 €",
        customer_mail="t.wenzel@nordbau.de",
        customer_phone="+49 211 4477 902",
        contact_label="Kunden kontaktieren",
        side_cards=[
            SideCard(
                IC_CAL,
                "Abholung",
                [("Wann", "Sa 24.08. · 09:00"), ("Hinweis", "Kühltasche mitbringen")],
                "Abholzeit ändern →",
            )
        ],
        height=1000,
    ),
    Card(
        file="Cafe.dc.html",
        archetype="cafe",
        business="Café Morgenrot · Café",
        crumbs="Verkäufe › Bestellungen",
        kind_label="Bestellung",
        number="#O-2QW7LM",
        ext_number="—",
        ext_new=False,
        status="In der Küche",
        status_color=ACCENT,
        status_next="Serviert · Storniert",
        meta="Tisch 7 · QR-Bestellung · 12:18 Uhr",
        pay_pill=("Bezahlt", OK, OK_SOFT),
        lines=[
            Line("2×", "Cappuccino", "im Haus", "19 %", "3,60 €", "7,20 €"),
            Line("1×", "Avocado-Brot", "im Haus", "19 %", "9,50 €", "9,50 €"),
            Line("1×", "Zimtschnecke", "zum Mitnehmen", "7 %", "3,80 €", "3,80 €"),
        ],
        totals=[
            ("Netto", "17,60 €"),
            ("MwSt. 19 % <span style=\"color: #B3B8C2\">im Haus</span>", "2,67 €"),
            ("MwSt. 7 % <span style=\"color: #B3B8C2\">außer Haus</span>", "0,23 €"),
        ],
        net_first=False,
        totals_new=False,
        total_label="Gesamt (brutto)",
        total_value="20,50 €",
        pay_status="Bezahlt",
        pay_color=OK,
        pay_note="Karte am Tisch · 12:41",
        pay_method="Kartenzahlung · Terminal 2",
        invoice_label="Beleg erstellen",
        invoice_new=False,
        invoice_langs=("DE", "EN"),
        invoice_note="Bewirtungsbeleg auf Wunsch",
        customer_name="Gast · Tisch 7",
        customer_initials="T7",
        customer_sub="Ohne Konto · QR-Bestellung",
        customer_mail="keine E-Mail hinterlegt",
        customer_phone="—",
        contact_label="Gast kontaktieren",
        side_cards=[
            SideCard(
                IC_CAL,
                "Service",
                [("Tisch", "7 · Fensterreihe"), ("Bestellt", "12:18 Uhr"), ("Küche", "2 Positionen offen")],
                "Küchenansicht öffnen →",
            )
        ],
        height=1000,
    ),
    Card(
        file="Restaurant.dc.html",
        archetype="restaurant",
        business="Pranasy — Vegan &amp; Ayurveda · Restaurant",
        crumbs="Verkäufe › Tischreservierungen",
        kind_label="Reservierung",
        number="#T-5KD8NR",
        ext_number="OT-88214",
        ext_new=True,
        status="Bestätigt",
        status_color=ACCENT,
        status_next="Erschienen · Nicht erschienen · Storniert",
        meta="Fr 05.09. · 19:30 Uhr · 4 Personen · Kanal: Website",
        pay_pill=None,
        lines=[
            Line("4×", "Tischplatz · Abendservice", "19:30–21:30", "", "—", "—"),
            Line("1×", "Menü „Ayurveda 5 Gänge“", "vorbestellt", "19 %", "58,00 €", "232,00 €"),
            Line("1×", "Weinbegleitung", "vorbestellt", "19 %", "24,00 €", "96,00 €"),
        ],
        totals=[
            ("Netto", "275,63 €"),
            ("MwSt. 19 %", "52,37 €"),
        ],
        net_first=False,
        totals_new=True,
        total_label="Gesamt (brutto)",
        total_value="328,00 €",
        pay_status="Anzahlung offen",
        pay_color=WARN,
        pay_note="Anzahlung 25 % · 82,00 € · fällig 02.09.",
        pay_method="Vorbestellung mit Anzahlung",
        invoice_label="Rechnung erstellen",
        invoice_new=True,
        invoice_langs=("DE", "EN", "RU"),
        invoice_note="Rechnung nach dem Besuch",
        customer_name="Familie Sander",
        customer_initials="FS",
        customer_sub="4 Besuche · Allergie: Nüsse",
        customer_mail="sander.family@example.de",
        customer_phone="+49 172 5533 018",
        contact_label="Gäste kontaktieren",
        side_cards=[
            SideCard(
                IC_CAL,
                "Tisch",
                [("Wann", "Fr 05.09. · 19:30"), ("Tisch", "12 · Wintergarten"), ("Hinweis", "Kinderstuhl")],
                "Verschieben →",
            )
        ],
        height=1020,
    ),
    Card(
        file="Hofladen.dc.html",
        archetype="retail",
        business="Hofladen Sonnenfeld · Einzelhandel",
        crumbs="Verkäufe › Bestellungen",
        kind_label="Bestellung",
        number="#O-9PL4XC",
        ext_number="—",
        ext_new=False,
        status="Neu",
        status_color=MUTED,
        status_next="Bestätigt · Storniert",
        meta="Eingegangen 23.08. 18:05 · Abholung Mi 27.08. · Kanal: Website",
        pay_pill=("Vorkasse offen", WARN, WARN_SOFT),
        lines=[
            Line("1×", "Bio-Gemüsekiste groß", "wöchentlich", "7 %", "28,00 €", "28,00 €"),
            Line("2×", "Bergkäse 300 g", "", "7 %", "7,90 €", "15,80 €"),
            Line("1×", "Apfelsaft naturtrüb 5 l", "Pfand 3,00 €", "7 %", "12,00 €", "12,00 €"),
        ],
        totals=[
            ("Netto", "51,21 €"),
            ("MwSt. 7 %", "3,59 €"),
            ("Pfand <span style=\"color: #B3B8C2\">ohne MwSt.</span>", "3,00 €"),
        ],
        net_first=False,
        totals_new=False,
        total_label="Gesamt (brutto)",
        total_value="58,80 €",
        pay_status="Vorkasse offen",
        pay_color=WARN,
        pay_note="Überweisung erwartet · Verwendungszweck O-9PL4XC",
        pay_method="Vorkasse · Bankverbindung im Bestätigungs-Mail",
        invoice_label="Rechnung erstellen",
        invoice_new=False,
        invoice_langs=("DE", "EN"),
        invoice_note="Noch keine Rechnung",
        customer_name="Miriam Kley",
        customer_initials="MK",
        customer_sub="Abo-Kundin · jede Woche",
        customer_mail="m.kley@example.de",
        customer_phone="+49 160 9922 774",
        contact_label="Kundin kontaktieren",
        side_cards=[
            SideCard(
                IC_CAL,
                "Abholung",
                [("Wann", "Mi 27.08. · 16:00–18:00"), ("Wo", "Hofladen, Feldweg 2")],
                "Abholzeit ändern →",
            )
        ],
        height=1020,
    ),
    Card(
        file="Aktionsmarkt.dc.html",
        archetype="grocery",
        business="Aktionsmarkt Sparfuchs · Lebensmittel",
        crumbs="Verkäufe › Bestellungen",
        kind_label="Bestellung",
        number="#O-1XR6VD",
        ext_number="—",
        ext_new=False,
        status="Reserviert",
        status_color=ACCENT,
        status_next="Abgeholt · Storniert",
        meta="Aktions-Kauf · reserviert bis Fr 29.08. 20:00 · Kanal: Aktionsseite",
        pay_pill=("Aktion", ACCENT_DARK, ACCENT_SOFT),
        lines=[
            Line("1×", "Kaffee-Paket „Mystery“", "Aktion −30 %", "19 %", "13,90 €", "13,90 €"),
            Line("2×", "Bio-Kiste Wochenmarkt", "Aktionspreis", "7 %", "18,50 €", "37,00 €"),
            Line("1×", "Rabatt „Sparfuchs-Woche“", "", "", "", "−5,00 €", negative=True),
        ],
        totals=[
            ("Netto", "41,60 €"),
            ("MwSt. 7 %", "2,42 €"),
            ("MwSt. 19 %", "1,88 €"),
        ],
        net_first=False,
        totals_new=False,
        total_label="Gesamt (brutto)",
        total_value="45,90 €",
        pay_status="Zahlung bei Abholung",
        pay_color=MUTED,
        pay_note="Reservierung verfällt Fr 20:00",
        pay_method="Vor Ort",
        invoice_label="Rechnung erstellen",
        invoice_new=False,
        invoice_langs=("DE", "TR"),
        invoice_note="Aktionsbeleg mit Ersparnis 18,90 €",
        customer_name="Ercan Yildiz",
        customer_initials="EY",
        customer_sub="6 Aktions-Käufe · spart im Schnitt 14 €",
        customer_mail="e.yildiz@example.de",
        customer_phone="+49 176 3311 508",
        contact_label="Kunden kontaktieren",
        side_cards=[
            SideCard(
                IC_CAL,
                "Reservierung",
                [("Gültig bis", "Fr 29.08. · 20:00"), ("Aktion", "Sparfuchs-Woche")],
                "Aktion öffnen →",
            )
        ],
        height=1020,
    ),
    Card(
        file="Mode.dc.html",
        archetype="clothing",
        business="Studio Nordwind · Bekleidung",
        crumbs="Verkäufe › Bestellungen",
        kind_label="Bestellung",
        number="#O-7TN2QF",
        ext_number="ETSY-4471-88",
        ext_new=False,
        status="Versandbereit",
        status_color=WARN,
        status_next="Versendet · Storniert",
        meta="Eingegangen 20.08. 21:14 · Kanal: Online-Shop",
        pay_pill=("Bezahlt", OK, OK_SOFT),
        lines=[
            Line("1×", "Mantel „Nordlicht“", "Größe M · Farbe Sand", "19 %", "189,00 €", "189,00 €"),
            Line("2×", "Leinenhemd", "Größe S · Farbe Blau", "19 %", "79,00 €", "158,00 €"),
            Line("1×", "Versand DHL", "", "19 %", "4,90 €", "4,90 €"),
            Line("1×", "Gutschein WELCOME10", "", "", "", "−35,19 €", negative=True),
        ],
        totals=[
            ("Netto", "266,98 €"),
            ("MwSt. 19 %", "50,73 €"),
        ],
        net_first=False,
        totals_new=False,
        total_label="Gesamt (brutto)",
        total_value="316,71 €",
        pay_status="Bezahlt",
        pay_color=OK,
        pay_note="Offen: 0,00 € · Rückgabefrist bis 17.09.",
        pay_method="PayPal · 20.08. 21:15",
        invoice_label="Rechnung erstellen",
        invoice_new=False,
        invoice_langs=("DE", "EN"),
        invoice_note="Rechnung R-2026-0212 · versendet",
        customer_name="Julia Brandt",
        customer_initials="JB",
        customer_sub="3 Bestellungen · 1 Rücksendung",
        customer_mail="julia.brandt@example.de",
        customer_phone="+49 151 2288 640",
        contact_label="Kundin kontaktieren",
        side_cards=[],
        delivery={
            "title": "Lieferung",
            "state": "Offen",
            "state_color": WARN,
            "state_bg": WARN_SOFT,
            "address": "Julia Brandt<br>Kirchgasse 8<br>50667 Köln",
            "field_label": "Sendungsnummer",
            "field_hint": "z. B. 00340434…",
            "doc": "Lieferschein (PDF)",
        },
        height=1080,
    ),
    Card(
        file="OnlineShop.dc.html",
        archetype="online_shop",
        business="Online-Shop · Versandhandel",
        crumbs="Verkäufe › Bestellungen",
        kind_label="Bestellung",
        number="#O-3GD9KW",
        ext_number="AMZ-889-4471",
        ext_new=False,
        status="Versendet",
        status_color=OK,
        status_next="Retoure · Storniert",
        meta="Eingegangen 19.08. 11:02 · Marktplatz-Import · Kanal: Amazon",
        pay_pill=("Bezahlt", OK, OK_SOFT),
        lines=[
            Line("3×", "Espresso-Bohnen 1 kg", "Art.-Nr. KB-220", "7 %", "18,90 €", "56,70 €"),
            Line("1×", "Handfilter-Set", "Art.-Nr. ZB-14", "19 %", "34,00 €", "34,00 €"),
            Line("1×", "Versand DHL Paket", "", "19 %", "5,90 €", "5,90 €"),
        ],
        totals=[
            ("Netto", "86,52 €"),
            ("MwSt. 7 %", "3,71 €"),
            ("MwSt. 19 %", "6,37 €"),
        ],
        net_first=False,
        totals_new=False,
        total_label="Gesamt (brutto)",
        total_value="96,60 €",
        pay_status="Bezahlt",
        pay_color=OK,
        pay_note="Auszahlung Marktplatz · 02.09.",
        pay_method="Marktplatz-Abwicklung",
        invoice_label="Rechnung erstellen",
        invoice_new=False,
        invoice_langs=("DE", "EN", "TR"),
        invoice_note="Rechnung R-2026-0198 · im Kundenkonto",
        customer_name="Peer Osthoff",
        customer_initials="PO",
        customer_sub="Neukunde · Marktplatz",
        customer_mail="peer.osthoff@example.de",
        customer_phone="—",
        contact_label="Kunden kontaktieren",
        side_cards=[],
        delivery={
            "title": "Lieferung",
            "state": "Versendet",
            "state_color": OK,
            "state_bg": OK_SOFT,
            "address": "Peer Osthoff<br>Marktstraße 21<br>20095 Hamburg",
            "field_label": "Sendungsnummer",
            "field_hint": "00340434 1234 5678 90",
            "doc": "Lieferschein (PDF)",
        },
        height=1060,
    ),
    Card(
        file="Friseur.dc.html",
        archetype="friseur",
        business="Salon Schöngut · Friseur",
        crumbs="Verkäufe › Termine",
        kind_label="Termin",
        number="#T-3M8P2Q",
        ext_number="SAL-2291",
        ext_new=True,
        status="Bestätigt",
        status_color=ACCENT,
        status_next="Erschienen · Nicht erschienen · Storniert",
        meta="Do 04.09. · 14:00–15:15 · Stuhl 2 · Mara",
        pay_pill=None,
        lines=[
            Line("1×", "Damenhaarschnitt &amp; Föhnen", "75 Min.", "19 %", "58,00 €", "58,00 €"),
            Line("1×", "Intensivkur", "Zusatzleistung", "19 %", "12,00 €", "12,00 €"),
            Line("1×", "Gutschein GS-4471", "", "", "", "−10,00 €", negative=True),
        ],
        totals=[
            ("Netto", "50,42 €"),
            ("MwSt. 19 %", "9,58 €"),
        ],
        net_first=False,
        totals_new=True,
        total_label="Gesamt (brutto)",
        total_value="60,00 €",
        pay_status="Vor Ort zu zahlen",
        pay_color=MUTED,
        pay_note="Zahlung im Salon · kein Online-Beleg",
        pay_method="Vor Ort · Karte oder bar",
        invoice_label="Rechnung erstellen",
        invoice_new=True,
        invoice_langs=("DE", "EN"),
        invoice_note="Beleg auf Wunsch der Kundin",
        customer_name="Lena Kraft",
        customer_initials="LK",
        customer_sub="Stammkundin · alle 6 Wochen",
        customer_mail="lena.kraft@example.de",
        customer_phone="+49 175 4412 903",
        contact_label="Kundin kontaktieren",
        side_cards=[
            SideCard(
                IC_CAL,
                "Termin",
                [("Wann", "Do 04.09. · 14:00"), ("Wer", "Mara · Stuhl 2"), ("Erinnerung", "gesendet 03.09.")],
                "Verschieben →",
            )
        ],
        height=1000,
    ),
    Card(
        file="Werkstatt.dc.html",
        archetype="werkstatt",
        business="KFZ-Werkstatt Dreyer · Werkstatt",
        crumbs="Verkäufe › Aufträge",
        kind_label="Auftrag",
        number="#A-6VB1XZ",
        ext_number="VERS-2026-4471",
        ext_new=True,
        status="In Arbeit",
        status_color=ACCENT,
        status_next="Erledigt · Storniert",
        meta="VW Golf VII · K-DR 4471 · angenommen 22.08. 08:15",
        pay_pill=None,
        lines=[
            Line("1×", "Inspektion nach Herstellervorgabe", "aus dem Sortiment", "19 %", "189,00 €", "189,00 €"),
            Line("4×", "Bremsbelag vorne", "Teil BR-88", "19 %", "34,50 €", "138,00 €"),
            Line("2,5 Std.", "Arbeitszeit Mechanik", "", "19 %", "78,00 €", "195,00 €"),
        ],
        totals=[
            ("Zwischensumme (netto)", "522,00 €"),
            ("MwSt. 19 %", "99,18 €"),
        ],
        net_first=True,
        totals_new=False,
        total_label="Gesamt (brutto)",
        total_value="621,18 €",
        pay_status="Offen",
        pay_color=WARN,
        pay_note="Zahlung bei Abholung des Fahrzeugs",
        pay_method="Rechnung an Versicherung möglich",
        invoice_label="Rechnung aus Auftrag erstellen",
        invoice_new=False,
        invoice_langs=("DE", "EN", "TR"),
        invoice_note="Kostenvoranschlag vom Kunden bestätigt",
        customer_name="Sabine Roth",
        customer_initials="SR",
        customer_sub="3 Aufträge · Fahrzeug seit 2021",
        customer_mail="s.roth@example.de",
        customer_phone="+49 221 5588 210",
        contact_label="Kundin kontaktieren",
        side_cards=[
            SideCard(
                IC_CAL,
                "Fahrzeug &amp; Termin",
                [("Fahrzeug", "VW Golf VII · 2019"), ("Kennzeichen", "K-DR 4471"), ("Fertig", "Do 28.08. · 16:00")],
                "Ersatzwagen prüfen →",
            )
        ],
        height=1040,
    ),
    Card(
        file="Handwerker.dc.html",
        archetype="handwerker",
        business="Meisterbetrieb Krause · Handwerk",
        crumbs="Verkäufe › Aufträge",
        kind_label="Auftrag",
        number="#A-4KP8WT",
        ext_number="BV-Hilden-22",
        ext_new=True,
        status="Beauftragt",
        status_color=ACCENT,
        status_next="Erledigt · Storniert",
        meta="Badsanierung · Objekt: Lindenweg 12, Hilden · Angebot vom 12.08.",
        pay_pill=None,
        lines=[
            Line("1×", "Fliesenarbeiten Bad 8 m²", "Material + Verlegung", "19 %", "2.240,00 €", "2.240,00 €"),
            Line("1×", "Duschwanne bodengleich", "aus dem Sortiment", "19 %", "890,00 €", "890,00 €"),
            Line("18 Std.", "Montage Meisterstunde", "", "19 %", "62,00 €", "1.116,00 €"),
            Line("1×", "Entsorgung Altbestand", "", "19 %", "180,00 €", "180,00 €"),
        ],
        totals=[
            ("Zwischensumme (netto)", "4.426,00 €"),
            ("MwSt. 19 %", "840,94 €"),
        ],
        net_first=True,
        totals_new=False,
        total_label="Gesamt (brutto)",
        total_value="5.266,94 €",
        pay_status="Anzahlung bezahlt",
        pay_color=WARN,
        pay_note="Offen: 3.686,86 € · Rest nach Abnahme",
        pay_method="Anzahlung 30 % · Überweisung 14.08.",
        invoice_label="Rechnung aus Auftrag erstellen",
        invoice_new=False,
        invoice_langs=("DE", "EN"),
        invoice_note="Teilrechnung 1 gestellt · Schlussrechnung offen",
        customer_name="Eheleute Hoffmann",
        customer_initials="EH",
        customer_sub="Privatkunde · Empfehlung",
        customer_mail="hoffmann.hilden@example.de",
        customer_phone="+49 2103 998 221",
        contact_label="Kunden kontaktieren",
        side_cards=[
            SideCard(
                IC_CAL,
                "Baustelle",
                [("Objekt", "Lindenweg 12, Hilden"), ("Start", "Mo 01.09."), ("Dauer", "ca. 9 Werktage")],
                "Termin planen →",
            )
        ],
        height=1060,
    ),
    Card(
        file="Catering.dc.html",
        archetype="catering",
        business="Grüne Tafel Catering · Catering",
        crumbs="Verkäufe › Aufträge",
        kind_label="Auftrag",
        number="#A-9QT4KD",
        ext_number="NW-2026-118",
        ext_new=True,
        status="Beauftragt",
        status_color=ACCENT,
        status_next="Erledigt · Storniert",
        meta="Firmenfeier Nordwind GmbH · 18.10. · 45 Gäste",
        pay_pill=None,
        lines=[
            Line("45×", "Fingerfood-Menü „Garten“", "pro Person · aus dem Sortiment", "19 %", "24,50 €", "1.102,50 €"),
            Line("45×", "Getränkepauschale", "", "19 %", "9,00 €", "405,00 €"),
            Line("12 Std.", "Servicekraft", "", "19 %", "32,00 €", "384,00 €"),
            Line("1×", "Anfahrt &amp; Aufbau", "", "19 %", "120,00 €", "120,00 €"),
        ],
        totals=[
            ("Zwischensumme (netto)", "2.011,50 €"),
            ("MwSt. 19 %", "382,19 €"),
        ],
        net_first=True,
        totals_new=False,
        total_label="Gesamt (brutto)",
        total_value="2.393,69 €",
        pay_status="Anzahlung offen",
        pay_color=WARN,
        pay_note="Anzahlung 30 % · 718,11 € · fällig 20.09.",
        pay_method="Angebot gültig bis 05.09.2026",
        invoice_label="Rechnung aus Auftrag erstellen",
        invoice_new=False,
        invoice_langs=("DE", "EN"),
        invoice_note="Angebot-Link für den Kunden · kopieren",
        customer_name="Nordwind GmbH",
        customer_initials="NG",
        customer_sub="Ansprechpartner: Jonas Weiler",
        customer_mail="j.weiler@nordwind.de",
        customer_phone="+49 211 7788 010",
        contact_label="Kunden kontaktieren",
        side_cards=[
            SideCard(
                IC_CAL,
                "Veranstaltung",
                [("Wann", "Sa 18.10. · 18:00"), ("Gäste", "45"), ("Art", "Firmenfeier"), ("Ort", "Nordwind Campus")],
                "Anfrage-Daten öffnen →",
            )
        ],
        height=1080,
    ),
    Card(
        file="Hotel.dc.html",
        archetype="hotel",
        business="Pension Seeblick · Hotel",
        crumbs="Verkäufe › Übernachtungen",
        kind_label="Buchung",
        number="#S-7K21QM",
        ext_number="BK-8891244",
        ext_new=True,
        status="Bestätigt",
        status_color=ACCENT,
        status_next="Angereist · Abgereist · Storniert",
        meta="Fr 12.09. – Mo 15.09. · 3 Nächte · 2 Erw. + 1 Kind · 1 Zimmer",
        pay_pill=None,
        lines=[
            Line("3 Nächte", "Doppelzimmer Seeblick", "129,00 € pro Nacht", "7 %", "129,00 €", "387,00 €"),
            Line("6×", "Frühstück", "pro Nacht · 2 Pers.", "7 %", "12,00 €", "72,00 €"),
            Line("1×", "Parkplatz", "einmalig", "19 %", "15,00 €", "15,00 €"),
            Line("1×", "Frühbucher −10 %", "", "", "", "−47,40 €", negative=True),
            Line("6×", "Kurtaxe", "ohne MwSt.", "—", "2,50 €", "15,00 €"),
        ],
        totals=[
            ("Netto", "391,73 €"),
            ("MwSt. 7 %", "28,47 €"),
            ("MwSt. 19 %", "2,40 €"),
            ("Kurtaxe <span style=\"color: #B3B8C2\">ohne MwSt.</span>", "15,00 €"),
        ],
        net_first=False,
        totals_new=True,
        total_label="Gesamt (brutto)",
        total_value="441,60 €",
        pay_status="Anzahlung bezahlt",
        pay_color=WARN,
        pay_note="Offen: 309,12 € von 441,60 €",
        pay_method="Anzahlung 30 % · Karte 14.08.",
        invoice_label="Rechnung erstellen",
        invoice_new=False,
        invoice_langs=("DE", "EN", "RU"),
        invoice_note="Rechnung bei Abreise",
        customer_name="Familie Berger",
        customer_initials="FB",
        customer_sub="2. Aufenthalt · Gast seit 2024",
        customer_mail="berger.familie@example.de",
        customer_phone="+49 170 2211 884",
        contact_label="Gast kontaktieren",
        side_cards=[
            SideCard(
                IC_CAL,
                "Aufenthalt",
                [("Zimmer", "204 · Seeblick"), ("Anreise", "Fr 12.09. ab 15:00"), ("Meldeschein", "ausgefüllt")],
                "Belegungsplan öffnen →",
            )
        ],
        height=1120,
    ),
    Card(
        file="Touren.dc.html",
        archetype="tour_operator",
        business="Himalaya Riders · Tour Operator",
        crumbs="Verkäufe › Tickets",
        kind_label="Ticket",
        number="#E-5RT9WX",
        ext_number="GYG-77120",
        ext_new=True,
        status="Bestätigt",
        status_color=ACCENT,
        status_next="Teilgenommen · Storniert",
        meta="Himalaya Enfield Tour · 12.–24.10.2026 · Tarif: Fahrer",
        pay_pill=None,
        lines=[
            Line("1×", "Himalaya Enfield Tour", "Fahrer (eigenes Motorrad)", "19 %", "2.450,00 €", "2.450,00 €"),
            Line("1×", "Enfield mieten", "Pool · 6 Maschinen", "19 %", "620,00 €", "620,00 €"),
            Line("1×", "Einzelzimmer-Zuschlag", "", "19 %", "340,00 €", "340,00 €"),
            Line("1×", "Gutschein WELCOME50", "", "", "", "−50,00 €", negative=True),
        ],
        totals=[
            ("Netto", "2.823,53 €"),
            ("MwSt. 19 %", "536,47 €"),
        ],
        net_first=False,
        totals_new=True,
        total_label="Gesamt (brutto)",
        total_value="3.360,00 €",
        pay_status="Ratenzahlung aktiv",
        pay_color=WARN,
        pay_note="2 von 4 Raten bezahlt · offen 1.680,00 €",
        pay_method="Nächste Rate 15.09. · Karte",
        invoice_label="Rechnung erstellen",
        invoice_new=True,
        invoice_langs=("DE", "EN"),
        invoice_note="Reisebestätigung versendet",
        customer_name="Marco Lehner",
        customer_initials="ML",
        customer_sub="Teilnehmer · 2. Reise",
        customer_mail="marco.lehner@example.de",
        customer_phone="+49 152 8899 341",
        contact_label="Teilnehmer kontaktieren",
        side_cards=[
            SideCard(
                IC_CAL,
                "Reise",
                [("Termin", "12.–24.10.2026"), ("Start", "Delhi"), ("Haftung", "unterschrieben")],
                "Reisegruppe öffnen →",
            )
        ],
        height=1080,
        head_badge="neu: Bildschirm",
    ),
    Card(
        file="Events.dc.html",
        archetype="events",
        business="Waldlicht Retreat · Veranstalter",
        crumbs="Verkäufe › Tickets",
        kind_label="Ticket",
        number="#E-8QM3HB",
        ext_number="EVB-55190",
        ext_new=True,
        status="Bestätigt",
        status_color=ACCENT,
        status_next="Teilgenommen · Storniert",
        meta="Waldlicht Herbst-Retreat · 03.–06.10. · Tarif: Einzelzimmer",
        pay_pill=None,
        lines=[
            Line("1×", "Retreat-Platz · 4 Tage", "Einzelzimmer", "19 %", "690,00 €", "690,00 €"),
            Line("1×", "Vollpension vegetarisch", "3 Tage", "7 %", "120,00 €", "120,00 €"),
            Line("1×", "Klangschalen-Workshop", "Zusatz", "19 %", "45,00 €", "45,00 €"),
        ],
        totals=[
            ("Netto", "729,26 €"),
            ("MwSt. 19 %", "117,39 €"),
            ("MwSt. 7 %", "8,35 €"),
        ],
        net_first=False,
        totals_new=True,
        total_label="Gesamt (brutto)",
        total_value="855,00 €",
        pay_status="Bezahlt",
        pay_color=OK,
        pay_note="Offen: 0,00 € von 855,00 €",
        pay_method="Überweisung · 08.08.",
        invoice_label="Rechnung erstellen",
        invoice_new=True,
        invoice_langs=("DE", "EN"),
        invoice_note="Teilnehmer-Infoblatt versendet",
        customer_name="Katrin Süss",
        customer_initials="KS",
        customer_sub="Teilnehmerin · 3. Retreat",
        customer_mail="katrin.suess@example.de",
        customer_phone="+49 171 6600 293",
        contact_label="Teilnehmerin kontaktieren",
        side_cards=[
            SideCard(
                IC_CAL,
                "Veranstaltung",
                [("Termin", "03.–06.10."), ("Ort", "Waldlicht Hof"), ("Plätze", "14 von 16 belegt")],
                "Teilnehmerliste öffnen →",
            )
        ],
        height=1060,
        head_badge="neu: Bildschirm",
    ),
]


def main():
    for card in CARDS:
        path = os.path.join(DIR, card.file)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render(card))
        print(f"{card.file:22} {card.archetype}")
    print(f"\n{len(CARDS)} артбордов записано в {DIR}")


if __name__ == "__main__":
    main()
