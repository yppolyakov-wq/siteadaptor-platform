"""DL-18.1 «Kartenformen» — три НОВЫЕ формы карточки товара/акции на согласование.

python _generate.py → *.dc.html + canvas.json (рядом). Затем seed-canvas.mjs.
Язык макета — тот же, что у канваса «Anzeigeformen» (DL-16), чтобы формы можно
было сравнивать между собой.
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
CSS = """
    body { margin: 0; font-family: Inter, "Segoe UI", sans-serif; color: #1f2937; }
    .wf { width: 760px; background: #ffffff; box-sizing: border-box; border: 1px solid #e5e7eb; }
    .wf.m { width: 390px; }
    .bar { display: flex; align-items: center; justify-content: space-between; padding: 10px 18px; border-bottom: 1px solid #e5e7eb; font-size: 11px; color: #6b7280; }
    .bar b { color: #111827; font-size: 12px; }
    .sec { padding: 14px 18px; }
    .ttl { font-size: 11px; font-weight: 600; color: #111827; margin-bottom: 8px; display: flex; justify-content: space-between; }
    .ttl span { font-weight: 400; color: #9ca3af; }
    .grid { display: grid; gap: 10px; }
    .cap { padding: 12px 18px 14px; background: #fafafa; border-top: 1px solid #e5e7eb; font-size: 11px; line-height: 1.55; color: #374151; }
    .cap b { color: #111827; }
    .tag { display: inline-block; font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 999px; background: #dcfce7; color: #166534; margin-right: 4px; }
    .tag.code { background: #fef3c7; color: #92400e; }
    .tag.dec { background: #dbeafe; color: #1e40af; }
    .ph { background: repeating-linear-gradient(135deg, #e5e7eb 0 6px, #f3f4f6 6px 12px); }
    .card { border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; background: #fff; position: relative; font-size: 10px; }
    .card .b { padding: 7px 9px; }
    .name { font-weight: 600; color: #111827; font-size: 11px; line-height: 1.25; }
    .price { font-weight: 800; color: #dc2626; font-size: 15px; }
    .price.k { color: #111827; }
    .old { color: #9ca3af; text-decoration: line-through; font-size: 10px; }
    .gp { color: #6b7280; font-size: 9px; }
    .save { color: #047857; font-size: 9px; font-weight: 600; }
    .badge { background: #dc2626; color: #fff; font-weight: 700; font-size: 10px; padding: 2px 7px; border-radius: 999px; display: inline-block; }
    .chip { display: inline-block; border: 1px solid #d1d5db; border-radius: 999px; padding: 2px 8px; font-size: 9px; color: #374151; margin-right: 4px; background: #fff; }
    .chip.on { background: #111827; color: #fff; border-color: #111827; }
    .btn { background: #111827; color: #fff; border-radius: 7px; padding: 6px 10px; font-size: 10px; font-weight: 600; text-align: center; }
    .btn.g { background: #047857; }
    table.cmp { border-collapse: collapse; width: 100%; font-size: 10.5px; }
    table.cmp th, table.cmp td { border: 1px solid #e5e7eb; padding: 5px 7px; text-align: left; vertical-align: top; }
    table.cmp th { background: #f9fafb; font-weight: 600; color: #111827; }
    /* N1 Regal-Preisschild — жёлтый ценник дискаунтера */
    .shelf { display: grid; grid-template-columns: 96px 1fr; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; background: #fff; }
    .shelf .ph { height: 100%; min-height: 84px; }
    .shelf .pricebox { background: #fde047; padding: 7px 9px; display: flex; flex-direction: column; justify-content: center; }
    .shelf .pricebox .price { color: #111827; font-size: 20px; line-height: 1; }
    /* N2 Lookbook — кадр 3:4, текст под ним, без рамки */
    .look { background: #fff; font-size: 10px; }
    .look .ph { aspect-ratio: 3 / 4; }
    .look .b { padding: 7px 0 0; }
    .look .brand { color: #9ca3af; font-size: 9px; letter-spacing: .04em; text-transform: uppercase; }
    /* N3 Deal-Kachel — горизонтальная плитка со всем на виду */
    .deal { display: grid; grid-template-columns: 132px 1fr; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; background: #fff; }
    .deal .ph { min-height: 100px; }
    .deal .b { padding: 9px 11px; display: flex; flex-direction: column; gap: 4px; }
    .row { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
    .cd { background: #fff7ed; border: 1px solid #fed7aa; color: #9a3412; border-radius: 6px; padding: 2px 6px; font-size: 9px; font-weight: 600; }
"""


def page(title, body):
    return (
        "<!-- сгенерировано _generate.py, правки — в нём -->\n"
        f"<style>{CSS}</style>\n<x-dc>\n{body}\n</x-dc>\n"
    )


def wf(head, sub, sections, cap, mobile=False):
    cls = "wf m" if mobile else "wf"
    inner = "".join(sections)
    return (
        f'<div class="{cls}"><div class="bar"><b>{head}</b><span>{sub}</span><span></span></div>'
        f'{inner}<div class="cap">{cap}</div></div>'
    )


def sec(title, hint, body):
    return f'<div class="sec"><div class="ttl">{title}<span>{hint}</span></div>{body}</div>'


# ---------------------------------------------------------------- N1 Regal
def shelf_card(name, price, old, gp, save, badge=""):
    b = f'<span class="badge">{badge}</span>' if badge else ""
    return (
        '<div class="shelf"><div class="ph"></div>'
        f'<div class="pricebox"><div class="row"><span class="price">{price}</span> {b}</div>'
        f'<div class="row"><span class="old">{old}</span><span class="gp">{gp}</span></div>'
        f'<div class="name">{name}</div><div class="save">{save}</div></div></div>'
    )


N1 = page(
    "N1 · Regal",
    wf(
        "N1 · «Regal» — ценник как в зале",
        "Referenz: ALDI/Kaufland Prospekt, elektronische Preisschilder",
        [
            sec(
                "Список товаров направления (десктоп, 2 колонки)",
                "цена ведёт, фото — опознавательный знак",
                '<div class="grid" style="grid-template-columns:1fr 1fr">'
                + shelf_card(
                    "Äpfel 1 kg", "1,99 €", "2,49 €", "1,99 €/kg", "Sie sparen 0,50 €", "−20 %"
                )
                + shelf_card(
                    "Bauernbrot 750 g", "0,99 €", "1,99 €", "1,32 €/kg", "Sie sparen 1,00 €"
                )
                + shelf_card(
                    "Gemahlener Kaffee 500 g",
                    "5,17 €",
                    "6,90 €",
                    "10,34 €/kg",
                    "Sie sparen 1,73 €",
                    "−25 %",
                )
                + shelf_card("Butter 250 g", "1,39 €", "1,99 €", "5,56 €/kg", "Sie sparen 0,60 €")
                + "</div>",
            ),
            sec(
                "Тот же список на телефоне",
                "одна колонка, высота строки 84 px",
                '<div class="grid" style="grid-template-columns:1fr;max-width:340px">'
                + shelf_card(
                    "Äpfel 1 kg", "1,99 €", "2,49 €", "1,99 €/kg", "Sie sparen 0,50 €", "−20 %"
                )
                + shelf_card("Tomaten 500 g", "2,24 €", "2,99 €", "4,48 €/kg", "Sie sparen 0,75 €")
                + "</div>",
            ),
        ],
        "<b>Что это.</b> Форма для продуктового: жёлтая плашка цены занимает две трети карточки, "
        "фото уменьшено до опознавательного квадрата слева. Цена, базовая цена (§ 5 PAngV) и выгода "
        "читаются с расстояния — как ценник на полке. <b>Кому.</b> Дискаунтер, супермаркет, "
        "напитки, дрогерия: там, где выбирают ЦЕНОЙ, а фото лишь подтверждает товар. "
        "<b>Плюс.</b> На экран помещается вдвое больше позиций, чем сеткой 4:3. "
        "<b>Минус.</b> Плохо продаёт «вкусный» товар (выпечка, готовая еда). "
        '<span class="tag code">код</span> новое значение оси `card_style="regal"` — карточка '
        "товара и акции; жёлтый цвет плашки берётся из акцента Look'а.",
    ),
)


# ---------------------------------------------------------------- N2 Lookbook
def look_card(brand, name, price, old="", note=""):
    o = f'<span class="old">{old}</span>' if old else ""
    n = f'<div class="gp">{note}</div>' if note else ""
    return (
        '<div class="look"><div class="ph"></div><div class="b">'
        f'<div class="brand">{brand}</div><div class="name">{name}</div>'
        f'<div class="row"><span class="price k">{price}</span>{o}</div>{n}</div></div>'
    )


N2 = page(
    "N2 · Lookbook",
    wf(
        "N2 · «Lookbook» — кадр решает",
        "Referenz: Zalando, COS, Arket, About You",
        [
            sec(
                "Сетка коллекции (десктоп, 3 колонки)",
                "кадр 3:4, ни рамок, ни теней",
                '<div class="grid" style="grid-template-columns:1fr 1fr 1fr">'
                + look_card("Studio Nordwind", "Sommerkleid Nordlicht", "79,90 €")
                + look_card("Studio Nordwind", "Leinenbluse Küste", "29,90 €", "39,90 €", "−25 %")
                + look_card("Studio Nordwind", "Strickcardigan Wolke", "89,90 €", "", "3 Farben")
                + "</div>",
            ),
            sec(
                "Наведение и выбор",
                "второй кадр по наведению · размеры без входа в карточку",
                '<div class="grid" style="grid-template-columns:1fr 1fr;max-width:420px">'
                + '<div class="look"><div class="ph" style="outline:2px solid #111827;outline-offset:-2px"></div>'
                '<div class="b"><div class="brand">кадр 2 из 3</div>'
                '<div class="name">Sommerkleid Nordlicht</div>'
                '<div class="row"><span class="price k">79,90 €</span></div>'
                '<div class="row" style="margin-top:3px"><span class="chip on">S</span>'
                '<span class="chip">M</span><span class="chip">L</span></div></div></div>'
                + '<div class="look"><div class="ph"></div><div class="b">'
                '<div class="brand">Sale</div><div class="name">Chino-Hose Deich</div>'
                '<div class="row"><span class="price">44,90 €</span>'
                '<span class="old">59,90 €</span></div>'
                '<div class="gp">Nur noch Größe 38 und 42</div></div></div>' + "</div>",
            ),
        ],
        "<b>Что это.</b> Форма для моды и товаров «настроения»: вертикальный кадр 3:4 во всю ширину "
        "плитки, подпись под фото маленькая и спокойная, скидка — тонкой строкой у цены, а не "
        "красной пилюлей. По наведению меняется кадр, размеры выбираются прямо в сетке. "
        "<b>Кому.</b> Одежда, украшения, интерьер, ремесло. "
        "<b>Плюс.</b> Кадр занимает 80 % плитки — витрина выглядит как каталог бренда. "
        "<b>Минус.</b> Требует хороших фотографий: со стоковыми кадрами форма разваливается. "
        '<span class="tag code">код</span> `card_style="lookbook"` + уже готовое листание фото '
        "(`card_slider`) как поведение по наведению.",
    ),
)


# ---------------------------------------------------------------- N3 Deal-Kachel
def deal_card(name, price, old, save, meta, cd="", btn="In den Warenkorb"):
    c = f'<span class="cd">{cd}</span>' if cd else ""
    return (
        '<div class="deal"><div class="ph"></div><div class="b">'
        f'<div class="name">{name}</div>'
        f'<div class="row"><span class="price">{price}</span><span class="old">{old}</span>'
        f'<span class="save">{save}</span></div>'
        f'<div class="row"><span class="gp">{meta}</span>{c}</div>'
        f'<div class="row" style="margin-top:2px"><span class="btn">{btn}</span>'
        '<span class="chip">Merken ♡</span></div></div></div>'
    )


N3 = page(
    "N3 · Deal-Kachel",
    wf(
        "N3 · «Deal-Kachel» — всё в одной строке",
        "Referenz: Marktguru, Lidl-App, MediaMarkt-Angebote",
        [
            sec(
                "Лента акций (десктоп, 2 колонки)",
                "цена · выгода · срок · действие — без перехода в карточку",
                '<div class="grid" style="grid-template-columns:1fr 1fr">'
                + deal_card(
                    "Orangensaft 1 L −20 %",
                    "1,99 €",
                    "2,49 €",
                    "−0,50 €",
                    "1,99 €/l · Wochenangebot",
                    "endet in 2 Tagen",
                )
                + deal_card(
                    "Bio-Gemüsekiste −20 %",
                    "19,92 €",
                    "24,90 €",
                    "−4,98 €",
                    "📦 Online reservieren · noch 5",
                    "",
                    "Reservieren",
                )
                + "</div>",
            ),
            sec(
                "Телефон",
                "фото 96 px, кнопка во всю ширину",
                '<div class="grid" style="grid-template-columns:1fr;max-width:340px">'
                + deal_card(
                    "Brötchen am Abend −50 %",
                    "0,30 €",
                    "0,60 €",
                    "−0,30 €",
                    "🔁 jeden Tag ab 18 Uhr",
                    "noch 3 Std",
                )
                + "</div>",
            ),
        ],
        "<b>Что это.</b> Горизонтальная плитка: слева фото, справа всё, ради чего заходят на "
        "страницу акций — цена, выгода, условие, срок и кнопка. Решение принимается без перехода "
        "в карточку. <b>Кому.</b> Страница «Aktionen», подборки, результаты поиска, e-mail-рассылка. "
        "<b>Плюс.</b> Самая высокая плотность смысла на пиксель; хорошо читается с телефона. "
        "<b>Минус.</b> Однообразна: подряд десять таких плиток выглядят как таблица. "
        '<span class="tag code">код</span> третий режим вывода `?ansicht=kacheln` рядом с '
        "«Karten | Liste» — сетка не меняется, меняется форма карточки.",
    ),
)

# ---------------------------------------------------------------- Vergleich
CMP = page(
    "Формы карточки — сводка",
    wf(
        "Kartenformen · сводка",
        "что уже есть и что предлагается",
        [
            sec(
                "Уже в системе",
                "переключается в Studio без кода",
                '<table class="cmp"><tr><th>Форма</th><th>Что делает</th><th>Где включена</th></tr>'
                "<tr><td><b>Standard</b></td><td>фото 1:1, под ним название и цена</td>"
                "<td>дефолт всех архетипов</td></tr>"
                "<tr><td><b>Overlay</b></td><td>текст поверх фото</td><td>демо одежды</td></tr>"
                "<tr><td><b>Compact</b></td><td>строка-прайс: фото слева, цена справа</td>"
                "<td>кафе, прайс-листы</td></tr>"
                "<tr><td><b>Etikett</b></td><td>ценник-этикетка под фото</td>"
                "<td>дил-сборки</td></tr>"
                "<tr><td><b>Preis zuerst</b> (акции)</td><td>плашка цены НАД фото</td>"
                "<td>демо продуктового</td></tr></table>",
            ),
            sec(
                "Предлагается добавить",
                "три формы, три разных рынка",
                '<table class="cmp"><tr><th>Форма</th><th>Рынок-референс</th><th>Сильна тем, что…</th>'
                "<th>Не подходит для…</th></tr>"
                "<tr><td><b>N1 Regal</b></td><td>ALDI, Kaufland, электронные ценники</td>"
                "<td>цена читается с расстояния, вдвое больше позиций на экране</td>"
                "<td>«вкусных» товаров, где решает кадр</td></tr>"
                "<tr><td><b>N2 Lookbook</b></td><td>Zalando, COS, Arket</td>"
                "<td>кадр занимает 80 % плитки, размер выбирается в сетке</td>"
                "<td>каталогов без хороших фото</td></tr>"
                "<tr><td><b>N3 Deal-Kachel</b></td><td>Marktguru, Lidl-App</td>"
                "<td>решение принимается без перехода в карточку</td>"
                "<td>длинных списков — однообразна</td></tr></table>",
            ),
            sec(
                "Что было предложено раньше и ждёт решения",
                "из канваса «Anzeigeformen» (DL-16)",
                '<table class="cmp"><tr><th>Форма</th><th>Идея</th></tr>'
                "<tr><td><b>AK2 Coupon</b></td><td>пунктирная рамка + код + «Reservieren» — "
                "для резервируемых и mystery-акций</td></tr>"
                "<tr><td><b>AK3 Countdown-Ring</b></td><td>оставшееся время кольцом на фото — "
                "для акций последнего дня</td></tr></table>",
            ),
        ],
        "<b>Как выбирать.</b> Форма карточки — свойство ВИТРИНЫ, а не товара: включается в Studio "
        "одним селектом и действует на весь сайт (у акций — своя ось). Поэтому три новые формы не "
        "конкурируют между собой, а закрывают три разных типа продажи: цена (N1), образ (N2), "
        "условие сделки (N3). <b>Стоимость.</b> Каждая форма — ветка в существующих партиалах "
        "карточки плюс значение оси в Studio; движки цен, скидок и наличия не меняются. "
        '<span class="tag">решение владельца</span> какие из трёх делаем и в каком порядке.',
    ),
)

FILES = {"Main.dc.html": CMP, "N1.dc.html": N1, "N2.dc.html": N2, "N3.dc.html": N3}
for name, html in FILES.items():
    (HERE / name).write_text(html, encoding="utf-8")

canvas = {
    "artboards": [
        {"file": "Main.dc.html", "x": 0, "y": 0, "w": 800, "h": 900, "title": "Сводка форм"},
        {"file": "N1.dc.html", "x": 900, "y": 0, "w": 800, "h": 720, "title": "N1 · Regal"},
        {"file": "N2.dc.html", "x": 1800, "y": 0, "w": 800, "h": 860, "title": "N2 · Lookbook"},
        {"file": "N3.dc.html", "x": 2700, "y": 0, "w": 800, "h": 700, "title": "N3 · Deal-Kachel"},
    ],
    "launch": {"view": "canvas"},
}
(HERE / "canvas.json").write_text(
    json.dumps(canvas, ensure_ascii=False, indent=1), encoding="utf-8"
)
print("готово:", ", ".join(FILES))
