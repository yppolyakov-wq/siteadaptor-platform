"""DL-16 «Anzeigeformen» — генератор артбордов канваса (wireframe-язык DL-12).
python _generate.py → *.dc.html + canvas.json (рядом). Затем seed-canvas.mjs."""

import json
from pathlib import Path

HERE = Path(__file__).parent
CSS = """
    body { margin: 0; font-family: Inter, "Segoe UI", sans-serif; color: #1f2937; }
    .wf { width: 720px; background: #ffffff; box-sizing: border-box; border: 1px solid #e5e7eb; }
    .wf.m { width: 390px; }
    .bar { display: flex; align-items: center; justify-content: space-between; padding: 10px 18px; border-bottom: 1px solid #e5e7eb; font-size: 11px; color: #6b7280; }
    .bar b { color: #111827; font-size: 12px; }
    .bx { background: #f3f4f6; border: 1px dashed #c7cdd6; border-radius: 6px; color: #4b5563; font-size: 11px; display: flex; align-items: center; justify-content: center; text-align: center; padding: 6px; box-sizing: border-box; line-height: 1.3; }
    .bx.img { background: repeating-linear-gradient(135deg, #e5e7eb 0 6px, #f3f4f6 6px 12px); }
    .bx.acc { background: #111827; color: #fff; border-style: solid; border-color: #111827; }
    .bx.soft { background: #eef2ff; border-color: #c7d2fe; color: #3730a3; }
    .bx.red { background: #dc2626; color: #fff; border: none; font-weight: 700; }
    .bx.plain { background: #fff; border-style: solid; }
    .bx.txt { justify-content: flex-start; text-align: left; align-items: flex-start; flex-direction: column; gap: 3px; }
    .sec { padding: 12px 18px; }
    .ttl { font-size: 11px; font-weight: 600; color: #111827; margin-bottom: 6px; display: flex; justify-content: space-between; }
    .ttl span { font-weight: 400; color: #9ca3af; }
    .grid { display: grid; gap: 8px; }
    .cap { padding: 12px 18px 14px; background: #fafafa; border-top: 1px solid #e5e7eb; font-size: 11px; line-height: 1.5; color: #374151; }
    .cap b { color: #111827; }
    .tag { display: inline-block; font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 999px; background: #dcfce7; color: #166534; margin-right: 4px; }
    .tag.code { background: #fef3c7; color: #92400e; }
    .tag.dec { background: #dbeafe; color: #1e40af; }
    .card { border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; background: #fff; position: relative; font-size: 10px; }
    .card .ph { background: repeating-linear-gradient(135deg, #e5e7eb 0 6px, #f3f4f6 6px 12px); }
    .card .b { padding: 6px 8px; }
    .badge { position: absolute; top: 6px; left: 6px; background: #dc2626; color: #fff; font-weight: 700; font-size: 9px; padding: 2px 6px; border-radius: 999px; }
    .price { font-weight: 800; color: #dc2626; font-size: 13px; }
    .old { color: #9ca3af; text-decoration: line-through; font-size: 9px; }
    .gp { color: #6b7280; font-size: 8px; }
    .chip { display: inline-block; border: 1px solid #d1d5db; border-radius: 999px; padding: 2px 8px; font-size: 9px; color: #374151; margin-right: 4px; background: #fff; }
    .chip.on { background: #111827; color: #fff; border-color: #111827; }
    .tab { display: inline-block; padding: 4px 10px; font-size: 10px; border-bottom: 2px solid transparent; color: #6b7280; }
    .tab.on { border-color: #111827; color: #111827; font-weight: 600; }
    .strip { display: flex; gap: 8px; overflow: hidden; position: relative; }
    .strip > * { flex: 0 0 auto; }
    .arrow { width: 22px; height: 22px; border-radius: 999px; background: #fff; border: 1px solid #d1d5db; display: flex; align-items: center; justify-content: center; font-size: 11px; color: #111827; box-shadow: 0 1px 3px rgba(0,0,0,.12); }
    .dots { display: flex; gap: 4px; justify-content: center; margin-top: 4px; }
    .dots i { width: 6px; height: 6px; border-radius: 999px; background: #d1d5db; display: block; }
    .dots i.on { background: #111827; }
    table.t { width: 100%; border-collapse: collapse; font-size: 10.5px; }
    table.t th { text-align: left; color: #6b7280; font-weight: 600; padding: 4px 6px; border-bottom: 1px solid #e5e7eb; }
    table.t td { padding: 4px 6px; border-bottom: 1px solid #f3f4f6; vertical-align: top; }
    .crumb { font-size: 10px; color: #6b7280; padding: 6px 18px 0; }
    .h1 { font-size: 16px; font-weight: 800; color: #111827; padding: 4px 18px 0; }
"""
HEAD = (
    '<!doctype html>\n<html>\n<head>\n  <meta charset="utf-8">\n  <script src="./support.js"></script>\n</head>\n<body>\n<x-dc>\n<helmet>\n'
    '  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap">\n'
    f"  <style>{CSS}  </style>\n</helmet>\n"
)
TAIL = "\n</x-dc>\n</body>\n</html>\n"


def wrap(title, sub, body, cap, mobile=False):
    cls = "wf m" if mobile else "wf"
    return (
        HEAD
        + f'<div class="{cls}"><div class="bar"><b>{title}</b><span>{sub}</span><span></span></div>{body}<div class="cap">{cap}</div></div>'
        + TAIL
    )


def bx(t, h=40, cls="", st=""):
    return f'<div class="bx {cls}" style="height:{h}px;{st}">{t}</div>'


def grid(cols, items, gap=8, st=""):
    return f'<div class="grid" style="grid-template-columns:{cols};gap:{gap}px;{st}">{"".join(items)}</div>'


def sec(title, inner, note=""):
    return f'<div class="sec"><div class="ttl">{title}<span>{note}</span></div>{inner}</div>'


def card(
    name="Orangensaft 1 L", price="1,99 €", old="2,49 €", ph=64, badge="−20 %", extra="", w=""
):
    b = f'<span class="badge">{badge}</span>' if badge else ""
    return (
        f'<div class="card" style="{w}">{b}<div class="ph" style="height:{ph}px"></div>'
        f'<div class="b"><div>{name}</div><div><span class="price">{price}</span> <span class="old">{old}</span></div>'
        f'<div class="gp">2,49 € / l · bis 09.09.</div>{extra}</div></div>'
    )


def strip(cards, left=False):
    arr_l = '<div class="arrow" style="position:absolute;left:4px;top:40%">‹</div>' if left else ""
    return f'<div class="strip">{"".join(cards)}{arr_l}<div class="arrow" style="position:absolute;right:4px;top:40%">›</div></div>'


def toolbar(extra=""):
    return grid(
        "auto 1fr auto auto",
        [
            bx("⚙ Filter", 26, "plain", "width:70px"),
            bx("", 26, "", "background:none;border:none"),
            bx("Sortieren ▾", 26, "plain", "width:90px"),
            bx("− 3 + · ☰ ⊞", 26, "plain", "width:110px"),
        ],
        6,
    )


def topbar():
    return '<div class="crumb">Logo · Aktionen · Sortiment · Treue · Über uns &nbsp;&nbsp;&nbsp;&nbsp; 🔍 ♡ 🛒</div>'


boards = {}
canvas = {"artboards": [], "annotations": [], "launch": {"view": "canvas"}}


def add(name, title, html, x, y, w=720, h=700):
    boards[name] = html
    canvas["artboards"].append(
        {"file": f"{name}.dc.html", "title": title, "x": x, "y": y, "w": w, "h": h}
    )


# ── Main ─────────────────────────────────────────────────────────────────────
rows = [
    (
        "K",
        "Kategorie",
        "K1 Kopfbild-Slider · K2 Regale · K3 Tabs · K5 Magazin · K4 Facetten links",
        "K1 + K2 + K3",
        "S/M/S",
    ),
    (
        "A",
        "Aktionen",
        "A1 Wochen-Tabs · A2 Prospekt-Seite · A3 Gruppen-Slider · A4 Tabelle · A5 Karte+Suche",
        "A3 + A4 + A5",
        "S/S/XS",
    ),
    (
        "P",
        "Produktkarte",
        "P1 Etikett · P2 Hover-Slider · P3 Info-Reihe (+ Standard/overlay/compact)",
        "P1 + P2",
        "S/S",
    ),
    (
        "D",
        "Produktdetail",
        "D1 Galerie-Slider · D2 Tabs/Akkordeon · D3 Vertrauensleiste · D4 Ленты · D5 Порядок секций · D6 Preisverlauf",
        "D1 + D3 + D4 + D2",
        "S/XS/S/S",
    ),
    (
        "AK",
        "Aktionskarte",
        "AK1 Preis-zuerst · AK2 Coupon · AK3 Countdown-Ring · AK4 Gruppe + Sie sparen",
        "AK1 + AK4",
        "S/XS",
    ),
    (
        "AD",
        "Aktionsdetail",
        "AD1 Ziel-Karte · AD2 Bedingungen · AD3 Weitere Aktionen · AD4 Prospekt-Detail · AD5 Свайп-галерея",
        "AD1 + AD2 + AD3",
        "XS/XS/XS",
    ),
    (
        "S",
        "Slider & Ansichten",
        "S1 Slider-Primitiv · S2 Лента только на мобайле · S3 Tabs/Akkordeon/Timeline/Tabelle · S4 Фиксы",
        "S1 + S4 (фундамент)",
        "M/XS",
    ),
]
tbl = '<table class="t"><tr><th>Код</th><th>Поверхность</th><th>Варианты (артборды)</th><th>Пакет v1</th><th>Цена</th></tr>'
for c, s, v, r, p in rows:
    tbl += f"<tr><td><b>{c}</b></td><td>{s}</td><td>{v}</td><td><b>{r}</b></td><td>{p}</td></tr>"
tbl += "</table>"
legend = (
    '<div style="margin-top:8px"><span class="tag">есть</span> уже в коде · <span class="tag code">код</span> нужен код · '
    '<span class="tag dec">решение</span> ждёт ответа владельца</div>'
)
found = bx(
    "Найдено разведкой: у акции НЕ показаны gültig ab · окно happy-hour · max/Kunde · срок резерва · САМА ЦЕЛЬ акции; на /aktionen/ поиск без входа; "
    "категория без крошек и лайтбокса; ленты без стрелок/точек; archetype-cover крутится на телефоне.",
    62,
    "soft txt",
)
add(
    "Main",
    "Сводка",
    wrap(
        "DL-16 · Anzeigeformen",
        "категория · акции · карточки · детали · слайдеры",
        sec("Что предлагается — сводка", tbl + legend) + sec("Пробелы (§1 дока)", found),
        "<b>Порядок v1:</b> S1 слайдер-примитив → акции (A3/A4/A5) → деталь акции (AD1–3) → карточки (AK1/P1/P2) → категория (K1/K2/K3) → деталь товара (D1/D3/D4/D2). "
        "Отложено: A1 (нужно «Vorschau» запланированных), A2/AD4 Prospekt, K4, D5, D6. Вопросы — док §5.",
    ),
    0,
    0,
    720,
    560,
)

# ── K1 Kopfbild-Slider ───────────────────────────────────────────────────────
k1 = topbar() + '<div class="crumb">Sortiment › <b>Getränke</b></div>'
k1 += sec(
    "Kopfbild als Slider (≤5 Fotos, без автопрокрутки на мобайле) + крошки",
    grid(
        "1fr 1fr",
        [
            bx(
                "Kicker · <b>Getränke</b><br>Beschreibung 2–3 строки<br><span class='chip on'>Angebot anfragen</span>",
                120,
                "txt plain",
            ),
            bx("Foto 1/3  ‹ ›", 120, "img")
            + '<div class="dots"><i class="on"></i><i></i><i></i></div>',
        ],
    ),
)
k1 += sec(
    "Unterkategorien",
    "<div>"
    + "".join(
        f'<span class="chip{" on" if i == 0 else ""}">{c}</span>'
        for i, c in enumerate(["Alle", "Säfte", "Wasser", "Limonade", "Kaffee"])
    )
    + "</div>",
)
k1 += sec(
    "Toolbar + Raster",
    toolbar()
    + '<div style="height:8px"></div>'
    + grid("repeat(4,1fr)", [card(ph=56) for _ in range(4)]),
)
add(
    "K1",
    "K1 · Kategorie · Kopfbild-Slider",
    wrap(
        "K1 · Kopfbild-Slider",
        "категория с фото",
        k1,
        "<b>K1.</b> Слайдер фото категории вместо статичного Kopfbild + <b>хлебные крошки</b> (сейчас только «← Alle») + лайтбокс. "
        "<span class='tag'>есть</span> archetype-cover, правила R5 · <span class='tag code'>код</span> крошки, слайдер на категории, гейт мобайла. Цена S.",
    ),
    820,
    0,
    720,
    640,
)


# ── K2 Regale ────────────────────────────────────────────────────────────────
def shelf(title, n):
    return sec(
        f"{title} · {n} &nbsp;→ Alle",
        strip(
            [card(ph=50, w="width:150px") for _ in range(4)]
            + [card(ph=50, w="width:150px;opacity:.5")]
        ),
    )


k2 = (
    topbar()
    + '<div class="crumb">Sortiment › <b>Catering</b></div><div class="h1">Catering · Speisekarte</div>'
)
k2 += shelf("Suppen", 8) + shelf("Beilagen", 9) + shelf("Ragouts", 8)
add(
    "K2",
    "K2 · Kategorie · Regale",
    wrap(
        "K2 · Regale («полки»)",
        "категории с подкатегориями",
        k2,
        "<b>K2.</b> Каждая подкатегория — строка «Название · N → Alle» + горизонтальная лента 5–6 карточек со стрелками и «peek» следующей (Lidl/REWE-App). "
        "Все подкатегории видны без прокрутки вниз, «Alle» ведёт на подкатегорию. <span class='tag'>есть</span> sf-scroll-grid · <span class='tag code'>код</span> S1 стрелки/точки + режим страницы категории. Цена M.",
    ),
    1640,
    0,
    720,
    620,
)

# ── K3 Tabs ──────────────────────────────────────────────────────────────────
k3 = topbar() + '<div class="crumb">Sortiment › <b>Catering</b></div><div class="h1">Catering</div>'
k3 += sec(
    "Sticky-Tabs подкатегорий (переключение без перезагрузки)",
    '<div style="border-bottom:1px solid #e5e7eb">'
    + "".join(
        f'<span class="tab{" on" if i == 1 else ""}">{t}</span>'
        for i, t in enumerate(
            ["Alle · 49", "Suppen · 8", "Beilagen · 9", "Ragouts · 8", "Saucen · 7", "Salate · 10"]
        )
    )
    + "</div>",
)
k3 += sec(
    "Raster der aktiven Unterkategorie",
    toolbar()
    + '<div style="height:8px"></div>'
    + grid(
        "repeat(4,1fr)",
        [card(name="Linsensuppe", price="4,90 €", old="", badge="", ph=56) for _ in range(8)],
    ),
)
add(
    "K3",
    "K3 · Kategorie · Tabs",
    wrap(
        "K3 · Tabs",
        "много подкатегорий, мало фото",
        k3,
        "<b>K3.</b> Подкатегории табами со счётчиком, липкая полоса; на телефоне — горизонтальный скролл табов. Смена таба = KAT-5 fetch-своп. "
        "<span class='tag'>есть</span> KAT-5 · <span class='tag code'>код</span> режим страницы + sticky. Цена S.",
    ),
    2460,
    0,
    720,
    620,
)

# ── A1 Wochen-Tabs ───────────────────────────────────────────────────────────
a1 = topbar() + '<div class="h1">Aktuelle Angebote</div>'
a1 += sec(
    "Wochen-Tabs",
    '<div style="border-bottom:1px solid #e5e7eb"><span class="tab on">Diese Woche · 14</span><span class="tab">Nächste Woche · 6</span></div>',
)
a1 += sec(
    "⏳ Endet bald",
    grid(
        "1fr 1fr",
        [
            bx("фото 38 % | Brötchen am Abend −50 % · 0,30 €", 44, "plain"),
            bx("фото 38 % | Toilettenpapier −35 % · 3,24 €", 44, "plain"),
        ],
    ),
)
a1 += sec("Ab Montag, 7.9.", grid("repeat(3,1fr)", [card(ph=48) for _ in range(3)]))
a1 += sec(
    "Ab Donnerstag, 10.9. &nbsp;<span class='chip'>Vorschau</span>",
    grid(
        "repeat(3,1fr)",
        [
            card(ph=48, badge="Ab Do.", extra="<div class='gp'>без ссылки до старта</div>")
            for _ in range(3)
        ],
    ),
)
add(
    "A1",
    "A1 · Aktionen · Wochen-Tabs",
    wrap(
        "A1 · Wochen-Tabs + Tage",
        "как Lidl/ALDI/PENNY (R1)",
        a1,
        "<b>A1.</b> Табы недель + секции по дню старта (`starts_at`); запланированные акции — карточками «Ab Do.» без ссылки (режим «Vorschau»). "
        "<span class='tag'>есть</span> promo_grouping=time (по концу) · <span class='tag dec'>решение</span> открыть запланированные как Vorschau · <span class='tag code'>код</span> группировка по старту. Цена M. Отложить до решения.",
    ),
    0,
    720,
    720,
    700,
)

# ── A2 Prospekt-Seite ────────────────────────────────────────────────────────
a2 = topbar() + '<div class="h1">Aktuelle Angebote</div>'
a2 += sec(
    "<span class='chip on'>Wochenangebote · 9</span> — «страница проспекта»",
    grid(
        "2fr 1fr 1fr",
        [
            card(
                ph=150,
                name="Bio-Gemüsekiste −20 %",
                price="19,92 €",
                old="24,90 €",
                w="grid-row:span 2",
            ),
            card(ph=60),
            card(ph=60),
            card(ph=60),
            card(ph=60),
        ],
    )
    + '<div style="height:8px"></div>'
    + grid("repeat(4,1fr)", [card(ph=40, w="font-size:9px") for _ in range(4)]),
)
a2 += sec(
    "<span class='chip on'>Anti-Food-Waste · 6</span>",
    grid(
        "2fr 1fr 1fr",
        [card(ph=110, w="grid-row:span 2"), card(ph=44), card(ph=44), card(ph=44), card(ph=44)],
    ),
)
add(
    "A2",
    "A2 · Aktionen · Prospekt-Seite",
    wrap(
        "A2 · Prospekt-Seite",
        "как печатный проспект",
        a2,
        "<b>A2.</b> Раскладка «проспекта»: 1 большая + 2 средних + 4 малых на «страницу» группы, заголовок стикером (Look-aware: prospekt/retro). "
        "CSS grid dense, первая карточка span 2. <span class='tag code'>код</span> стиль листинга `promo_list_style=prospekt` + порядок «featured первой». Цена M. После v1.",
    ),
    820,
    720,
    720,
    700,
)

# ── A3 Gruppen-Slider ────────────────────────────────────────────────────────
a3 = topbar() + '<div class="h1">Aktuelle Angebote &nbsp;<span class="chip">🔍 Suche</span></div>'
a3 += sec(
    "Chips",
    "<div>"
    + "".join(
        f'<span class="chip">{c}</span>'
        for c in ["Endet heute", "Diese Woche", "−20 %+", "−50 %+", "Reservierbar"]
    )
    + "</div>",
)
for t, n in (("⏳ Endet bald", 4), ("Wochenangebote", 9), ("Anti-Food-Waste", 6), ("Räumung", 3)):
    a3 += sec(
        f"{t} · {n} &nbsp;→ Alle",
        strip(
            [
                card(ph=44, w="width:160px", extra="<div class='gp'>Sie sparen 0,50 €</div>")
                for _ in range(4)
            ]
            + [card(ph=44, w="width:160px;opacity:.5")]
        ),
    )
add(
    "A3",
    "A3 · Aktionen · Gruppen-Slider",
    wrap(
        "A3 · Gruppen-Slider",
        "все группы выше сгиба",
        a3,
        "<b>A3.</b> Каждая группа — строка + лента со стрелками; «Alle» = фильтр группы (чип). Плюс <b>A5</b>: поле поиска на странице, на карточке чип группы и «Sie sparen». "
        "<span class='tag'>есть</span> группы, чипы, ?q= · <span class='tag code'>код</span> S1 + режим страницы «Slider». Цена S. Рекомендуется в v1.",
    ),
    1640,
    720,
    720,
    700,
)

# ── A4 Tabelle ───────────────────────────────────────────────────────────────
a4 = topbar() + '<div class="h1">Aktuelle Angebote</div>'
a4 += sec(
    "Ansicht: <span class='chip'>Karten</span><span class='chip on'>Liste</span>",
    '<table class="t"><tr><th></th><th>Angebot</th><th>Gruppe</th><th>statt</th><th>Preis</th><th>Sie sparen</th><th>Grundpreis</th><th>bis</th><th></th></tr>'
    + "".join(
        f'<tr><td><div class="ph" style="width:28px;height:28px;background:#e5e7eb;border-radius:4px"></div></td><td>{n}</td><td><span class="chip">{g}</span></td><td class="old">{o}</td><td class="price">{p}</td><td>{s}</td><td class="gp">{gp}</td><td>{b}</td><td>♡</td></tr>'
        for n, g, o, p, s, gp, b in [
            (
                "Orangensaft 1 L",
                "Woche",
                "2,49 €",
                "1,99 €",
                "0,50 € (−20 %)",
                "1,99 €/l",
                "07.09.",
            ),
            ("Gouda jung 400 g", "Woche", "3,49 €", "2,79 €", "0,70 €", "6,98 €/kg", "09.09."),
            (
                "Toilettenpapier 10er",
                "Räumung",
                "4,99 €",
                "3,24 €",
                "1,75 € (−35 %)",
                "0,32 €/Rolle",
                "heute",
            ),
            (
                "Waschmittel 2 kg",
                "Räumung",
                "8,99 €",
                "5,39 €",
                "3,60 € (−40 %)",
                "2,70 €/kg",
                "16.09.",
            ),
        ]
    )
    + "</table>",
)
add(
    "A4",
    "A4 · Aktionen · Tabelle",
    wrap(
        "A4 · Tabelle",
        "для сравнения",
        a4,
        "<b>A4.</b> Посетительский вид «Liste»: одна строка на акцию — сравнить цены и сроки за секунду; сортировка по столбцам = существующие сорты. "
        "Серверный `?ansicht=liste` как у каталога (KAT-5 без перезагрузки). <span class='tag code'>код</span> шаблон строки + тумблер. Цена S.",
    ),
    2460,
    720,
    720,
    520,
)


# ── P1 Produktkarte ──────────────────────────────────────────────────────────
def etikett():
    return (
        '<div class="card"><div class="ph" style="height:64px"></div><div style="position:absolute;top:6px;right:6px;background:#fff;border:2px solid #111;padding:3px 6px;text-align:right">'
        '<div class="price" style="font-size:15px;color:#111">1,99 €</div><div class="gp">1,99 €/l</div></div><div class="b"><div>Orangensaft 1 L</div><div class="old">statt 2,49 € · −20 %</div></div></div>'
    )


def hover():
    return (
        '<div class="card"><div class="ph" style="height:64px"></div><div class="arrow" style="position:absolute;left:4px;top:24px;width:18px;height:18px">‹</div><div class="arrow" style="position:absolute;right:4px;top:24px;width:18px;height:18px">›</div>'
        '<div class="dots" style="position:absolute;top:50px;left:0;right:0"><i class="on"></i><i></i><i></i></div><div class="b"><div>Studio Nordwind Jacke</div><div><span class="price">89 €</span></div><div class="gp">3 Fotos · Farben: ● ● ●</div></div></div>'
    )


def inforow():
    return (
        '<div class="card" style="display:flex;align-items:center;gap:8px;padding:6px"><div class="ph" style="width:56px;height:44px;border-radius:6px"></div>'
        '<div style="flex:1"><div><b>Linsensuppe</b> 🌱 🌾</div><div class="gp">Allergene: A, G · 380 ml · 12,90 €/l</div></div><div><span class="price">4,90 €</span></div><div class="bx acc" style="width:26px;height:26px;border-radius:999px">+</div></div>'
    )


p1 = sec(
    "Standard (сейчас) · Etikett (P1)",
    grid("1fr 1fr", [card(ph=64, name="Orangensaft 1 L"), etikett()]),
)
p1 += sec("Hover-Slider (P2) · Info-Reihe (P3)", grid("1fr 1fr", [hover(), inforow()]))
p1 += sec(
    "Оси, которые уже есть",
    '<div><span class="chip">card_style: "" / overlay / compact</span><span class="chip">media_shape: round / wide</span><span class="chip">card_chrome: hard / hairline / line</span></div>',
)
add(
    "P1",
    "P1–P3 · Produktkarte · Formen",
    wrap(
        "P · Produktkarte",
        "новые значения card_style",
        p1,
        "<b>P1 Etikett</b> — цена первой (R3), плашка-ценник в углу, Grundpreis под ней. <b>P2 Hover-Slider</b> — у товара с ≥2 фото точки/стрелки, свайп на мобайле. "
        "<b>P3 Info-Reihe</b> — горизонтальная строка для гастро (диеты, аллергены, Grundpreis). <span class='tag code'>код</span> ветки `card_style` с паритет-замком «"
        " байт-в-байт». Цена S каждая.",
    ),
    0,
    1520,
    720,
    560,
)

# ── D1 Produktdetail Desktop ─────────────────────────────────────────────────
d1 = topbar() + '<div class="crumb">Sortiment › Getränke › <b>Orangensaft 1 L</b></div>'
d1 += sec(
    "Galerie-Slider (D1) + Kaufbox + Vertrauensleiste (D3)",
    grid(
        "40px 1fr 1fr",
        [
            grid(
                "1fr",
                [
                    bx("", 34, "img"),
                    bx("", 34, "img", "outline:2px solid #111"),
                    bx("", 34, "img"),
                    bx("", 34, "img"),
                ],
                4,
            ),
            bx("Hauptfoto 4:3 · 🔍 Zoom · ‹ ›", 160, "img"),
            bx(
                "Getränke<br><b style='font-size:13px'>Orangensaft 1 L</b><br>★ 4,6 (12)<br><span class='price' style='font-size:16px'>1,99 €</span> <span class='old'>2,49 €</span> · 1,99 €/l<br>"
                "<span class='chip'>🏬 Abholung heute</span><span class='chip'>🚚 Lieferung</span><span class='chip'>🕒 Mo–Sa 8–20</span><br>"
                "<span class='chip on' style='padding:4px 14px'>In den Warenkorb</span> ♡",
                160,
                "txt plain",
            ),
        ],
    ),
)
d1 += sec(
    "Tabs statt langer Spalte (D2)",
    '<div style="border-bottom:1px solid #e5e7eb"><span class="tab on">Beschreibung</span><span class="tab">Details</span><span class="tab">Bewertungen · 12</span></div>'
    + bx("Текст активной вкладки", 40, "plain"),
)
d1 += sec(
    "Passt dazu (D4) &nbsp;→ Alle",
    strip(
        [card(ph=40, w="width:120px", badge="") for _ in range(5)]
        + [card(ph=40, w="width:120px;opacity:.5", badge="")]
    ),
)
d1 += sec(
    "Zuletzt angesehen (D4)",
    strip([card(ph=36, w="width:100px", badge="", old="") for _ in range(6)]),
)
add(
    "D1",
    "D1–D4 · Produktdetail · Desktop",
    wrap(
        "D · Produktdetail",
        "десктоп",
        d1,
        "<b>D1</b> вертикальные миниатюры + зум (сейчас 5 миниатюр сеткой). <b>D3</b> Vertrauensleiste из данных тенанта. <b>D2</b> табы/аккордеон вместо колонки. <b>D4</b> ленты «Passt dazu» (вместо сетки «Mehr aus Kategorie») и «Zuletzt angesehen» (сессия). "
        "<span class='tag'>есть</span> галерея, лайтбокс, sticky-aside · <span class='tag code'>код</span> S1, крошки, табы, сессия. Цена S/XS/S/S.",
    ),
    820,
    1520,
    720,
    740,
)

# ── D2 Mobil ─────────────────────────────────────────────────────────────────
d2 = (
    '<div class="crumb">‹ Getränke</div>'
    + sec(
        "Swipe-Galerie",
        bx("Foto 2/4 (свайп)", 200, "img")
        + '<div class="dots"><i></i><i class="on"></i><i></i><i></i></div>',
    )
    + sec(
        "",
        bx(
            "<b style='font-size:13px'>Orangensaft 1 L</b><br>★ 4,6 (12)<br><span class='price' style='font-size:16px'>1,99 €</span> <span class='old'>2,49 €</span> · 1,99 €/l<br><span class='chip'>🏬 heute</span><span class='chip'>🚚</span><span class='chip'>🕒 8–20</span>",
            124,
            "txt plain",
        ),
    )
    + sec(
        "Akkordeon",
        grid(
            "1fr",
            [
                bx("Beschreibung ▾", 26, "plain"),
                bx("Details ▸", 26, "plain"),
                bx("Bewertungen · 12 ▸", 26, "plain"),
            ],
            4,
        ),
    )
    + sec("Passt dazu", strip([card(ph=40, w="width:110px", badge="") for _ in range(4)]))
    + sec(
        "",
        bx(
            "<span class='price'>1,99 €</span> &nbsp;&nbsp; <span class='chip on' style='padding:5px 16px'>In den Warenkorb</span>",
            40,
            "plain",
            "position:sticky;bottom:0",
        ),
    )
)
add(
    "D2",
    "D2 · Produktdetail · Mobil",
    wrap(
        "D · Produktdetail",
        "мобайл 390",
        d2,
        "Свайп-галерея с точками (без миниатюр), аккордеон вместо колонки, sticky-buybar (уже есть), лента «Passt dazu» свайпом. Правило S2: «лента только на мобайле» — на десктопе те же товары сеткой.",
        mobile=True,
    ),
    1640,
    1520,
    390,
    760,
)


# ── AK1 Aktionskarte ─────────────────────────────────────────────────────────
def preisfirst():
    return (
        '<div class="card"><div style="background:#fff7ed;padding:6px 8px;border-bottom:1px solid #fed7aa"><span class="price" style="font-size:18px">1,99 €</span> <span class="old">statt 2,49 €</span> <span class="chip on" style="background:#dc2626;border-color:#dc2626">−20 %</span>'
        '<div class="gp">1,99 €/l · Sie sparen 0,50 €</div></div><div class="ph" style="height:52px"></div><div class="b"><div>Orangensaft 1 L</div><div class="gp"><span class="chip">Wochenangebote</span> bis 07.09.</div></div></div>'
    )


def coupon():
    return (
        '<div class="card" style="border-style:dashed;border-width:2px"><div class="ph" style="height:44px"></div><div class="b" style="border-top:2px dashed #d1d5db"><div>Bio-Gemüsekiste −20 %</div><div><span class="price">19,92 €</span> <span class="old">24,90 €</span></div>'
        '<div class="gp">📦 Online reservieren · Code <b>SPAR20</b> · Nur noch 5</div><div class="chip on" style="margin-top:3px">Reservieren</div></div></div>'
    )


def ring():
    return (
        '<div class="card"><span class="badge">−50 %</span><div class="ph" style="height:64px"></div><div style="position:absolute;top:34px;right:8px;width:34px;height:34px;border-radius:999px;border:4px solid #f59e0b;border-right-color:#e5e7eb;background:#fff;display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:700">3 h</div>'
        '<div class="b"><div>Brötchen am Abend −50 %</div><div><span class="price">0,30 €</span> <span class="old">0,60 €</span></div><div class="gp">⏳ endet in 3 Std · 🔁 jeden Tag</div></div></div>'
    )


ak = sec(
    "Сейчас · Preis-zuerst (AK1)",
    grid("1fr 1fr", [card(ph=64, extra="<div class='gp'>📅 bis 07.09.</div>"), preisfirst()]),
)
ak += sec("Coupon (AK2) · Countdown-Ring (AK3)", grid("1fr 1fr", [coupon(), ring()]))
add(
    "AK1",
    "AK1–AK3 · Aktionskarte · Formen",
    wrap(
        "AK · Aktionskarte",
        "формы карточки акции",
        ak,
        "<b>AK1 Preis-zuerst</b> — блок цены сверху (ALDI/HOFER/Marktguru), фото ниже; «Sie sparen» и чип группы (AK4/A5). <b>AK2 Coupon</b> — перфорация + код/«Reservieren» для 📦/mystery. "
        "<b>AK3 Countdown-Ring</b> — оставшееся время кольцом на фото. `discount_style` не трогаем (C1) — это формы карточки. <span class='tag code'>код</span> `card_style` для промо + per-Look CSS. Цена S/S/S.",
    ),
    2460,
    1320,
    720,
    560,
)

# ── AD1 Aktionsdetail Desktop ────────────────────────────────────────────────
ad = topbar() + '<div class="crumb">Aktionen › Wochenangebote › <b>Orangensaft −20 %</b></div>'
ad += sec(
    "Galerie + Preisblock + NEU: Ziel-Karte (AD1) и Bedingungen (AD2)",
    grid(
        "1fr 1fr",
        [
            bx("Hauptfoto 1:1 · миниатюры · ‹ ›", 230, "img"),
            bx(
                "<span class='price' style='font-size:22px'>1,99 €</span> <span class='old'>2,49 €</span> <span class='chip on' style='background:#dc2626;border-color:#dc2626'>−20 %</span><br>"
                "Sie sparen 0,50 € · 1,99 €/l · Niedrigster Preis 30 T.: 2,49 €<br>✓ Verfügbar · 🆕 · 📅 bis 07.09.<br>"
                "<div style='border:1px solid #e5e7eb;border-radius:8px;padding:5px;margin:4px 0;width:100%'><b>Gilt für</b> · ▣ Orangensaft 1 L → zum Produkt</div>"
                "<div style='border:1px solid #e5e7eb;border-radius:8px;padding:5px;width:100%'><b>Bedingungen</b><br>🕒 Mo–Mi 10–14 Uhr · 👤 max. 2 pro Kunde · 📦 Reservierung 24 h · 📅 gültig ab 07.09.</div>"
                "<span class='chip on' style='padding:5px 16px;margin-top:4px'>Jetzt kaufen</span>",
                230,
                "txt plain",
            ),
        ],
    ),
)
ad += sec(
    "Weitere Aktionen aus «Wochenangebote» (AD3) &nbsp;→ Alle",
    strip(
        [card(ph=40, w="width:120px") for _ in range(5)] + [card(ph=40, w="width:120px;opacity:.5")]
    ),
)
add(
    "AD1",
    "AD1–AD3 · Aktionsdetail · Desktop",
    wrap(
        "AD · Aktionsdetail",
        "десктоп",
        ad,
        "<b>AD1 Ziel-Karte</b> — цель акции (товар/услуга/номер/комбо) с фото и ссылкой: сейчас на детали её нет вовсе. <b>AD2 Bedingungen</b> — окно happy-hour, лимит на клиента, срок резерва, «gültig ab» (данные есть, показа нет). "
        "<b>AD3</b> лента акций той же группы (сейчас только на 410-странице). Всё XS, без миграций.",
    ),
    0,
    2340,
    720,
    620,
)

# ── AD2 Mobil Prospekt-Detail ────────────────────────────────────────────────
ad2 = (
    sec(
        "Full-bleed Foto + Preis-Sticker (Look-aware)",
        '<div style="position:relative">'
        + bx("Foto", 230, "img")
        + '<div style="position:absolute;right:10px;bottom:10px;background:#fde047;color:#111;border:2px solid #111;transform:rotate(-4deg);padding:6px 10px;font-weight:800;font-size:18px;box-shadow:3px 3px 0 #111">1,99 €<div style="font-size:9px;font-weight:600">statt 2,49 € · −20 %</div></div></div>',
    )
    + sec(
        "",
        bx(
            "<b style='font-size:13px'>Orangensaft −20 % — nur 40 Flaschen</b><br>Sie sparen 0,50 € · 1,99 €/l<br><span class='chip'>Wochenangebote</span> Nur noch 40<br>⏳ 2 T · 14 Std · 22 Min",
            90,
            "txt plain",
        ),
    )
    + sec("Gilt für", bx("▣ Orangensaft 1 L · zum Produkt →", 34, "plain"))
    + sec("Weitere Aktionen", strip([card(ph=40, w="width:110px") for _ in range(4)]))
    + sec(
        "",
        bx(
            "<span class='price'>1,99 €</span> &nbsp;&nbsp; <span class='chip on' style='padding:5px 16px'>Jetzt kaufen</span>",
            40,
            "plain",
        ),
    )
)
add(
    "AD2",
    "AD4 · Aktionsdetail · Mobil Prospekt",
    wrap(
        "AD4 · Prospekt-Detail",
        "мобайл 390",
        ad2,
        "Полноэкранное фото со стикером цены в стиле Look'а (prospekt — жёлтый, monochrom — чёрный квадрат…), под ним «Sie sparen», группа, дефицит, countdown, Ziel-Karte, лента, sticky-buybar. Цена S, после v1.",
        mobile=True,
    ),
    820,
    2340,
    390,
    760,
)

# ── S1 Slider-Primitiv ───────────────────────────────────────────────────────
s1 = sec(
    "Анатомия слайдера-примитива (S1)",
    '<div style="position:relative">'
    + strip(
        [card(ph=44, w="width:150px", badge="") for _ in range(4)]
        + [card(ph=44, w="width:150px;opacity:.45", badge="")],
        left=True,
    )
    + "</div>"
    + '<div class="dots"><i class="on"></i><i></i><i></i></div>'
    + '<div style="font-size:10px;color:#374151;margin-top:6px">‹ › стрелки (десктоп: при наведении/всегда — вопрос 2) · точки · snap · «peek» следующей карточки · свайп на тач · клавиатура ← → · <b>без автопрокрутки</b> · «Alle →» в заголовке · без JS = обычная overflow-лента</div>',
)
s1 += sec(
    "Где применяется",
    '<table class="t"><tr><th>Поверхность</th><th>Потребители</th></tr>'
    "<tr><td>Категория</td><td>K1 фото-слайдер, K2 полки подкатегорий</td></tr><tr><td>Акции</td><td>A3 группы, AD3 «Weitere Aktionen»</td></tr>"
    "<tr><td>Деталь товара</td><td>D1 галерея (мобайл свайп), D4 «Passt dazu» / «Zuletzt angesehen»</td></tr><tr><td>Главная</td><td>секции с `scroll` (уже лента — получают стрелки/точки даром), похожие наборы (MEN-21)</td></tr></table>",
)
s1 += sec(
    "Другие виды вывода (S3) — по одному потребителю",
    grid(
        "repeat(5,1fr)",
        [
            bx("<b>Tabs</b><br>K3, D2", 54, "plain"),
            bx("<b>Akkordeon</b><br>D2 мобайл", 54, "plain"),
            bx("<b>Timeline</b><br>акции по времени (A1)", 54, "plain"),
            bx("<b>Tabelle</b><br>A4", 54, "plain"),
            bx("<b>Masonry / Bento</b><br>A2 Prospekt", 54, "plain"),
        ],
    ),
)
s1 += sec(
    "S4 фиксы (XS)",
    bx(
        "archetype-cover без автопрокрутки на телефоне · лайтбокс на фото Kopfbild · чекбокс «Scrollen» для каталога/категорий в Studio · countdown-sm с фолбэком даты · `menu_show_prices` на /sortiment/",
        44,
        "soft txt",
    ),
)
add(
    "S1",
    "S1–S4 · Slider-Primitiv & Ansichten",
    wrap(
        "S · Slider & andere Ansichten",
        "фундамент для K/A/D/AD",
        s1,
        "<b>S1</b> — один компонент вместо разрозненных overflow-полос: стрелки, точки, snap, peek, свайп, клавиатура; правила R5 (без автопрокрутки, ≤5 у hero, CTA дублируются). "
        "<b>S2</b> «лента только на мобайле» (Dawn swipe_on_mobile). <span class='tag'>есть</span> sf-scroll-grid + snap · <span class='tag code'>код</span> стрелки/точки/peek + Studio-чекбокс для листингов. Цена M.",
    ),
    1640,
    2340,
    720,
    700,
)

canvas["annotations"] = [
    {
        "id": "frage",
        "x": 2460,
        "y": 2340,
        "w": 300,
        "text": "На согласование: пакет v1 (Main, колонка «Пакет v1») + 5 вопросов в доке §5 (стрелки всегда/при наведении; Preis-zuerst дефолтом для deal_*; Vorschau запланированных; таблица — тумблер посетителя или режим владельца).",
    },
    {
        "id": "regeln",
        "x": 2460,
        "y": 2520,
        "w": 300,
        "text": "Всё без миграций; _discount_display/_promo_card не переписываем (C1 SF-аудита) — новые формы = ветки card_style с паритет-замком. Каждая форма — только при потребителе в демо.",
    },
]
for name, html in boards.items():
    (HERE / f"{name}.dc.html").write_text(html, encoding="utf-8")
(HERE / "canvas.json").write_text(
    json.dumps(canvas, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("boards:", len(boards))
