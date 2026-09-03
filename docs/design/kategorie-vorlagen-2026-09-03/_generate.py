"""DL-20: канвас «Vorlagen der Kategorieseiten» — 5 макетов страницы категории
товаров + 5 макетов страницы группы акций (запрос владельца 2026-09-03).

Правки — ЗДЕСЬ, потом `python _generate.py` и пере-сид канваса.
Стиль вайрфрейма — тот же, что в `kartenformen-2026-09-02` (владелец его принял).
"""

import json
from pathlib import Path

HERE = Path(__file__).parent

CSS = """
<style>
  body { margin: 0; font-family: Inter, "Segoe UI", sans-serif; color: #1f2937; }
  .wf { width: 760px; background: #fff; box-sizing: border-box; border: 1px solid #e5e7eb; }
  .bar { display: flex; align-items: center; justify-content: space-between;
         padding: 9px 18px; border-bottom: 1px solid #e5e7eb; font-size: 11px; color: #6b7280; }
  .bar b { color: #111827; font-size: 12px; }
  .sec { padding: 14px 18px; }
  .crumbs { font-size: 9px; color: #9ca3af; margin-bottom: 6px; }
  .h1 { font-size: 17px; font-weight: 800; color: #111827; margin: 0 0 4px; }
  .h1.sm { font-size: 14px; }
  .sub { font-size: 10px; color: #6b7280; line-height: 1.5; }
  .h2 { font-size: 11px; font-weight: 700; color: #111827; margin: 0 0 7px;
        display: flex; justify-content: space-between; align-items: baseline; }
  .h2 span { font-weight: 400; color: #9ca3af; font-size: 9px; }
  .grid { display: grid; gap: 9px; }
  .row { display: flex; gap: 9px; }
  .ph { background: repeating-linear-gradient(135deg, #e5e7eb 0 6px, #f3f4f6 6px 12px); }
  .card { border: 1px solid #e5e7eb; border-radius: 9px; overflow: hidden;
          background: #fff; font-size: 10px; position: relative; }
  .card .b { padding: 6px 8px; }
  .name { font-weight: 600; color: #111827; font-size: 10px; line-height: 1.25; }
  .price { font-weight: 800; color: #111827; font-size: 13px; }
  .price.red { color: #dc2626; }
  .old { color: #9ca3af; text-decoration: line-through; font-size: 9px; }
  .save { color: #047857; font-size: 9px; font-weight: 600; }
  .badge { background: #dc2626; color: #fff; font-weight: 700; font-size: 9px;
           padding: 2px 6px; border-radius: 999px; display: inline-block; }
  .chip { display: inline-block; border: 1px solid #d1d5db; border-radius: 999px;
          padding: 2px 8px; font-size: 9px; color: #374151; margin: 0 4px 4px 0; background: #fff; }
  .chip.on { background: #111827; color: #fff; border-color: #111827; }
  .btn { background: #111827; color: #fff; border-radius: 6px; padding: 5px 9px;
         font-size: 9px; font-weight: 600; text-align: center; display: inline-block; }
  .btn.ghost { background: #fff; color: #374151; border: 1px solid #d1d5db; }
  .tools { display: flex; justify-content: space-between; align-items: center;
           border-top: 1px solid #f3f4f6; border-bottom: 1px solid #f3f4f6;
           padding: 7px 18px; font-size: 9px; color: #6b7280; }
  .box { border: 1px solid #e5e7eb; border-radius: 9px; }
  .side { width: 150px; flex: 0 0 150px; }
  .side .it { font-size: 9px; color: #374151; padding: 3px 0; }
  .side .it.on { font-weight: 700; color: #111827; }
  .cap { padding: 12px 18px 14px; background: #fafafa; border-top: 1px solid #e5e7eb;
         font-size: 11px; line-height: 1.55; color: #374151; }
  .cap b { color: #111827; }
  .tag { display: inline-block; font-size: 10px; font-weight: 600; padding: 2px 7px;
         border-radius: 999px; background: #dcfce7; color: #166534; margin-right: 4px; }
  .tag.new { background: #dbeafe; color: #1e40af; }
  .tag.warn { background: #fef3c7; color: #92400e; }
  table.cmp { border-collapse: collapse; width: 100%; font-size: 10px; margin-top: 6px; }
  table.cmp th, table.cmp td { border: 1px solid #e5e7eb; padding: 5px 7px;
                               text-align: left; vertical-align: top; }
  table.cmp th { background: #f9fafb; font-weight: 600; color: #111827; }
  .strip { display: flex; gap: 9px; overflow: hidden; }
  .strip > * { flex: 0 0 118px; }
</style>
"""


def page(title, kicker, body, caption):
    return (
        CSS
        + f'<div class="wf"><div class="bar"><b>{title}</b><span>{kicker}</span></div>'
        + body
        + f'<div class="cap">{caption}</div></div>'
    )


def card(h=54, name="Produkt", price="4,90 €", old="", badge="", body_extra=""):
    top = (
        f'<span class="badge" style="position:absolute;top:5px;left:5px">{badge}</span>'
        if badge
        else ""
    )
    old_html = f' <span class="old">{old}</span>' if old else ""
    return (
        f'<div class="card">{top}<div class="ph" style="height:{h}px"></div>'
        f'<div class="b"><div class="name">{name}</div>'
        f'<div style="margin-top:3px"><span class="price">{price}</span>{old_html}</div>'
        f"{body_extra}</div></div>"
    )


def grid(cards, cols=3):
    return (
        f'<div class="grid" style="grid-template-columns:repeat({cols},1fr)">'
        + "".join(cards)
        + "</div>"
    )


def crumbs(txt="Startseite › Sortiment › Backwaren"):
    return f'<div class="crumbs">{txt}</div>'


def tools(left="⚙ Filter · Sortierung: Beliebt", right="▦ ▤ · Dichte − 4 +"):
    return f'<div class="tools"><span>{left}</span><span>{right}</span></div>'


# ─────────────────────────── товарные категории ───────────────────────────

P1 = page(
    "P1 · Schaufenster",
    "Kategorieseite · ein Produkt führt",
    crumbs().join(['<div class="sec">', ""])
    + '<div class="h1">Backwaren</div>'
    + '<div class="sub">Täglich frisch aus eigener Backstube.</div></div>'
    + '<div class="sec" style="padding-top:0">'
    + '<div class="box row" style="padding:9px;gap:12px;align-items:center">'
    + '<div class="ph" style="width:210px;height:104px;border-radius:7px;flex:0 0 210px"></div>'
    + '<div style="flex:1"><span class="badge">Empfehlung</span>'
    + '<div class="name" style="font-size:13px;margin-top:5px">Bauernbrot 1 kg</div>'
    + '<div class="sub" style="margin:4px 0 6px">Natursauerteig, 24 h geführt — der Klassiker '
    + "des Hauses.</div>"
    + '<span class="price" style="font-size:17px">4,90 €</span> '
    + '<span class="btn" style="margin-left:6px">In den Korb</span></div></div></div>'
    + tools()
    + '<div class="sec">'
    + grid(
        [
            card(name="Roggenmischbrot"),
            card(name="Dinkelbrot"),
            card(name="Baguette"),
            card(name="Körnerbrötchen"),
            card(name="Laugenstange"),
            card(name="Croissant"),
        ]
    )
    + "</div>",
    "<b>Одна позиция ведёт страницу.</b> Первый товар (рекомендованный или новинка) выведен "
    "широкой картой с описанием и кнопкой, остальные — обычной сеткой. "
    "<b>Когда уместно:</b> категория, где есть очевидный флагман — пекарня с фирменным хлебом, "
    "мастерская с основной услугой, магазин с хитом сезона. "
    '<span class="tag new">нового в движке</span> вывод «герой-товара» на листинге — сейчас '
    "такого нет ни в одном стиле.",
)

P2 = page(
    "P2 · Navigator",
    "Kategorieseite · Filter und Struktur links",
    '<div class="sec">'
    + crumbs()
    + '<div class="h1">Damenmode</div></div>'
    + '<div class="sec" style="padding-top:0"><div class="row">'
    + '<div class="side"><div class="box" style="padding:9px">'
    + '<div class="h2" style="margin-bottom:5px">Kategorien</div>'
    + '<div class="it on">Damenmode</div><div class="it">· Kleider (18)</div>'
    + '<div class="it">· Oberteile (24)</div><div class="it">· Hosen (11)</div>'
    + '<div class="it">· Accessoires (9)</div>'
    + '<div class="h2" style="margin:10px 0 5px">Filter</div>'
    + '<div class="it">Größe: S M L XL</div><div class="it">Farbe: ● ● ● ●</div>'
    + '<div class="it">Preis: 10 – 120 €</div><div class="it">☑ Nur verfügbar</div>'
    + "</div></div>"
    + '<div style="flex:1">'
    + '<div class="tools" style="border-top:0;padding:0 0 7px">'
    + "<span>132 Artikel</span><span>Sortierung: Neu ▾ · ▦ ▤</span></div>"
    + grid(
        [
            card(name="Leinenkleid", price="79,00 €"),
            card(name="Strickpullover", price="59,00 €"),
            card(name="Chino", price="49,00 €"),
            card(name="Seidenbluse", price="89,00 €"),
            card(name="Wollschal", price="29,00 €"),
            card(name="Ledergürtel", price="39,00 €"),
        ]
    )
    + "</div></div></div>",
    "<b>Структура и фильтры — слева, товары справа.</b> Классическая раскладка большого "
    "каталога: подкатегории со счётчиками и фасеты всегда на виду, не занимают первый экран "
    "сверху. На телефоне колонка сворачивается в кнопку «Фильтры» (как сейчас). "
    "<b>Когда уместно:</b> сотни позиций, много подкатегорий, покупатель приходит выбирать по "
    'параметрам. <span class="tag new">нового в движке</span> боковая колонка — сегодня фасеты '
    "только панелью сверху.",
)

P3 = page(
    "P3 · Magazin",
    "Kategorieseite · Titelbild und wenige große Karten",
    '<div class="ph" style="height:92px"></div>'
    + '<div class="sec" style="padding-bottom:6px">'
    + '<div class="h1">Manufaktur-Möbel</div>'
    + '<div class="sub">Jedes Stück entsteht bei uns in der Werkstatt — aus heimischem Holz, '
    + "in kleiner Serie. Lieferzeit 4 – 6 Wochen.</div></div>"
    + tools(left="8 Stücke", right="Sortierung: Empfohlen")
    + '<div class="sec">'
    + grid(
        [
            card(
                h=76,
                name="Esstisch «Eiche massiv»",
                price="1.290 €",
                body_extra='<div class="sub" style="margin-top:4px">Geölte Wildeiche, '
                "220 × 100 cm, auf Maß.</div>",
            ),
            card(
                h=76,
                name="Sideboard «Linie»",
                price="890 €",
                body_extra='<div class="sub" style="margin-top:4px">Drei Schubladen, '
                "grifflos, Nussbaum.</div>",
            ),
            card(
                h=76,
                name="Stuhl «Sprosse»",
                price="240 €",
                body_extra='<div class="sub" style="margin-top:4px">Buche, geflochtene '
                "Sitzfläche.</div>",
            ),
            card(
                h=76,
                name="Regal «Turm»",
                price="640 €",
                body_extra='<div class="sub" style="margin-top:4px">Fünf Böden, wandhängend.</div>',
            ),
        ],
        cols=2,
    )
    + "</div>",
    "<b>Обложка и крупные карточки с описанием.</b> Шапка категории — во всю ширину, дальше "
    "по 2 карточки в ряд, у каждой есть текст. <b>Когда уместно:</b> мало позиций и они дорогие "
    "— мебель, украшения, туры, пакеты услуг: там решение принимают по описанию, а не по цене. "
    '<span class="tag">есть частично</span> шапка Kopfbild уже существует, ново — крупная '
    "сетка с описанием вместо мелких плиток.",
)

P4 = page(
    "P4 · Mosaik",
    "Kategorieseite · Kacheln unterschiedlicher Größe",
    '<div class="sec">'
    + crumbs("Startseite › Sortiment › Feinkost")
    + '<div class="h1">Feinkost</div></div>'
    + tools(left="Filter · 34 Artikel", right="▦ ▤")
    + '<div class="sec">'
    + '<div class="grid" style="grid-template-columns:repeat(4,1fr);grid-auto-rows:64px">'
    + '<div class="card" style="grid-column:span 2;grid-row:span 2">'
    + '<div class="ph" style="height:100%"></div>'
    + '<div style="position:absolute;left:7px;bottom:7px;background:#fff;border-radius:6px;'
    + 'padding:4px 7px"><div class="name">Trüffel-Sortiment</div>'
    + '<span class="price">34,00 €</span></div></div>'
    + card(h=34, name="Olivenöl", price="12,90 €")
    + card(h=34, name="Pesto", price="6,40 €")
    + '<div class="card" style="grid-column:span 2"><div class="row" style="height:100%">'
    + '<div class="ph" style="width:56px;flex:0 0 56px"></div>'
    + '<div class="b"><div class="name">Balsamico 12 Jahre</div>'
    + '<span class="price">24,00 €</span></div></div></div>'
    + card(h=34, name="Meersalz", price="4,20 €")
    + card(h=34, name="Honig", price="8,90 €")
    + card(h=34, name="Senf", price="3,90 €")
    + card(h=34, name="Chutney", price="5,50 €")
    + "</div></div>",
    "<b>Плитки разного размера.</b> Первая позиция занимает четверть экрана, дальше обычные и "
    "широкие вперемешку — сетка перестаёт быть однообразной. <b>Когда уместно:</b> витрина, где "
    "надо выделить несколько позиций из ряда — деликатесы, подарочные наборы, «интересное». "
    '<span class="tag warn">риск</span> при плохих фото выглядит хуже ровной сетки — стоит '
    "включать там, где фотографии сильные.",
)

P5 = page(
    "P5 · Kompakt",
    "Kategorieseite · viele Artikel auf einen Blick",
    '<div class="sec" style="padding-bottom:8px">'
    + crumbs("Startseite › Sortiment › Ersatzteile")
    + '<div class="h1">Ersatzteile</div>'
    + '<div class="row" style="gap:18px;margin-top:7px">'
    + '<div style="flex:1"><div class="it" style="font-size:9px;font-weight:700">Bremsen</div>'
    + '<div class="sub">Beläge · Scheiben · Sättel</div></div>'
    + '<div style="flex:1"><div class="it" style="font-size:9px;font-weight:700">Filter</div>'
    + '<div class="sub">Öl · Luft · Innenraum</div></div>'
    + '<div style="flex:1"><div class="it" style="font-size:9px;font-weight:700">Zündung</div>'
    + '<div class="sub">Kerzen · Spulen</div></div>'
    + '<div style="flex:1"><div class="it" style="font-size:9px;font-weight:700">Öle</div>'
    + '<div class="sub">Motor · Getriebe</div></div></div></div>'
    + tools(left="412 Artikel · Suche nach Art.-Nr.", right="Sortierung: Art.-Nr.")
    + '<div class="sec">'
    + '<div class="grid" style="grid-template-columns:repeat(6,1fr)">'
    + "".join(
        card(h=30, name=n, price=p)
        for n, p in [
            ("Bremsbelag VA", "34,90 €"),
            ("Bremsscheibe", "59,00 €"),
            ("Ölfilter", "9,40 €"),
            ("Luftfilter", "14,20 €"),
            ("Zündkerze", "6,90 €"),
            ("Zündspule", "48,00 €"),
            ("Innenraumfilter", "12,50 €"),
            ("Motoröl 5W-30", "39,90 €"),
            ("Keilriemen", "22,00 €"),
            ("Wasserpumpe", "78,00 €"),
            ("Thermostat", "26,50 €"),
            ("Kühlmittel", "11,90 €"),
        ]
    )
    + "</div></div>",
    "<b>Много позиций на экран.</b> Подкатегории — компактным указателем в несколько колонок "
    "сверху, товары — плотной сеткой по 6 в ряд с минимумом хрома. <b>Когда уместно:</b> "
    "запчасти, крепёж, расходники, канцелярия — там, где покупатель ищет конкретную позицию, "
    "а не разглядывает витрину. "
    '<span class="tag new">нового в движке</span> указатель подкатегорий колонками.',
)

# ─────────────────────────── группы акций ───────────────────────────

AK_NOTE = (
    '<div class="sec" style="background:#fffbeb;border-bottom:1px solid #fde68a;padding:9px 18px">'
    '<div class="sub" style="color:#92400e"><b>Сегодня:</b> страницы группы акций не существует — '
    "<code>/aktionen/?gruppe=…</code> отдаёт плоскую сетку под общим заголовком «Aktuelle "
    "Angebote», названия группы на странице нет.</div></div>"
)


def promo(
    h=48,
    name="Angebot",
    price="2,49 €",
    old="3,49 €",
    save="Sie sparen 1,00 €",
    badge="−29 %",
    extra="",
):
    return (
        f'<div class="card"><span class="badge" style="position:absolute;top:5px;left:5px">'
        f'{badge}</span><div class="ph" style="height:{h}px"></div>'
        f'<div class="b"><div class="name">{name}</div>'
        f'<div style="margin-top:3px"><span class="price red">{price}</span> '
        f'<span class="old">{old}</span></div>'
        f'<div class="save">{save}</div>{extra}</div></div>'
    )


A1 = page(
    "A1 · Schaufenster",
    "Gruppenseite · ein Deal führt",
    AK_NOTE
    + '<div class="sec"><div class="crumbs">Aktionen › Wochenangebote</div>'
    + '<div class="h1">Wochenangebote</div>'
    + '<div class="sub">14 Angebote · noch bis Sonntag</div></div>'
    + '<div class="sec" style="padding-top:0">'
    + '<div class="box row" style="padding:9px;gap:12px;align-items:center;'
    + 'border-color:#fecaca;background:#fef2f2">'
    + '<div class="ph" style="width:190px;height:96px;border-radius:7px;flex:0 0 190px"></div>'
    + '<div style="flex:1"><span class="badge">−40 %</span>'
    + '<div class="name" style="font-size:13px;margin-top:5px">Kaffee «Hausmischung» 1 kg</div>'
    + '<div style="margin:4px 0"><span class="price red" style="font-size:18px">11,90 €</span> '
    + '<span class="old">19,90 €</span> <span class="save">Sie sparen 8,00 €</span></div>'
    + '<div class="sub">⏳ Endet in 2 T. 6 Std. · nur solange Vorrat reicht</div></div></div></div>'
    + '<div class="sec" style="padding-top:0">'
    + grid(
        [
            promo(
                name="Bio-Milch 1 l",
                price="0,99 €",
                old="1,29 €",
                save="Sie sparen 0,30 €",
                badge="−23 %",
            ),
            promo(
                name="Butter 250 g",
                price="1,79 €",
                old="2,49 €",
                save="Sie sparen 0,70 €",
                badge="−28 %",
            ),
            promo(
                name="Eier 10er",
                price="2,29 €",
                old="2,99 €",
                save="Sie sparen 0,70 €",
                badge="−23 %",
            ),
            promo(
                name="Mehl 1 kg",
                price="0,79 €",
                old="1,09 €",
                save="Sie sparen 0,30 €",
                badge="−27 %",
            ),
            promo(
                name="Zucker 1 kg",
                price="0,89 €",
                old="1,19 €",
                save="Sie sparen 0,30 €",
                badge="−25 %",
            ),
            promo(
                name="Nudeln 500 g",
                price="0,69 €",
                old="0,99 €",
                save="Sie sparen 0,30 €",
                badge="−30 %",
            ),
        ]
    )
    + "</div>",
    "<b>Заголовок группы + главный дил широкой картой.</b> Появляется то, чего сейчас нет "
    "вовсе: название группы, число акций и общий срок. <b>Когда уместно:</b> группа с одним "
    "«паровозом» — недельное предложение, акция месяца. "
    '<span class="tag">реюз</span> широкая карта уже написана (`_promo_featured.html`), '
    "но на странице акций сегодня не используется.",
)

A2 = page(
    "A2 · Prospekt",
    "Gruppenseite · Werbezeitung",
    AK_NOTE
    + '<div class="sec" style="background:#dc2626;color:#fff;padding:10px 18px">'
    + '<div style="font-size:16px;font-weight:800">Wochen-Prospekt</div>'
    + '<div style="font-size:10px;opacity:.9">Gültig 03.09. – 09.09. · 18 Angebote</div></div>'
    + '<div class="sec">'
    + '<div class="grid" style="grid-template-columns:repeat(5,1fr)">'
    + "".join(
        promo(h=32, name=n, price=p, old=o, save="", badge=b)
        for n, p, o, b in [
            ("Bio-Milch", "0,99 €", "1,29 €", "−23 %"),
            ("Butter", "1,79 €", "2,49 €", "−28 %"),
            ("Eier 10er", "2,29 €", "2,99 €", "−23 %"),
            ("Mehl", "0,79 €", "1,09 €", "−27 %"),
            ("Zucker", "0,89 €", "1,19 €", "−25 %"),
            ("Nudeln", "0,69 €", "0,99 €", "−30 %"),
            ("Reis", "1,49 €", "1,99 €", "−25 %"),
            ("Öl", "2,99 €", "3,99 €", "−25 %"),
            ("Kaffee", "11,90 €", "19,90 €", "−40 %"),
            ("Tee", "2,49 €", "3,29 €", "−24 %"),
        ]
    )
    + "</div></div>",
    "<b>Плотная сетка «как рекламная газета».</b> Цены крупные, описаний нет, по 5–6 позиций "
    "в ряд, шапка группы — цветная плашка со сроком действия. <b>Когда уместно:</b> продуктовый "
    "и дискаунтер: покупатель просматривает весь прайс глазами, а не читает. "
    '<span class="tag new">нового в движке</span> плотность и цветная шапка группы со сроком.',
)

A3 = page(
    "A3 · Magazin",
    "Gruppenseite · Titelbild und Bedingungen",
    AK_NOTE
    + '<div class="ph" style="height:84px"></div>'
    + '<div class="sec" style="padding-bottom:6px">'
    + '<div class="h1">Herbst-Wellness</div>'
    + '<div class="sub">Drei Anwendungen zum Kennenlernpreis — buchbar von Montag bis '
    + "Mittwoch, solange Termine frei sind.</div></div>"
    + '<div class="sec" style="padding-top:8px">'
    + grid(
        [
            promo(
                h=64,
                name="Klassische Massage 60 Min.",
                price="49,00 €",
                old="69,00 €",
                save="Sie sparen 20,00 €",
                badge="−29 %",
                extra='<div class="sub" style="margin-top:4px">Mo – Mi · 10 – 14 Uhr · '
                "max. 2 pro Kunde</div>",
            ),
            promo(
                h=64,
                name="Gesichtsbehandlung",
                price="59,00 €",
                old="79,00 €",
                save="Sie sparen 20,00 €",
                badge="−25 %",
                extra='<div class="sub" style="margin-top:4px">Mo – Mi · Termin nach '
                "Absprache</div>",
            ),
        ],
        cols=2,
    )
    + "</div>",
    "<b>Обложка группы, описание и условия.</b> У каждой акции под ценой видно, когда она "
    "действует и сколько раз можно взять. <b>Когда уместно:</b> услуги и пакеты — салон, отель, "
    "студия: там условие «Mo–Mi до 14:00» важнее размера скидки. "
    '<span class="tag">реюз</span> блок условий уже написан (DL-16.3, «Bedingungen» на детали '
    "акции) — здесь он поднимается на карточку.",
)

A4 = page(
    "A4 · Countdown",
    "Gruppenseite · alles läuft auf eine Frist zu",
    AK_NOTE
    + '<div class="sec" style="background:#111827;color:#fff;padding:11px 18px;text-align:center">'
    + '<div style="font-size:10px;opacity:.8">Black Week endet in</div>'
    + '<div style="font-size:20px;font-weight:800;letter-spacing:1px">2 Tage 06 : 41 : 09</div>'
    + "</div>"
    + '<div class="sec" style="padding-bottom:6px">'
    + '<div class="h2">Zuerst ablaufend <span>nach Restzeit sortiert</span></div></div>'
    + '<div class="sec" style="padding-top:0">'
    + grid(
        [
            promo(
                name="Winterjacke",
                price="89,00 €",
                old="149,00 €",
                save="⏳ noch 6 Std.",
                badge="−40 %",
            ),
            promo(
                name="Wollpullover",
                price="49,00 €",
                old="79,00 €",
                save="⏳ noch 1 T.",
                badge="−38 %",
            ),
            promo(
                name="Lederstiefel",
                price="119,00 €",
                old="179,00 €",
                save="⏳ noch 2 T.",
                badge="−34 %",
            ),
            promo(name="Schal", price="19,00 €", old="29,00 €", save="⏳ noch 2 T.", badge="−34 %"),
            promo(name="Mütze", price="12,00 €", old="19,00 €", save="⏳ noch 3 T.", badge="−37 %"),
            promo(
                name="Handschuhe",
                price="15,00 €",
                old="24,00 €",
                save="⏳ noch 3 T.",
                badge="−38 %",
            ),
        ]
    )
    + "</div>",
    "<b>Общий таймер кампании и сортировка по остатку времени.</b> Сверху — до конца всей "
    "кампании, карточки идут от самой срочной. <b>Когда уместно:</b> кампания с одной датой "
    "окончания — Black Week, распродажа сезона, «последние дни». "
    '<span class="tag">реюз</span> сегментный отсчёт уже написан (волна aktionsmarkt), '
    "здесь он поднимается на уровень группы.",
)

_A5_COLS = [
    ("Basis", "89 €", "119 €", "✓ Ölwechsel<br>✓ Sichtprüfung<br>· · ·<br>· · ·", "", False),
    (
        "Komfort",
        "149 €",
        "219 €",
        "✓ Ölwechsel<br>✓ Sichtprüfung<br>✓ Bremsen<br>✓ Ersatzwagen",
        "border-color:#111827;border-width:2px",
        True,
    ),
    (
        "Premium",
        "249 €",
        "349 €",
        "✓ alles aus Komfort<br>✓ Klima-Service<br>✓ Hol- und Bringdienst<br>✓ TÜV",
        "",
        False,
    ),
]


def _col(name, price, old, feats, highlight, popular):
    """Колонка сравнения (A5) — отдельной функцией: f-строка не терпит кавычек внутри."""
    badge = '<span class="badge" style="margin-bottom:5px">Beliebt</span>' if popular else ""
    return (
        f'<div class="box" style="flex:1;padding:10px;{highlight}">{badge}'
        f'<div class="name" style="font-size:12px">{name}</div>'
        f'<div style="margin:5px 0"><span class="price red" style="font-size:16px">{price}</span> '
        f'<span class="old">{old}</span></div>'
        f'<div class="sub" style="line-height:1.7">{feats}</div>'
        f'<div class="btn" style="width:100%;box-sizing:border-box;margin-top:8px">Buchen</div>'
        "</div>"
    )


A5 = page(
    "A5 · Vergleich",
    "Gruppenseite · Angebote nebeneinander",
    AK_NOTE
    + '<div class="sec"><div class="h1">Wartungs-Pakete</div>'
    + '<div class="sub">Drei Pakete — Sie zahlen einmal, wir erledigen alles.</div></div>'
    + '<div class="sec" style="padding-top:2px"><div class="row">'
    + "".join(_col(*args) for args in _A5_COLS)
    + "</div></div>",
    "<b>Акции группы стоят рядом и сравниваются.</b> Одинаковая высота колонок, состав "
    "списком, средняя выделена как рекомендованная. <b>Когда уместно:</b> группа, где позиции "
    "конкурируют между собой — пакеты обслуживания, тарифы, абонементы, наборы меню. "
    '<span class="tag new">нового в движке</span> колоночное сравнение — сейчас акции всегда '
    "выводятся равноправной сеткой.",
)

# ─────────────────────────── сводка ───────────────────────────

MAIN = page(
    "Vorlagen der Kategorieseiten",
    "DL-20 · на согласование",
    '<div class="sec"><div class="h1">Пять шаблонов на каждую из двух страниц</div>'
    + '<div class="sub">Запрос владельца 03.09: «макеты категорий товара и категорий акций, '
    + "5 шт, та же механика выбора шаблона и наследования через общие настройки».</div></div>"
    + '<div class="sec" style="padding-top:0">'
    + '<div class="h2">Страница категории товаров <span>/sortiment/&lt;kategorie&gt;/</span></div>'
    + '<table class="cmp"><tr><th style="width:96px">Шаблон</th><th>Что меняется</th>'
    + "<th style='width:150px'>Кому</th></tr>"
    + "<tr><td><b>P1 Schaufenster</b></td><td>первый товар — широкой картой с описанием и "
    + "кнопкой, остальные сеткой</td><td>есть флагман</td></tr>"
    + "<tr><td><b>P2 Navigator</b></td><td>подкатегории и фильтры боковой колонкой, товары "
    + "справа</td><td>большой каталог</td></tr>"
    + "<tr><td><b>P3 Magazin</b></td><td>обложка + по 2 крупные карточки с описанием</td>"
    + "<td>мало и дорого</td></tr>"
    + "<tr><td><b>P4 Mosaik</b></td><td>плитки разного размера, первая — четверть экрана</td>"
    + "<td>сильные фото</td></tr>"
    + "<tr><td><b>P5 Kompakt</b></td><td>указатель подкатегорий колонками + сетка по 6</td>"
    + "<td>сотни артикулов</td></tr></table>"
    + '<div class="sub" style="margin-top:6px">Уже есть и остаются: Standard, Kopfbild, Sets, '
    + "Preisliste, Regale, Tabs — новые пять их не повторяют.</div></div>"
    + '<div class="sec" style="padding-top:4px">'
    + '<div class="h2">Страница группы акций <span>/aktionen/?gruppe=…</span></div>'
    + '<div class="sub" style="margin-bottom:6px">Сегодня этой страницы фактически нет: '
    + "фильтр по группе отдаёт плоскую сетку под общим заголовком, названия группы не видно.</div>"
    + '<table class="cmp"><tr><th style="width:96px">Шаблон</th><th>Что меняется</th>'
    + "<th style='width:150px'>Кому</th></tr>"
    + "<tr><td><b>A1 Schaufenster</b></td><td>заголовок группы + главный дил широкой картой</td>"
    + "<td>есть «паровоз»</td></tr>"
    + "<tr><td><b>A2 Prospekt</b></td><td>плотная сетка по 5–6, крупные цены, шапка со сроком</td>"
    + "<td>продукты, дискаунтер</td></tr>"
    + "<tr><td><b>A3 Magazin</b></td><td>обложка группы + условия акции на карточке</td>"
    + "<td>услуги и пакеты</td></tr>"
    + "<tr><td><b>A4 Countdown</b></td><td>общий таймер кампании, сортировка по остатку</td>"
    + "<td>Black Week, сезон</td></tr>"
    + "<tr><td><b>A5 Vergleich</b></td><td>колонки рядом, состав списком, «Beliebt»</td>"
    + "<td>пакеты и тарифы</td></tr></table></div>"
    + '<div class="sec" style="padding-top:4px">'
    + '<div class="h2">Механика — та же, что у форм карточки (DL-19)</div>'
    + '<table class="cmp"><tr><th style="width:150px">Слой</th><th>Где задаётся</th></tr>'
    + "<tr><td>для всего сайта</td><td>Studio → «Design»: плитки с мини-макетом и "
    + "предпросмотром, отдельно для категорий товара и для групп акций</td></tr>"
    + "<tr><td>для одной категории</td><td>карточка категории в кабинете — поле уже есть "
    + "(«Seitenvorlage»), к нему добавляются новые плитки</td></tr>"
    + "<tr><td>для одной группы акций</td><td>список акций в кабинете: у каждой группы — свой "
    + "выбор (модели группы нет, поэтому хранится в настройках сайта по имени группы)</td></tr>"
    + "<tr><td><b>приоритет</b></td><td>выбор у категории/группы <b>побеждает</b> общий "
    + "дефолт; пустое значение = «как на всём сайте»</td></tr></table></div>",
    "<b>Что здесь ново по сравнению с DL-19.</b> Там форма карточки была свойством витрины "
    "плюс отдельной позиции. Здесь то же правило переносится на КОМПОЗИЦИЮ страницы. "
    "Побочно закрывается реальный пробел: у группы акций впервые появляется собственная "
    "страница с названием, а у категории товара — общий дефолт (сегодня шаблон задаётся "
    "только поштучно, и владелец обязан выставить его в каждой категории вручную). "
    '<span class="tag">решение владельца</span> какие из десяти делаем и в каком порядке; '
    "по умолчанию беру все десять.",
)

FILES = {
    "Main.dc.html": MAIN,
    "P1.dc.html": P1,
    "P2.dc.html": P2,
    "P3.dc.html": P3,
    "P4.dc.html": P4,
    "P5.dc.html": P5,
    "A1.dc.html": A1,
    "A2.dc.html": A2,
    "A3.dc.html": A3,
    "A4.dc.html": A4,
    "A5.dc.html": A5,
}
for name, html in FILES.items():
    (HERE / name).write_text(html, encoding="utf-8")

canvas = {
    "artboards": [
        {"file": "Main.dc.html", "x": 0, "y": 0, "w": 800, "h": 1180, "title": "Сводка"},
        {"file": "P1.dc.html", "x": 900, "y": 0, "w": 800, "h": 690, "title": "P1 · Schaufenster"},
        {"file": "P2.dc.html", "x": 1800, "y": 0, "w": 800, "h": 600, "title": "P2 · Navigator"},
        {"file": "P3.dc.html", "x": 2700, "y": 0, "w": 800, "h": 700, "title": "P3 · Magazin"},
        {"file": "P4.dc.html", "x": 3600, "y": 0, "w": 800, "h": 620, "title": "P4 · Mosaik"},
        {"file": "P5.dc.html", "x": 4500, "y": 0, "w": 800, "h": 620, "title": "P5 · Kompakt"},
        {
            "file": "A1.dc.html",
            "x": 900,
            "y": 820,
            "w": 800,
            "h": 830,
            "title": "A1 · Schaufenster",
        },
        {"file": "A2.dc.html", "x": 1800, "y": 820, "w": 800, "h": 620, "title": "A2 · Prospekt"},
        {"file": "A3.dc.html", "x": 2700, "y": 820, "w": 800, "h": 700, "title": "A3 · Magazin"},
        {"file": "A4.dc.html", "x": 3600, "y": 820, "w": 800, "h": 780, "title": "A4 · Countdown"},
        {"file": "A5.dc.html", "x": 4500, "y": 820, "w": 800, "h": 620, "title": "A5 · Vergleich"},
    ],
    "launch": {"view": "canvas"},
}
(HERE / "canvas.json").write_text(
    json.dumps(canvas, ensure_ascii=False, indent=1), encoding="utf-8"
)
print("готово:", ", ".join(FILES))
