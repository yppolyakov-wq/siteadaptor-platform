"""STU: канвас «Studio v2 — два уровня + охват» (запрос владельца 2026-09-03).

Правки — ЗДЕСЬ, потом `python _generate.py` и пере-сид канваса.
Стиль вайрфрейма — как в `kategorie-vorlagen-2026-09-03` (владелец его принял).
"""

import json
from pathlib import Path

HERE = Path(__file__).parent

CSS = """
<style>
  body { margin: 0; font-family: Inter, "Segoe UI", sans-serif; color: #1f2937; }
  .wf { width: 960px; background: #fff; box-sizing: border-box; border: 1px solid #e5e7eb; }
  .app { display: flex; height: 470px; background: #f2f4f7; }
  .top { display: flex; align-items: center; gap: 10px; padding: 8px 14px;
         border-bottom: 1px solid #e5e7eb; background: #fff; font-size: 10px; color: #6b7280; }
  .top .brand { font-weight: 800; color: #111827; font-size: 12px; }
  .top .sp { flex: 1; }
  .rail { width: 132px; flex: 0 0 132px; background: #fff; border-right: 1px solid #e5e7eb;
          padding: 10px 8px; }
  .rail .it { display: flex; gap: 7px; align-items: flex-start; padding: 7px 8px;
              border-radius: 8px; font-size: 10px; color: #374151; margin-bottom: 3px; }
  .rail .it.on { background: #eef2ff; color: #3730a3; font-weight: 700; }
  .rail .it small { display: block; font-weight: 400; color: #9ca3af; font-size: 8px;
                    margin-top: 1px; line-height: 1.3; }
  .canvas { flex: 1; padding: 12px; min-width: 0; }
  .frame { background: #fff; border: 1px solid #d1d5db; border-radius: 8px; height: 100%;
           box-sizing: border-box; padding: 10px; position: relative; overflow: hidden; }
  .pane { width: 250px; flex: 0 0 250px; background: #fff; border-left: 1px solid #e5e7eb;
          padding: 10px; box-sizing: border-box; }
  .pane h4 { margin: 0 0 2px; font-size: 11px; color: #111827; }
  .pane .ctx { font-size: 9px; color: #6b7280; margin-bottom: 8px; }
  .fld { margin-bottom: 9px; }
  .fld .lb { font-size: 9px; color: #6b7280; margin-bottom: 3px; display: flex;
             justify-content: space-between; align-items: center; gap: 6px; }
  .ctrl { border: 1px solid #d1d5db; border-radius: 6px; padding: 5px 7px; font-size: 9px;
          color: #374151; background: #fff; }
  .tiles { display: flex; gap: 5px; }
  .tiles .t { flex: 1; border: 1px solid #d1d5db; border-radius: 6px; height: 30px;
              background: repeating-linear-gradient(135deg,#eef2f7 0 4px,#f8fafc 4px 8px); }
  .tiles .t.on { border-color: #4f46e5; box-shadow: 0 0 0 2px #e0e7ff inset; }
  .seg { display: flex; border: 1px solid #d1d5db; border-radius: 7px; overflow: hidden;
         font-size: 9px; margin-bottom: 9px; }
  .seg div { flex: 1; text-align: center; padding: 5px 3px; color: #6b7280; }
  .seg div.on { background: #111827; color: #fff; font-weight: 700; }
  .pill { border: 1px solid #d1d5db; border-radius: 999px; padding: 1px 7px; font-size: 8px;
          color: #6b7280; background: #fff; white-space: nowrap; }
  .pill.own { border-color: #4f46e5; color: #3730a3; background: #eef2ff; font-weight: 700; }
  .dot { width: 5px; height: 5px; border-radius: 999px; background: #4f46e5;
         display: inline-block; margin-right: 3px; }
  .ph { background: repeating-linear-gradient(135deg, #e5e7eb 0 6px, #f3f4f6 6px 12px); }
  .mock .hd { height: 22px; border-bottom: 1px solid #eef2f7; display: flex; gap: 5px;
              align-items: center; font-size: 8px; color: #9ca3af; }
  .mock .row { display: flex; gap: 7px; margin-top: 8px; }
  .mock .box { border: 1px solid #e5e7eb; border-radius: 6px; flex: 1; height: 62px; }
  .mock .sel { outline: 2px solid #4f46e5; outline-offset: 1px; position: relative; }
  .mock .sel::after { content: "⚙ настройки этой области"; position: absolute; top: -9px; left: 6px;
                      background: #4f46e5; color: #fff; font-size: 7px; padding: 1px 5px;
                      border-radius: 999px; }
  .cap { padding: 12px 16px 14px; background: #fafafa; border-top: 1px solid #e5e7eb;
         font-size: 11px; line-height: 1.55; color: #374151; }
  .cap b { color: #111827; }
  .tag { display: inline-block; font-size: 10px; font-weight: 600; padding: 2px 7px;
         border-radius: 999px; background: #dcfce7; color: #166534; margin-right: 4px; }
  .tag.warn { background: #fef3c7; color: #92400e; }
  .tag.new { background: #dbeafe; color: #1e40af; }
  .doc { padding: 18px 22px; width: 800px; box-sizing: border-box; }
  .doc h1 { font-size: 19px; margin: 0 0 3px; color: #111827; }
  .doc h2 { font-size: 12px; margin: 16px 0 6px; color: #111827; }
  .doc p, .doc li { font-size: 11px; line-height: 1.6; color: #374151; }
  .doc ul { margin: 4px 0 0; padding-left: 17px; }
  .doc .lead { color: #6b7280; font-size: 11px; margin-bottom: 2px; }
  table.cmp { border-collapse: collapse; width: 100%; font-size: 10px; margin-top: 6px; }
  table.cmp th, table.cmp td { border: 1px solid #e5e7eb; padding: 5px 7px;
                               text-align: left; vertical-align: top; }
  table.cmp th { background: #f9fafb; font-weight: 600; color: #111827; }
  .q { border-left: 3px solid #4f46e5; padding: 4px 0 4px 9px; margin: 7px 0; font-size: 11px; }
  .q b { color: #111827; }
</style>
"""


def top_bar(page_label):
    return f"""
  <div class="top"><span class="brand">Studio</span>
    <span>↶ ↷</span><span>🖥 📱</span>
    <span class="sp"></span>
    <span>{page_label}</span>
    <span class="pill">Vorschau</span><span class="pill own">Speichern</span></div>"""


def canvas_mock(title, sel_index=1, boxes=("Баннер", "Сетка товаров", "Отзывы")):
    rows = ""
    for i, _b in enumerate(boxes):
        cls = "box ph sel" if i == sel_index else "box ph"
        rows += f'<div class="{cls}"></div>'
    return f"""
    <div class="canvas"><div class="frame mock">
      <div class="hd">▢ {title}</div>
      <div class="row">{rows}</div>
      <div class="row"><div class="box ph"></div><div class="box ph"></div></div>
      <div class="row"><div class="box ph" style="height:40px"></div></div>
    </div></div>"""


def wrap(body, cap):
    return f"""<!-- STU canvas -->{CSS}
<div class="wf">{body}<div class="cap">{cap}</div></div>"""


# ─────────────────────────── V1 «Две полки» ───────────────────────────
V1 = wrap(
    top_bar("Страница товара · Bio-Apfelsaft")
    + """
  <div class="app">
    <div class="rail">
      <div class="it"><span>🎨</span><span>Дизайн сайта<small>Look, цвета, шрифт, карточки</small></span></div>
      <div class="it on"><span>📄</span><span>Эта страница<small>Страница товара</small></span></div>
      <div class="it"><span>🧱</span><span>Блоки<small>добавить на страницу</small></span></div>
      <div class="it"><span>🖼</span><span>Медиа</span></div>
    </div>"""
    + canvas_mock("/sortiment/bio-apfelsaft/", 1, ("Галерея", "Блок цены и кнопки", "Описание"))
    + """
    <div class="pane">
      <h4>Страница товара</h4>
      <div class="ctx">то, что вижу на канве</div>
      <div class="seg"><div class="on">Всем товарам</div><div>Только этому</div></div>
      <div class="fld"><div class="lb">Макет страницы</div>
        <div class="tiles"><div class="t on"></div><div class="t"></div><div class="t"></div></div></div>
      <div class="fld"><div class="lb">Галерея</div><div class="ctrl">Слева · миниатюры столбиком ▾</div></div>
      <div class="fld"><div class="lb">Секции</div>
        <div class="ctrl">☑ Отзывы &nbsp; ☑ Похожие &nbsp; ☐ Zuletzt angesehen</div></div>
      <div class="fld"><div class="lb">Форма карточки в списках</div>
        <div class="tiles"><div class="t"></div><div class="t on"></div><div class="t"></div></div></div>
    </div>
  </div>""",
    "<b>V1 «Две полки».</b> Слева — УРОВНИ, а не области: «Дизайн сайта» отдельным входом "
    "(как просил владелец), второй пункт подписан ТИПОМ страницы, на которой стоит канва. "
    "Охват — один переключатель вверху панели: <b>всем товарам / только этому</b>. "
    "<span class='tag'>ближе всего к формулировке владельца</span> "
    "<span class='tag warn'>минус: охват один на всю панель</span>",
)

# ──────────────────── V2 «Один инспектор + сегмент» ────────────────────
V2 = wrap(
    top_bar("Страница товара · Bio-Apfelsaft")
    + """
  <div class="app">
    <div class="rail" style="width:112px;flex:0 0 112px">
      <div class="it on"><span>⚙</span><span>Настройки</span></div>
      <div class="it"><span>🧱</span><span>Блоки</span></div>
      <div class="it"><span>🖼</span><span>Медиа</span></div>
      <div class="it"><span>📄</span><span>Страницы</span></div>
    </div>"""
    + canvas_mock("/sortiment/bio-apfelsaft/", 1, ("Галерея", "Блок цены и кнопки", "Описание"))
    + """
    <div class="pane">
      <div class="seg"><div>Весь сайт</div><div class="on">Этот тип</div><div>Только этот</div></div>
      <h4>Страница товара</h4>
      <div class="ctx">3 настройки переопределены для этого товара</div>
      <div class="fld"><div class="lb">Макет страницы</div>
        <div class="tiles"><div class="t on"></div><div class="t"></div><div class="t"></div></div></div>
      <div class="fld"><div class="lb">Галерея</div><div class="ctrl">Слева · миниатюры столбиком ▾</div></div>
      <div class="fld"><div class="lb">Секции</div>
        <div class="ctrl">☑ Отзывы &nbsp; ☑ Похожие &nbsp; ☐ Zuletzt angesehen</div></div>
      <div class="fld"><div class="lb">Форма карточки</div>
        <div class="tiles"><div class="t"></div><div class="t on"></div><div class="t"></div></div></div>
    </div>
  </div>""",
    "<b>V2 «Один инспектор + сегмент охвата».</b> Рейки уровней нет — уровень задаёт "
    "верхний сегмент <b>Весь сайт | Этот тип | Только этот</b>, содержимое панели меняется "
    "по нему и по типу страницы на канве. "
    "<span class='tag'>самый компактный хром, одна модель</span> "
    "<span class='tag warn'>минус: «Общий дизайн» перестаёт быть отдельным входом слева</span>",
)

# ─────────── V3 «Уровень в рейке + охват у каждой настройки» ───────────
V3 = wrap(
    top_bar("Страница товара · Bio-Apfelsaft")
    + """
  <div class="app">
    <div class="rail">
      <div class="it"><span>🎨</span><span>Дизайн сайта<small>Look, цвета, шрифт</small></span></div>
      <div class="it on"><span>📄</span><span>Эта страница<small>Страница товара</small></span></div>
      <div class="it"><span>🧱</span><span>Блоки</span></div>
      <div class="it"><span>🖼</span><span>Медиа</span></div>
    </div>"""
    + canvas_mock("/sortiment/bio-apfelsaft/", 1, ("Галерея", "Блок цены и кнопки", "Описание"))
    + """
    <div class="pane">
      <h4>Страница товара</h4>
      <div class="ctx">Bio-Apfelsaft · <span class="dot"></span>2 своих настройки</div>
      <div class="fld"><div class="lb">Макет страницы <span class="pill">для всех ▾</span></div>
        <div class="tiles"><div class="t on"></div><div class="t"></div><div class="t"></div></div></div>
      <div class="fld"><div class="lb"><span><span class="dot"></span>Галерея</span>
        <span class="pill own">только здесь ▾</span></div>
        <div class="ctrl">Слева · миниатюры столбиком ▾</div></div>
      <div class="fld"><div class="lb">Секции <span class="pill">для всех ▾</span></div>
        <div class="ctrl">☑ Отзывы &nbsp; ☑ Похожие &nbsp; ☐ Zuletzt angesehen</div></div>
      <div class="fld"><div class="lb"><span><span class="dot"></span>Форма карточки</span>
        <span class="pill own">только здесь ▾</span></div>
        <div class="tiles"><div class="t"></div><div class="t on"></div><div class="t"></div></div></div>
    </div>
  </div>""",
    "<b>V3 «Уровень в рейке + охват у каждой настройки» (гибрид).</b> Рейка как в V1, но охват — "
    "пилюля РЯДОМ С КАЖДОЙ настройкой; переопределённые помечены точкой, сразу видно, что у "
    "этого товара своё, а что от сайта. "
    "<span class='tag'>точно отражает механику «своё бьёт общее», уже работающую в коде</span> "
    "<span class='tag warn'>минус: элементов в панели больше, дороже в реализации</span>",
)


# ─────────────────── Второй уровень на разных типах ───────────────────
def page_type(title, ctx, fields, boxes, sel, cap):
    flds = ""
    for lb, ctrl, own in fields:
        pill = (
            '<span class="pill own">только здесь ▾</span>'
            if own
            else '<span class="pill">для всех ▾</span>'
        )
        dot = '<span class="dot"></span>' if own else ""
        flds += (
            f'<div class="fld"><div class="lb"><span>{dot}{lb}</span>{pill}</div>'
            f'<div class="ctrl">{ctrl}</div></div>'
        )
    return wrap(
        top_bar(title)
        + """
  <div class="app">
    <div class="rail">
      <div class="it"><span>🎨</span><span>Дизайн сайта</span></div>
      <div class="it on"><span>📄</span><span>Эта страница<small>"""
        + ctx
        + """</small></span></div>
      <div class="it"><span>🧱</span><span>Блоки</span></div>
      <div class="it"><span>🖼</span><span>Медиа</span></div>
    </div>"""
        + canvas_mock(title, sel, boxes)
        + f"""
    <div class="pane"><h4>{ctx}</h4><div class="ctx">настройки именно этого типа</div>{flds}</div>
  </div>""",
        cap,
    )


P_HOME = page_type(
    "Главная",
    "Главная",
    [
        ("Порядок и состав секций", "▤ Баннер · Акции · Категории · Отзывы …", False),
        ("Вид баннера", "Split · текст слева, фото справа ▾", False),
        ("Секция акций", "Spotlight · 1 крупная + 2 плитки ▾", False),
        ("Ряды плиток", "Verteilen (по центру) ▾", False),
    ],
    ("Баннер", "Акции", "Категории"),
    1,
    "<b>Главная.</b> Здесь второй уровень = то, что сегодня в области «sections»: состав и "
    "порядок секций, вид баннера, стиль каждой секции. Ничего не переезжает — просто перестаёт "
    "лежать вперемешку с настройками всего сайта.",
)

P_CAT = page_type(
    "/sortiment/getraenke/",
    "Категория товаров",
    [
        ("Шаблон страницы категории", "Schaufenster ▾", True),
        ("Раскладка товаров", "4 в ряд · Verteilen ▾", False),
        ("Фильтры", "☑ показывать · ☑ подкатегории первыми", False),
        ("Форма карточки", "Regal ▾", False),
    ],
    ("Шапка категории", "Подкатегории", "Сетка товаров"),
    2,
    "<b>Категория.</b> Ровно то, чего сейчас нет в Студии: шаблон страницы КАТЕГОРИИ "
    "(<i>Category.page_style</i>) правится только в форме категории. Здесь он на месте — с "
    "охватом «всем категориям / только этой». Подкатегория — тот же экран, отдельный тип не нужен.",
)

P_PROMO = page_type(
    "/aktionen/",
    "Страница акций",
    [
        ("Шаблон обзора", "Prospekt ▾", False),
        ("Группировка", "по темам ▾ (или по времени)", False),
        ("Вид групп", "лентами со стрелками ▾", False),
        ("Форма карточки акции", "Preis zuerst ▾", False),
    ],
    ("Kopfbild", "Чипы групп", "Группа «Wochenangebote»"),
    2,
    "<b>Акции.</b> Сегодня эти три настройки лежат в области «Тема» — то есть видны на ЛЮБОЙ "
    "странице и не видны на своей. Здесь они там, где ожидаются. Страница ГРУППЫ акций — "
    "такой же экран с охватом «всем группам / только этой».",
)

P_TEXT = page_type(
    "/ueber-uns/",
    "Текстовая страница",
    [
        ("Ширина текста", "узкая колонка ▾", False),
        ("Блоки страницы", "Заголовок · Текст+фото · Команда · FAQ", False),
        ("Шапка", "с фото ▾", False),
    ],
    ("Заголовок", "Текст + фото", "Команда"),
    1,
    "<b>Текстовые и правовые.</b> Сейчас на них панель показывает контролы ГЛАВНОЙ (скоуп-фильтр "
    "без хоста считает их главной). Здесь — только то, что применимо: блоки страницы и ширина.",
)

# ─────────────────────────── Сводка ───────────────────────────
MAIN = f"""<!-- STU canvas -->{CSS}
<div class="wf" style="width:800px"><div class="doc">
  <div class="lead">Запрос владельца 2026-09-03 · дизайн на утверждение</div>
  <h1>Studio v2 — два уровня настройки</h1>
  <p>«Есть 2 уровня: настройка дизайна сайта общая и настройка макета каждого типа страниц…
  Если я нахожусь на странице товара, то показывает настройки именно этого типа… применить
  для всех или изменить только для этого товара или категории… а то сейчас там каша».</p>

  <h2>Диагноз</h2>
  <p>Данные УЖЕ трёхуровневые, а интерфейс плоский:</p>
  <table class="cmp">
    <tr><th>Уровень</th><th>Что в нём живёт</th><th>Где настраивается сегодня</th></tr>
    <tr><td><b>Сайт</b></td><td>Look, цвет, шрифт, форма карточек, фон, хром</td>
        <td>Студия → «Тема» · <i>плюс те же Look/сборки ещё на 2 экранах</i></td></tr>
    <tr><td><b>Тип страницы</b></td><td>секции главной, шаблон каталога/категории/акций,
        раскладки листингов, секции деталей, блоки страницы</td>
        <td>размазано: часть в «Тема», часть в «Landing», часть на <i>/site/pages/</i>,
        часть в списке акций</td></tr>
    <tr><td><b>Объект</b></td><td>своя форма карточки у товара/акции, свой шаблон у категории
        и группы акций</td><td><b>в Студии недоступно вообще</b> — только формы кабинета</td></tr>
  </table>
  <p style="margin-top:8px">Плюс две несогласованные навигации (рейка уровней поверх вкладок
  областей), мёртвый код и дубли — отсюда ощущение каши.</p>

  <h2>Три варианта (артборды справа)</h2>
  <ul>
    <li><b>V1 «Две полки»</b> — уровень слева в рейке, охват одним переключателем вверху панели.</li>
    <li><b>V2 «Один инспектор»</b> — без рейки уровней, охват сегментом Весь сайт | Тип | Этот.</li>
    <li><b>V3 гибрид</b> — уровень в рейке + охват пилюлей у КАЖДОЙ настройки, переопределённые
        помечены точкой. <span class="tag new">рекомендация</span></li>
  </ul>
  <p>Дальше — как второй уровень выглядит на разных типах: главная · категория · акции ·
  текстовая. Клик по области канвы открывает ровно эту панель — на ЛЮБОМ типе страницы.</p>

  <h2>Что предлагается убрать</h2>
  <table class="cmp">
    <tr><th>Кандидат</th><th>Почему</th></tr>
    <tr><td>Экран <i>/dashboard/design/</i></td><td>третье место с теми же Look/сборками</td></tr>
    <tr><td>Экран <i>/dashboard/site/pages/</i></td><td>второй писатель раскладок листингов</td></tr>
    <tr><td>Область «Layout-Vorlagen» (quickstart)</td><td>переписывает секции, конфликтует со сборкой</td></tr>
    <tr><td>Пустая область «Footer», дубль <i>nav_style</i>, мёртвый JS</td><td>ничего не делают</td></tr>
  </table>

  <h2>Вопросы</h2>
  <div class="q"><b>Q1.</b> Какой вариант — V1, V2 или V3?</div>
  <div class="q"><b>Q2.</b> Убираем всё из списка выше или что-то оставить?</div>
  <div class="q"><b>Q3.</b> Типы страниц второго уровня: главная · каталог · категория · товар ·
    акции · группа акций · акция · услуги/номера/события · корзина · оформление заказа ·
    текстовые · правовые. Всё нужно?</div>
  <div class="q"><b>Q4.</b> Клик по области открывает макет типа, блоки этой области — или
    и то и другое одной панелью?</div>
  <div class="q"><b>Q5.</b> «Наборы» вариаций — это готовые комбинации «шаблон + карточка +
    раскладка» на тип страницы (как сборки, но для одной страницы)?</div>
</div></div>"""

BOARDS = [
    ("Main.dc.html", MAIN, 800, 1240, "Сводка и вопросы"),
    ("V1.dc.html", V1, 980, 700, "V1 · Две полки"),
    ("V2.dc.html", V2, 980, 700, "V2 · Один инспектор"),
    ("V3.dc.html", V3, 980, 700, "V3 · Гибрид (рекомендация)"),
    ("PHome.dc.html", P_HOME, 980, 680, "Тип: Главная"),
    ("PCat.dc.html", P_CAT, 980, 680, "Тип: Категория"),
    ("PPromo.dc.html", P_PROMO, 980, 680, "Тип: Акции"),
    ("PText.dc.html", P_TEXT, 980, 660, "Тип: Текстовая"),
]

arts, x, y = [], 0, 0
for i, (name, html, w, h, title) in enumerate(BOARDS):
    (HERE / name).write_text(html, encoding="utf-8")
    arts.append({"file": name, "x": x, "y": y, "w": w, "h": h, "title": title})
    x += w + 90
    if i in (3,):  # перенос строки после вариантов
        x, y = 0, 1340

(HERE / "canvas.json").write_text(
    json.dumps({"artboards": arts, "launch": {"view": "canvas"}}, ensure_ascii=False, indent=1),
    encoding="utf-8",
)
print("ok:", len(arts), "artboards")
