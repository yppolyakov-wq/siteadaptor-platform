"""Канвас «Панель Студии» — дизайн области настроек (STU-18, 2026-09-10).

Запрос владельца: «проверь панель настроек, вывод информации тут ужасен, сделай
дизайн этой области и на согласование разведай, какие блоки и настройки в студии
должны быть на каждой странице» + три оси плана LAY + «настройки шрифтов и тд»
+ «всё должно быть согласовано с дизайнами сайтов и палитр».

Страница «Сегодня» нарисована ПО ЗАМЕРУ на живом стенде (демо aktionsmarkt,
Chromium 1440×900, панель 380 px, локаль кабинета — русская): высоты строк,
обрезанные подписи и перелив 30 px взяты из `scratchpad/measure.py|ru.py`,
а не по памяти. Разбор — `docs/stu18-panel-ia-plan-2026-09-10.md`.

Визуальный словарь — кабинет после редизайна B: холст #F2F4F7, карточки
rounded-2xl, индиго #4f46e5, системный шрифт. Значения панели сверены с
`templates/tenant/site_home.html` (ширина 380 px, группы `.bld-grp`
radius .6rem, сводка 11px #9ca3af).

Правки — ЗДЕСЬ, потом `python _generate.py` и пере-сид канваса.
"""

import json
from pathlib import Path
from string import Template

HERE = Path(__file__).parent

IND = "#4f46e5"  # индиго кабинета
IND_BG = "#eef2ff"
IND_TX = "#3730a3"
LINE = "#e5e7eb"
G400, G500, G700, G900 = "#9ca3af", "#6b7280", "#374151", "#111827"

CSS = Template("""
<style>
  body { margin:0; font-family: ui-sans-serif, system-ui, "Segoe UI", sans-serif;
         color:#1f2937; background:#f2f4f7; -webkit-font-smoothing:antialiased; }
  .bd { padding:20px; box-sizing:border-box; }
  .hd { margin-bottom:14px; }
  .hd .k { font-size:10px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; color:${IND}; }
  .hd h2 { margin:3px 0 0; font-size:17px; color:${G900}; letter-spacing:-.01em; }
  .hd p { margin:4px 0 0; font-size:11.5px; color:${G500}; line-height:1.5; max-width:62ch; }

  /* ── панель ── */
  .pane { width:380px; background:#fff; border:1px solid ${LINE}; border-radius:14px;
          box-sizing:border-box; overflow:hidden; box-shadow:0 1px 2px rgba(16,24,40,.05); }
  .pane-hd { display:flex; align-items:center; gap:8px; padding:10px 14px;
             border-bottom:1px solid #f1f2f4; }
  .pane-hd .t { font-size:13px; font-weight:700; color:${G700}; }
  .pane-hd .sp { flex:1; }
  .pane-hd .x { color:${G400}; font-size:13px; }
  .pane-hd .lang { border:1px solid #d1d5db; border-radius:7px; padding:1px 6px;
                   font-size:10.5px; color:${G500}; }
  .pane-bd { padding:12px; }

  /* ── СЕГОДНЯ: карточка-фиксет как сейчас ── */
  .fs { border:1px solid ${LINE}; border-radius:16px; padding:14px; background:#fff; margin-bottom:12px; }
  .fs > .lg { font-size:14px; font-weight:700; color:${G900}; margin-bottom:10px; }
  .old-lbl { font-size:13px; font-weight:600; color:${G900}; margin:0 0 6px; }
  .old-sub { font-size:11px; color:${G500}; margin:0 0 6px; }
  .old-sel { border:1px solid #d1d5db; border-radius:8px; padding:6px 8px; font-size:12.5px;
             color:${G500}; background:#fff; display:flex; justify-content:space-between; }
  .clip { display:block; width:64px; font-size:10px; line-height:1.2; color:${G500};
          height:24px; overflow:hidden; margin-top:4px; }
  .tiles-flex { display:flex; flex-wrap:wrap; gap:8px; }
  .tile { border:1px solid ${LINE}; border-radius:8px; padding:6px; background:#fff; }
  .tile.on { border-color:${IND}; box-shadow:0 0 0 2px #c7d2fe; }
  .thumb { width:56px; height:40px; border-radius:4px; background:#f3f4f6;
           box-shadow:inset 0 0 0 1px ${LINE}; display:block; }
  .ax2 { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:8px; }
  .ax2 .f { font-size:11px; color:${G500}; }
  .ax2 .c { margin-top:2px; border:1px solid #d1d5db; border-radius:5px; padding:4px 6px;
            font-size:11px; color:${G500}; background:#fff; }
  .ax2 .ph { color:#b6bcc6; }

  /* ── ПРЕДЛОЖЕНИЕ: группа оси ── */
  .grp { border:1px solid ${LINE}; border-radius:10px; background:#fff; margin-bottom:8px; }
  .grp-hd { display:flex; align-items:center; gap:6px; padding:8px 10px; }
  .grp-hd .ch { color:${G400}; font-size:10px; width:9px; }
  .grp-hd .ax { font-size:9px; font-weight:800; letter-spacing:.07em; color:${IND};
                border:1px solid #dfe3ff; background:${IND_BG}; border-radius:4px; padding:1px 4px; }
  .grp-hd .nm { font-size:12.5px; font-weight:700; color:${G900}; }
  .grp-hd .val { margin-left:auto; font-size:11px; color:${G400}; max-width:54%;
                 overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .grp-bd { padding:2px 10px 10px; border-top:1px solid #f4f5f7; }

  /* строка настройки — ОДИН шаблон */
  .row { margin-top:10px; }
  .row:first-child { margin-top:8px; }
  .row .lb { display:block; font-size:11.5px; font-weight:600; color:${G700}; margin-bottom:4px; }
  .row .hint { display:block; font-size:10.5px; color:${G400}; margin:-2px 0 4px; line-height:1.35; }
  .ctrl { width:100%; box-sizing:border-box; height:32px; border:1px solid #d1d5db;
          border-radius:8px; padding:0 9px; font-size:12.5px; color:${G900}; background:#fff;
          display:flex; align-items:center; }
  .ctrl .cv { margin-left:auto; color:${G400}; font-size:11px; }
  .two { display:grid; grid-template-columns:1fr 1fr; gap:8px; }

  /* сегмент «Сетка | Слайдер» */
  .seg { display:flex; border:1px solid #d1d5db; border-radius:8px; overflow:hidden; height:32px; }
  .seg span { flex:1; display:flex; align-items:center; justify-content:center;
              font-size:12px; color:${G500}; }
  .seg span.on { background:${IND_BG}; color:${IND_TX}; font-weight:700; }

  /* плитки — GRID, подпись переносится */
  .tiles { display:grid; grid-template-columns:repeat(auto-fill, minmax(96px,1fr)); gap:8px; }
  .tl { border:1px solid ${LINE}; border-radius:9px; padding:6px; background:#fff; }
  .tl.on { border-color:${IND}; box-shadow:0 0 0 2px #c7d2fe; }
  .tl.off { opacity:.45; }
  .tl .th { width:100%; height:46px; border-radius:5px; background:#f3f4f6;
            box-shadow:inset 0 0 0 1px ${LINE}; display:block; }
  .tl .cap { display:block; margin-top:5px; font-size:10.5px; line-height:1.25; color:${G500};
             overflow-wrap:break-word; }
  .tl.on .cap { color:${IND_TX}; font-weight:600; }

  .scope { display:flex; gap:4px; }
  .scope span { border:1px solid #d1d5db; border-radius:999px; padding:1px 8px;
                font-size:10.5px; color:${G500}; }
  .scope span.on { border-color:${IND}; background:${IND_BG}; color:${IND_TX}; font-weight:600; }

  .note { margin-top:8px; border:1px solid #e8eaee; background:#fafbfc; border-radius:8px;
          padding:8px 9px; font-size:10.5px; color:${G500}; line-height:1.45; }
  .note b { color:${G700}; }
  .note a { color:${IND}; }

  .foot { margin-top:10px; border-top:1px solid #f1f2f4; padding-top:10px;
          display:flex; align-items:center; gap:8px; }
  .foot .sw { width:14px; height:14px; border-radius:999px; background:#16a34a;
              box-shadow:inset 0 0 0 1px rgba(0,0,0,.08); }
  .foot .tx { font-size:11.5px; color:${G700}; }
  .foot .tx small { display:block; color:${G400}; font-size:10.5px; }
  .foot .go { margin-left:auto; font-size:11px; color:${IND}; }

  /* выноски */
  .cal { display:flex; gap:8px; margin-bottom:9px; }
  .cal .n { flex:0 0 auto; width:19px; height:19px; border-radius:999px; background:#fee2e2;
            color:#b91c1c; font-size:10.5px; font-weight:800; display:flex;
            align-items:center; justify-content:center; }
  .cal .n.ok { background:#dcfce7; color:#15803d; }
  .cal .tx { font-size:11.5px; color:${G700}; line-height:1.45; }
  .cal .tx b { color:${G900}; }
  .cal .tx code { font-size:10.5px; background:#f3f4f6; border-radius:3px; padding:0 3px;
                  color:${G500}; }
  .pin { position:absolute; width:19px; height:19px; border-radius:999px; background:#dc2626;
         color:#fff; font-size:10.5px; font-weight:800; display:flex; align-items:center;
         justify-content:center; box-shadow:0 1px 3px rgba(0,0,0,.28); }

  .mtx { border-collapse:collapse; width:100%; font-size:11px; }
  .mtx th { text-align:left; font-size:10px; font-weight:700; color:${G500};
            padding:5px 6px; border-bottom:1px solid ${LINE}; }
  .mtx td { padding:4px 6px; border-bottom:1px solid #f2f3f5; color:${G700}; }
  .mtx td.y { color:#15803d; font-weight:700; }
  .mtx td.n { color:${G400}; }
  .mtx td.w { color:#b45309; font-weight:700; }
  .mtx td.x { color:#b91c1c; font-weight:700; }
  .mtx tr.sec td { background:#f8f9fb; font-weight:700; color:${G900}; font-size:10.5px; }
  .lgnd { font-size:10.5px; color:${G500}; margin-top:8px; line-height:1.6; }

  .spec { display:flex; gap:14px; align-items:flex-start; margin-bottom:14px; }
  .spec .demo { flex:0 0 200px; }
  .spec .txt { font-size:11.5px; color:${G700}; line-height:1.5; }
  .spec .txt > b:first-child { color:${G900}; display:block; margin-bottom:2px; font-size:12px; }
  .spec .txt b { color:${G900}; }
  .spec .txt code { font-size:10.5px; background:#f3f4f6; border-radius:3px; padding:0 3px; color:${G500}; }
</style>
""").substitute(
    IND=IND,
    IND_BG=IND_BG,
    IND_TX=IND_TX,
    LINE=LINE,
    G400=G400,
    G500=G500,
    G700=G700,
    G900=G900,
)


def doc(inner: str) -> str:
    return (
        '<!doctype html>\n<html>\n<head>\n  <meta charset="utf-8">\n'
        '  <script src="./support.js"></script>\n</head>\n<body>\n<x-dc>\n<helmet>'
        + CSS
        + "</helmet>\n"
        + inner
        + "\n</x-dc>\n</body>\n</html>\n"
    )


def head(kicker: str, title: str, sub: str) -> str:
    return f'<div class="hd"><div class="k">{kicker}</div><h2>{title}</h2><p>{sub}</p></div>'


def cal(n: str, text: str, ok: bool = False) -> str:
    return f'<div class="cal"><div class="n{" ok" if ok else ""}">{n}</div><div class="tx">{text}</div></div>'


# ─────────────────────────────────────────────────────────────────────────────
# СЕГОДНЯ
# ─────────────────────────────────────────────────────────────────────────────


def _old_tile(cap: str, on: bool = False, clip: bool = False) -> str:
    cls = "tile on" if on else "tile"
    capcls = "clip" if clip else "clip"
    return (
        f'<div class="{cls}"><span class="thumb"></span><span class="{capcls}">{cap}</span></div>'
    )


def heute_aktionen() -> str:
    comp = "".join(
        _old_tile(c, on=(c == "С обложкой"), clip=True)
        for c in [
            "Стандарт (сетка)",
            "С обложкой",
            "Прайс-лист",
            "Полки (подкатегории лентами)",
            "Вкладки (подкатегории вкладками)",
            "Витрина",
            "Навигатор",
            "Журнал",
            "Компактно",
        ]
    )
    promo_forms = "".join(
        _old_tile(c, on=(c == "Цена сверху"), clip=True)
        for c in [
            "Стандартный",
            "Цена сверху",
            "Полочный ценник",
            "Лукбук",
            "Плитка предложения",
            "Купон",
            "Кольцо отсчёта",
        ]
    )
    grid = "".join(
        _old_tile(c, on=(c == "3 в строке"), clip=True)
        for c in [
            "Стандартный",
            "Список",
            "2 в строке",
            "3 в строке",
            "4 в строке",
            "5 в ряд",
            "6 в ряд",
            "Галерея",
        ]
    )
    panel = f"""
    <div class="pane">
      <div class="pane-hd"><span class="t">Эта страница: Акции</span><span class="sp"></span><span class="x">✕</span></div>
      <div class="pane-bd">
        <div class="old-sub">Акции</div>
        <div class="fs">
          <div class="lg">Шаблон страницы</div>
          <p class="old-lbl">Страница акций: шаблон</p>
          <div class="tiles-flex">{comp}</div>
          <p class="old-lbl" style="margin-top:14px">Страница акций: группировка</p>
          <div class="old-sel"><span>По группам</span><span>▾</span></div>
          <p class="old-lbl" style="margin-top:14px">Акции: сетка</p>
          <div class="tiles-flex">{grid}</div>
          <div class="ax2">
            <div><div class="f">Вывод</div><div class="c">Сетка ▾</div></div>
            <div><div class="f">Последний ряд</div><div class="c">Распределить ▾</div></div>
            <div><div class="f">Рядов</div><div class="c ph">все</div></div>
            <div><div class="f">На странице</div><div class="c ph">Стандартный</div></div>
          </div>
          <div class="ax2" style="grid-template-columns:1fr">
            <div><div class="f">Скорость (сек.)</div><div class="c ph">выкл</div></div>
          </div>
          <p class="old-lbl" style="margin-top:14px">Форма карточки акции</p>
          <div class="tiles-flex">{promo_forms}</div>
          <div class="scope" style="margin-top:10px"><span class="on">Для всех</span><span>Только здесь</span></div>
        </div>
      </div>
    </div>"""
    calls = (
        cal(
            "1",
            "<b>Заголовок карточки дублирует настройку.</b> «Шаблон страницы» → и сразу «Страница акций: шаблон». Рамка не несёт смысла.",
        )
        + cal(
            "2",
            "<b>Подписи обрезаны.</b> «Полки (подкатегори…», «Вкладки (подкатегор…» — у плитки жёсткая ширина подписи <code>w-16</code> = 64 px и <code>line-clamp-2</code>. По-немецки влезает, по-русски нет.",
        )
        + cal(
            "3",
            "<b>Два набора плиток одного вида означают разное.</b> Сверху — композиция страницы, снизу — пресет сетки. Мини-макеты нарисованы одинаково.",
        )
        + cal(
            "4",
            "<b>Одна ось разорвана надвое.</b> Плитки «Акции: сетка» и пять полей ниже — это ОДНА ось «сетка», но выглядят как два раздела: крупные плитки и мелкие серые поля в две колонки.",
        )
        + cal(
            "5",
            "<b>Значение по умолчанию выглядит выключенным.</b> «все», «Стандартный», «выкл» — это <code>placeholder</code> пустых числовых полей. Серый текст читается как «недоступно».",
        )
        + cal(
            "6",
            "<b>Замер:</b> 4 настройки = 973 px. Плитки композиции 289 px · сетка 296 px · форма карточки 332 px. Почти три экрана прокрутки.",
        )
    )
    return doc(
        f"""<div class="bd">
      {
            head(
                "Сегодня · замер на стенде",
                "Панель на /aktionen/ — как есть",
                "Демо <b>aktionsmarkt</b>, Chromium 1440×900, панель 380 px, кабинет по-русски. "
                "Высоты и обрезки — из браузерного замера, не по памяти.",
            )
        }
      <div style="display:flex; gap:26px; align-items:flex-start">
        <div style="flex:0 0 380px">{panel}</div>
        <div style="flex:1; padding-top:4px">{calls}</div>
      </div>
    </div>"""
    )


def heute_katalog() -> str:
    forms = "".join(
        _old_tile(c, on=(c == "Полочный ценник"), clip=True)
        for c in [
            "Стандартный",
            "Текст на фото",
            "Компактная строка",
            "Ценник",
            "Полочный ценник",
            "Лукбук",
            "Плитка предложения",
        ]
    )
    panel = f"""
    <div class="pane">
      <div class="pane-hd"><span class="t">Эта страница: Каталог</span><span class="sp"></span><span class="x">✕</span></div>
      <div class="pane-bd">
        <div class="old-sub">Каталог</div>
        <div class="fs">
          <div class="lg">Шаблон страницы</div>
          <p class="old-lbl">Форма карточки</p>
          <div class="tiles-flex">{forms}</div>
          <div class="scope" style="margin-top:10px"><span class="on">Для всех</span><span>Только здесь</span></div>
          <div style="margin-top:12px; display:flex; gap:8px; align-items:flex-start">
            <span style="width:14px;height:14px;border:1px solid #d1d5db;border-radius:4px;margin-top:1px"></span>
            <span style="font-size:12.5px;color:#374151;line-height:1.35">Маркировка в меню (диеты, аллергены)</span>
          </div>
        </div>
        <div class="fs">
          <div class="lg">Целевые страницы</div>
          <p style="font-size:11.5px;color:#9ca3af;line-height:1.45;margin:0 0 8px">
            Переключите предварительный просмотр на страницу и щёлкните по сетке, чтобы отредактировать макет здесь.</p>
          <div style="background:#eef2ff;border-radius:8px;padding:8px 9px;font-size:11.5px;color:#3730a3;line-height:1.4">
            Отображаются только блоки для текущей страницы.</div>
          <p class="old-lbl" style="margin-top:12px">Каталог: сетка</p>
          <div class="tiles-flex">{"".join(_old_tile(c, on=(c == "3 в строке"), clip=True) for c in ["Список", "2 в строке", "3 в строке", "4 в строке", "6 в ряд"])}</div>
          <div style="margin-top:10px; display:flex; align-items:center; gap:6px">
            <span style="font-size:11px;color:#6b7280;flex:1">Сортировка</span>
            <span style="border:1px solid #d1d5db;border-radius:5px;padding:2px 6px;font-size:11px;color:#6b7280">Самые новые ▾</span>
          </div>
          <div style="margin-top:8px; display:flex; align-items:center; gap:6px">
            <span style="width:12px;height:12px;border:1px solid #d1d5db;border-radius:3px"></span>
            <span style="font-size:11px;color:#6b7280">Показать фильтры</span>
          </div>
          <p class="old-lbl" style="margin-top:14px">Шаблон страницы каталога</p>
          <div class="tiles-flex">{"".join(_old_tile(c, on=(c == "Полки"), clip=True) for c in ["Стандарт (сетка)", "С обложкой", "Полки", "Вкладки", "Витрина", "Навигатор"])}</div>
        </div>
      </div>
    </div>"""
    calls = (
        cal(
            "1",
            "<b>Заголовок карточки обманывает.</b> Карточка называется «Шаблон страницы», а внутри — <b>форма карточки</b>. Настоящий шаблон страницы (<code>catalog_page_style</code>) лежит НИЖЕ, во второй карточке «Целевые страницы».",
        )
        + cal(
            "2",
            "<b>Три оси разложены по двум карточкам с чужими именами.</b> Композиция и сетка — в «Целевых страницах», форма карточки — в «Шаблоне страницы». Ни одна карточка не называет ось.",
        )
        + cal(
            "3",
            "<b>Ещё один набор одинаковых плиток.</b> Владелец только что видел такие же выше — там они значили форму карточки, здесь плотность сетки.",
        )
        + cal(
            "4",
            "<b>Перелив 30 px по горизонтали</b> — в русской локали; в немецкой 0. Отсюда полоса прокрутки внизу панели.",
        )
        + cal(
            "5",
            "<b>Ритм рваный.</b> Замер строк: форма карточки 319 px · сетка 405 px · шаблон 302 px — и между ними «Сортировка» 24 px и «Показать фильтры» 16 px. Самые частые настройки выглядят как случайные строчки.",
        )
        + cal(
            "6",
            "<b>Пять шаблонов строки в одной панели:</b> подпись сверху + широкий контрол · флекс «подпись—селект» · мелкая инлайн-подпись · чекбокс · плитки. Три разных размера поля.",
        )
    )
    return doc(
        f"""<div class="bd">
      {
            head(
                "Сегодня · замер на стенде",
                "Панель на /sortiment/ — как есть",
                "Тот же прогон. Здесь видно главное: <b>заголовки карточек не описывают содержимое</b>, "
                "и три оси разложены по двум карточкам с чужими именами.",
            )
        }
      <div style="display:flex; gap:26px; align-items:flex-start">
        <div style="flex:0 0 380px">{panel}</div>
        <div style="flex:1; padding-top:4px">{calls}</div>
      </div>
    </div>"""
    )


# ─────────────────────────────────────────────────────────────────────────────
# ПРЕДЛОЖЕНИЕ
# ─────────────────────────────────────────────────────────────────────────────


def grp(ax: str, name: str, val: str, body: str = "", open_: bool = False, scope: str = "") -> str:
    ch = "▾" if open_ else "▸"
    sc = ""
    if scope:
        sc = f'<div class="row"><div class="scope"><span class="{"on" if scope == "site" else ""}">Для всех</span><span class="{"on" if scope == "own" else ""}">Только здесь</span></div></div>'
    inner = f'<div class="grp-bd">{body}{sc}</div>' if open_ else ""
    return (
        f'<div class="grp"><div class="grp-hd"><span class="ch">{ch}</span>'
        f'<span class="ax">{ax}</span><span class="nm">{name}</span>'
        f'<span class="val">{val}</span></div>{inner}</div>'
    )


def tiles(items, cols_hint="") -> str:
    out = []
    for cap, state in items:
        cls = "tl on" if state == "on" else ("tl off" if state == "off" else "tl")
        out.append(
            f'<div class="{cls}"><span class="th"></span><span class="cap">{cap}</span></div>'
        )
    return f'<div class="tiles">{"".join(out)}</div>'


def row(label, control, hint="") -> str:
    h = f'<span class="hint">{hint}</span>' if hint else ""
    return f'<div class="row"><span class="lb">{label}</span>{h}{control}</div>'


def sel(value, muted=False) -> str:
    c = ' style="color:#9ca3af"' if muted else ""
    return f'<div class="ctrl"{c}><span>{value}</span><span class="cv">▾</span></div>'


FOOT = (
    '<div class="foot"><span class="sw"></span>'
    '<span class="tx">Оформление сайта<small>Look «Prospekt» · Barlow Condensed</small></span>'
    '<span class="go">Открыть →</span></div>'
)


def pane(title, body, sub="") -> str:
    s = f'<div class="old-sub" style="margin-bottom:8px">{sub}</div>' if sub else ""
    return f"""<div class="pane">
      <div class="pane-hd"><span class="t">{title}</span><span class="sp"></span>
        <span class="lang">🌐 RU</span><span class="x">✕</span></div>
      <div class="pane-bd">{s}{body}{FOOT}</div></div>"""


def main_board() -> str:
    grid_body = (
        row(
            "Тип вывода", '<div class="seg"><span class="on">Сетка</span><span>Слайдер</span></div>'
        )
        + row(
            "Плотность",
            tiles(
                [
                    ("Список", ""),
                    ("2 в строке", ""),
                    ("3 в строке", "on"),
                    ("4 в строке", ""),
                    ("6 в ряд", ""),
                    ("Галерея", ""),
                ]
            ),
        )
        + f'<div class="row two"><div><span class="lb">Рядов</span>{sel("все")}</div>'
        f'<div><span class="lb">На странице</span>{sel("Стандартный")}</div></div>'
        + row("Последний ряд", sel("Распределить"))
    )
    body = (
        grp("A", "Шаблон страницы", "С обложкой", open_=False)
        + grp("B", "Вывод", "Сетка · 3 в строке", body=grid_body, open_=True)
        + grp("C", "Карточка", "Полочный ценник", open_=False)
        + grp("—", "Содержание страницы", "Группировка", open_=False)
    )
    return doc(
        f"""<div class="bd">
      {
            head(
                "Предложение · основной макет",
                "Панель: страница со списком",
                "Одна структура на всех 30 типах: <b>A Композиция · B Сетка · C Карточка · Содержание</b>. "
                "Группы свёрнуты, значение — в заголовке; открыта одна. Свёрнутая панель — "
                "четыре строки; сегодня те же четыре настройки развёрнуты всегда и дают 973 px.",
            )
        }
      {pane("Эта страница: Акции", body, "")}
      <div style="width:380px; margin-top:14px">
        {
            cal(
                "✓",
                "<b>Ось названа.</b> Бейдж A/B/C и имя группы говорят, что именно настраивается — вместо «Шаблон страницы», под которым лежит форма карточки.",
                True,
            )
        }
        {
            cal(
                "✓",
                "<b>Сетка снова одна.</b> Плотность и параметры — в одной группе, одним размером контролов.",
                True,
            )
        }
        {
            cal(
                "✓",
                "<b>Значение видно свёрнутым.</b> «Сетка · 3 в строке» в заголовке; листать, чтобы вспомнить выбор, не нужно.",
                True,
            )
        }
        {
            cal(
                "✓",
                "<b>«все» и «Стандартный» — это значения,</b> а не серые плейсхолдеры пустого поля: обычный селект с явной опцией.",
                True,
            )
        }
      </div>
    </div>"""
    )


def kategorie() -> str:
    comp = tiles(
        [
            ("Стандарт (сетка)", ""),
            ("С обложкой", "on"),
            ("Сначала сеты и меню", "off"),
            ("Полки (подкатегории лентами)", "off"),
            ("Вкладки (подкатегории вкладками)", "off"),
            ("Витрина", ""),
            ("Навигатор", ""),
            ("Журнал", ""),
            ("Мозаика", ""),
            ("Компактно", ""),
        ]
    )
    body = (
        grp(
            "A",
            "Шаблон страницы",
            "С обложкой · здесь",
            open_=True,
            scope="own",
            body=comp
            + '<div class="note"><b>Полки</b>, <b>Вкладки</b> и <b>Сначала сеты и меню</b> '
            "недоступны: у этой категории нет подкатегорий и наборов. "
            "Гейт уже описан в реестре (<code>available_for</code>) — сегодня он не подключён (Д-1).</div>",
        )
        + grp("B", "Вывод", "Сетка · 4 в строке", open_=False)
        + grp("C", "Карточка", "Лукбук", open_=False)
        + grp("—", "Содержание страницы", "3 настройки", open_=False)
    )
    return doc(
        f"""<div class="bd">
      {
            head(
                "Предложение",
                "Панель: категория — охват и гейт",
                "Охват виден в <b>заголовке группы</b> («· здесь»), а переключатель остаётся в своей строке — "
                "этого требует существующий замок. Недоступные композиции погашены с причиной — "
                "вместо молчаливого «выбрал и ничего не изменилось».",
            )
        }
      {pane("Эта страница: Категория «Напитки»", body)}
    </div>"""
    )


def detail() -> str:
    body = (
        grp(
            "A",
            "Шаблон страницы",
            "Вкладки",
            open_=True,
            body=row(
                "Раскладка страницы",
                sel("Вкладки"),
                "Как разложены секции детали: подряд · вкладками · во всю ширину.",
            ),
        )
        + grp(
            "B",
            "Вывод",
            "Похожие: 4 в строке",
            open_=True,
            body=row(
                "Похожие товары",
                sel("4 в строке"),
                "У детали одна поверхность вывода — полоса «Похожие». "
                "Остальные параметры сетки для неё сегодня не хранятся — в карте это «частично».",
            ),
        )
        + grp("C", "Карточка", "Полочный ценник · этот товар", open_=False)
        + grp("—", "Содержание страницы", "Секции", open_=False)
    )
    return doc(
        f"""<div class="bd">
      {
            head(
                "Предложение",
                "Панель: страница товара",
                "На детали три оси тоже есть, но означают другое: композиция — раскладка секций, "
                "сетка — единственная полоса «Похожие». Структура и порядок групп те же.",
            )
        }
      {pane("Эта страница: Товар", body)}
    </div>"""
    )


def textseite() -> str:
    body = (
        grp(
            "—",
            "Содержание страницы",
            "Обычная ширина",
            open_=True,
            body=row("Ширина текста", sel("Обычная")),
        )
        + '<div class="note" style="margin-top:2px"><b>Здесь нет сетки и карточек.</b> '
        "Страница состоит из текста и блоков — их правят прямо на канве. "
        "Шаблона страницы для текстовых страниц не существует.</div>"
    )
    return doc(
        f"""<div class="bd">
      {
            head(
                "Предложение",
                "Панель: текстовая страница",
                "Группа без применимых настроек <b>не рисуется</b> — вместо трёх пустых рамок "
                "одна строка и честное объяснение. Прецедент уже есть: подсказка для «Команда» и «Галерея».",
            )
        }
      {pane("Эта страница: О нас", body)}
    </div>"""
    )


def startseite() -> str:
    body = grp("A", "Первый экран", "Сплит с фото", open_=False) + grp(
        "—",
        "Блоки главной",
        "Состав и порядок",
        open_=True,
        body='<div class="note" style="margin-top:6px">У каждого блока главной '
        "<b>своя сетка и своя форма карточки</b> — они правятся в самом блоке "
        "на канве. Поэтому здесь групп B и C нет: иначе одна настройка спорила бы "
        "<b>с каждым блоком</b>.</div>",
    )
    return doc(
        f"""<div class="bd">
      {
            head(
                "Предложение",
                "Панель: главная",
                "Единственный тип, где поверхностей много (по одной на блок). "
                "Оси живут в блоке, панель страницы отвечает за первый экран и состав.",
            )
        }
      {pane("Эта страница: Главная", body)}
    </div>"""
    )


def telefon() -> str:
    body = (
        grp("A", "Шаблон страницы", "С обложкой", open_=False)
        + grp(
            "B",
            "Вывод",
            "Сетка · 3 в строке",
            open_=True,
            body=row(
                "Тип вывода",
                '<div class="seg"><span class="on">Сетка</span><span>Слайдер</span></div>',
            )
            + row("Плотность", tiles([("Список", ""), ("2 в строке", ""), ("3 в строке", "on")])),
        )
        + grp("C", "Карточка", "Полочный ценник", open_=False)
        + grp("—", "Содержание страницы", "1 настройка", open_=False)
    )
    sheet = f"""<div style="width:390px; height:600px; background:#e9edf2; border-radius:22px;
        border:1px solid {LINE}; overflow:hidden; position:relative; box-sizing:border-box">
      <div style="position:absolute;inset:0;padding:10px">
        <div style="background:#fff;border-radius:10px;height:100%;box-shadow:inset 0 0 0 1px {LINE};
             display:flex;align-items:center;justify-content:center;color:{G400};font-size:12px">канва</div>
      </div>
      <div style="position:absolute;left:0;right:0;bottom:0;background:#fff;border-radius:16px 16px 0 0;
           box-shadow:0 -8px 24px rgba(16,24,40,.12);padding:8px 12px 14px;box-sizing:border-box;max-height:78%">
        <div style="width:34px;height:4px;border-radius:999px;background:#dfe3e8;margin:0 auto 8px"></div>
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
          <span style="font-size:13px;font-weight:700;color:{G700}">Эта страница: Акции</span>
          <span style="flex:1"></span><span style="font-size:10.5px;color:{G500};border:1px solid #d1d5db;
            border-radius:7px;padding:1px 6px">🌐 RU</span><span style="color:{G400}">✕</span></div>
        {body}
      </div></div>"""
    return doc(
        f"""<div class="bd">
      {
            head(
                "Предложение",
                "Телефон: тот же порядок групп",
                "Панель становится нижним листом (механика уже есть). Свёрнутые группы со значением "
                "в заголовке здесь важнее всего: на 390 px три простыни плиток были бы нечитаемы.",
            )
        }
      {sheet}
    </div>"""
    )


def gestaltung() -> str:
    left = f"""<div class="pane">
      <div class="pane-hd"><span class="t">Эта страница: Акции</span><span class="sp"></span>
        <span class="lang">🌐 RU</span><span class="x">✕</span></div>
      <div class="pane-bd">
        {grp("A", "Шаблон страницы", "С обложкой")}
        {grp("B", "Вывод", "Сетка · 3 в строке")}
        {grp("C", "Карточка", "Полочный ценник")}
        {grp("—", "Содержание страницы", "1 настройка")}
        <div class="foot"><span class="sw"></span>
          <span class="tx">Оформление сайта<small>Look «Prospekt» · Barlow Condensed · зелёный</small></span>
          <span class="go">Открыть →</span></div>
      </div></div>"""
    right = f"""<div style="flex:1">
      {cal("1", "<b>Рекомендую оставить шрифт, цвет, тему и скругления на «Оформлении сайта».</b> Это глобальные настройки; смешивать их с постраничными — значит вернуть кашу. Их вынесли туда осознанно (STU-12g, решение владельца 1B) и закрепили замком. <b>Это рекомендация, а не решённое</b> — см. Р-3 ниже.")}
      {cal("2", "<b>Предлагаю добавить:</b> живая сводка внизу панели — имя Look, шрифт, кружок акцента — и переход. Владелец видит, чем оформлен сайт, не уходя со страницы. На макетах панели она уже нарисована.")}
      {cal("3", "<b>Плитки рисуются палитрой сайта.</b> Сегодня мини-макеты жёстко серо-янтарно-красные (<code>bg-amber-200</code>, <code>bg-red-500</code>): мини-макет листовки красный, даже если акцент сайта зелёный. Предлагаю рисовать их переменными витрины и подписывать шрифтом сайта.")}
      {cal("4", "<b>Развилка Р-4:</b> <b>сборки</b> («Startpaket») на экране оформления одним кликом переписывают композицию, сетку и форму карточки — то есть настройки, которые владелец только что выставил в панели. Предупреждать? Или запретить пакету трогать то, что тронуто руками (правило LAY-5)?")}
      {cal("5", "<b>Развилка Р-3:</b> если шрифт нужен именно в Студии — вернём ввод в группу оформления. Рекомендую не возвращать: сводка + переход дают то же, не ломая границу «страница ↔ сайт».")}
    </div>"""
    return doc(
        f"""<div class="bd">
      {
            head(
                "Предложение · согласование с палитрой",
                "Где живут шрифты и палитра",
                "Ответ на «настройки шрифтов и тд» и «всё должно быть согласовано с дизайнами сайтов и палитр».",
            )
        }
      <div style="display:flex; gap:26px; align-items:flex-start">{left}{right}</div>
    </div>"""
    )


def komponenten() -> str:
    demo_row = f'<div style="width:200px">{row("Последний ряд", sel("Распределить"))}</div>'
    demo_grp = f'<div style="width:200px">{grp("B", "Вывод", "Сетка · 3", open_=False)}</div>'
    demo_tiles = f'<div style="width:200px">{tiles([("Полки (подкатегории лентами)", "on"), ("Витрина", ""), ("Журнал", "")])}</div>'
    demo_scope = (
        '<div style="width:200px"><div class="scope"><span class="on">Для всех</span>'
        "<span>Только здесь</span></div></div>"
    )
    demo_seg = '<div style="width:200px"><div class="seg"><span class="on">Сетка</span><span>Слайдер</span></div></div>'
    items = [
        (
            demo_grp,
            "Группа оси",
            "Свёрнута по умолчанию, в заголовке — <b>текущее значение</b>. Бейдж <code>A/B/C</code> называет ось. "
            "Компонент уже есть в панели — <code>.bld-grp</code>, им свёрстаны настройки блока; "
            "распространяем на настройки страницы, чтобы визуальный язык стал один.",
        ),
        (
            demo_row,
            "Строка настройки",
            "Подпись 11.5 px / 600 над контролом, контрол во всю ширину, высота 32 px, радиус 8 px. "
            "<b>Один шаблон вместо пяти.</b> Никаких инлайн-подписей и трёх размеров поля.",
        ),
        (
            demo_tiles,
            "Плитки",
            "<code>grid</code> с <code>minmax(88px,1fr)</code> вместо <code>flex-wrap</code> — ряды выравниваются. "
            "Подпись переносится по словам (<code>overflow-wrap:break-word</code>) вместо обрезки по "
            "<code>w-16</code>: это и чинит перелив 30 px в русской локали.",
        ),
        (
            demo_seg,
            "Тип вывода",
            "Сегмент «Сетка | Слайдер» вместо селекта: два значения, между которыми переключаются часто. "
            "«Скорость» показывается <b>только</b> при слайдере — сегодня она всегда на месте и пишет «выкл».",
        ),
        (
            demo_scope,
            "Охват",
            "В заголовке группы значение говорит, чей выбор действует («С обложкой · здесь»); "
            "сам переключатель остаётся в своей строке — этого требует существующий замок. "
            "Точка на «Только здесь» = у объекта своё значение.",
        ),
    ]
    specs = "".join(
        f'<div class="spec"><div class="demo">{d}</div><div class="txt"><b>{t}</b>{x}</div></div>'
        for d, t, x in items
    )
    return doc(
        f"""<div class="bd">
      {
            head(
                "Предложение",
                "Компоненты панели",
                "Пять компонентов закрывают все 40 строк реестра. Цвета и ширина — как в кабинете: "
                "индиго #4f46e5, панель 380 px; скругления карточек панели — 10-14 px.",
            )
        }
      {specs}
      <div class="note" style="max-width:640px"><b>Что НЕ меняется:</b> имена полей, коды
      <code>data-stu-setting</code> и <code>data-stu-page</code>, механика скрытия (только CSS, поля остаются
      в форме — инвариант W0). Поэтому замок «реестр ↔ панель» продолжает держать соответствие,
      а сохранение и живой черновик не трогаются. Миграций нет.</div>
    </div>"""
    )


def matrix() -> str:
    rows = [
        ("sec", "Списки товаров и акций", "", "", "", ""),
        ("", "Каталог", "y", "y", "y", "сорт · фильтры · цены · маркировка"),
        ("", "Категория", "y", "y", "y", "сорт · фильтры · подкатегории · цены · маркировка"),
        ("", "Акции", "y", "y", "y", "группировка"),
        ("", "Группа акций", "y", "y", "y", "—"),
        ("sec", "Списки без шаблона страницы", "", "", "", ""),
        ("", "Услуги /termin/", "x", "y", "y", "сортировка"),
        ("", "Номера /unterkunft/", "x", "y", "y", "сортировка"),
        ("", "События", "x", "y", "y", "сортировка"),
        ("", "Туры", "x", "y", "w", "ширина текста"),
        ("", "Наборы /kombi/", "x", "y", "w", "ширина текста"),
        ("", "Лукбук", "x", "y", "y", "ширина текста"),
        ("", "Мерклист", "x", "y", "y", "ширина текста"),
        ("", "Блог", "x", "y", "n", "ширина текста"),
        ("", "Отзывы", "x", "y", "n", "ширина текста"),
        ("sec", "Детальные страницы", "", "", "", ""),
        ("", "Товар", "y", "w", "y", "секции"),
        ("", "Услуга · Номер", "y", "n", "y", "секции"),
        ("", "Событие", "y", "n", "n", "секции"),
        ("", "Акция", "y", "n", "y", "—"),
        ("sec", "Прочее", "", "", "", ""),
        ("", "Главная", "y", "b", "b", "состав блоков"),
        ("", "Finder", "n", "x", "y", "ширина текста"),
        ("", "Корзина", "n", "n", "y", "«Passt dazu»"),
        ("", "Команда · Галерея", "n", "b", "n", "текст страницы"),
        ("", "Текстовые (7 типов)", "n", "n", "n", "ширина текста"),
    ]
    body = ""
    for kind, name, a, b, c, d in rows:
        if kind == "sec":
            body += f'<tr class="sec"><td colspan="5">{name}</td></tr>'
            continue

        def cell(v):
            return {
                "y": '<td class="y">✓</td>',
                "n": '<td class="n">—</td>',
                "w": '<td class="w">частично</td>',
                "x": '<td class="x">НЕТ</td>',
                "b": '<td style="color:#6b7280">в блоке</td>',
            }[v]

        body += f"<tr><td>{name}</td>{cell(a)}{cell(b)}{cell(c)}<td>{d}</td></tr>"
    return doc(
        f"""<div class="bd">
      {
            head(
                "Разведка · на согласование",
                "Какая ось действует на каком типе страницы",
                "30 типов реестра, сведённые к строкам. <b>Красное «НЕТ» — это работа</b>, "
                "а не пропуск в панели: реестр композиций объявляет пять поверхностей и растёт только "
                "тогда, когда рендер страницы действительно читает выбор.",
            )
        }
      <table class="mtx">
        <tr><th style="width:30%">Тип страницы</th><th>A Композиция<br><span style="font-weight:400">(шаблон страницы)</span></th><th>B Сетка</th>
            <th>C Карточка</th><th style="width:32%">Содержание</th></tr>
        {body}
      </table>
      <div class="lgnd">
        <b style="color:#15803d">✓</b> — ось есть и работает &nbsp;·&nbsp;
        <b style="color:#b45309">частично</b> — предлагается, исполняется не полностью &nbsp;·&nbsp;
        <b style="color:#9ca3af">—</b> — оси нет и она честно не предлагается &nbsp;·&nbsp;
        <b style="color:#6b7280">в блоке</b> — ось есть, но живёт в блоке главной, не в панели страницы &nbsp;·&nbsp;
        <b style="color:#b91c1c">НЕТ</b> — страница ось читать могла бы, но реализации нет.<br>
        <b>Итог для решения Р-2:</b> «шаблон страницы» отсутствует на <b>девяти листингах</b>
        (услуги, номера, события, туры, наборы, лукбук, мерклист, блог, отзывы).
        Чтобы «Полки/Витрина/Журнал» появились на /termin/, их нужно там реализовать.
      </div>
    </div>"""
    )


ARTBOARDS = {
    "HeuteAktionen": (heute_aktionen, 980, 1440, "Сегодня: /aktionen/"),
    "HeuteKatalog": (heute_katalog, 980, 1330, "Сегодня: /sortiment/"),
    "Main": (main_board, 460, 1150, "Панель: список"),
    "Kategorie": (kategorie, 460, 1010, "Панель: категория"),
    "Detail": (detail, 460, 670, "Панель: товар"),
    "TextSeite": (textseite, 460, 480, "Панель: текстовая"),
    "Startseite": (startseite, 460, 460, "Панель: главная"),
    "Telefon": (telefon, 460, 790, "Телефон"),
    "Gestaltung": (gestaltung, 1020, 520, "Шрифты и палитра"),
    "Komponenten": (komponenten, 780, 800, "Компоненты"),
    "Matrix": (matrix, 900, 880, "Матрица осей"),
}

PAGE_OF = {
    "HeuteAktionen": "heute",
    "HeuteKatalog": "heute",
    "Main": "vorschlag",
    "Kategorie": "vorschlag",
    "Detail": "vorschlag",
    "TextSeite": "vorschlag",
    "Startseite": "vorschlag",
    "Telefon": "vorschlag",
    "Gestaltung": "vorschlag",
    "Komponenten": "system",
    "Matrix": "system",
}

LAYOUT = {
    "HeuteAktionen": (0, 0),
    "HeuteKatalog": (1080, 0),
    "Main": (0, 0),
    "Kategorie": (560, 0),
    "Detail": (1120, 0),
    "TextSeite": (1680, 0),
    "Startseite": (0, 1290),
    "Telefon": (560, 1290),
    "Gestaltung": (1120, 1290),
    "Komponenten": (0, 0),
    "Matrix": (880, 0),
}

NOTES = [
    {
        "id": "note-heute",
        "x": 0,
        "y": -150,
        "w": 700,
        "page": "heute",
        "text": "Замер на живом стенде (демо aktionsmarkt, панель 380 px, кабинет по-русски).\n"
        "Высоты строк и обрезанные подписи — из браузера, не по памяти.\n"
        "Разбор — docs/stu18-panel-ia-plan-2026-09-10.md §1-2.",
    },
    {
        "id": "note-vorschlag",
        "x": 0,
        "y": -170,
        "w": 760,
        "page": "vorschlag",
        "text": "Одна структура на всех 30 типах: A Композиция · B Сетка · C Карточка · Содержание.\n"
        "Группа без применимых настроек не рисуется. Где оси нет — строка-объяснение,\n"
        "а не контрол-обманка. Ключей хранения и миграций нет: строки перекладываются.",
    },
    {
        "id": "note-system",
        "x": 0,
        "y": -150,
        "w": 700,
        "page": "system",
        "text": "Слева — пять компонентов, которыми верстаются все 40 строк реестра.\n"
        "Справа — карта «ось × тип страницы» на согласование (решение Р-2).",
    },
]


def main() -> None:
    boards = []
    for name, (fn, w, h, title) in ARTBOARDS.items():
        (HERE / f"{name}.dc.html").write_text(fn(), encoding="utf-8")
        x, y = LAYOUT[name]
        boards.append(
            {
                "file": f"{name}.dc.html",
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "title": title,
                "page": PAGE_OF[name],
            }
        )
    (HERE / "canvas.json").write_text(
        json.dumps(
            {
                "pages": [
                    {"id": "vorschlag", "name": "Предложение"},
                    {"id": "heute", "name": "Сегодня"},
                    {"id": "system", "name": "Компоненты и карта"},
                ],
                "artboards": boards,
                "annotations": NOTES,
                "launch": {"view": "canvas", "page": "vorschlag"},
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print("артбордов:", len(boards))


if __name__ == "__main__":
    main()
