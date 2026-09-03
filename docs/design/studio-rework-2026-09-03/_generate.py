"""STU: канвас «Studio v2» (запрос владельца 2026-09-03).

Правки — ЗДЕСЬ, потом `python _generate.py` и пере-сид канваса.
Раскладка: всё компактно в две колонки, чтобы при открытии было видно сразу.
"""

import json
from pathlib import Path

HERE = Path(__file__).parent

CSS = """
<style>
  body { margin: 0; font-family: Inter, "Segoe UI", sans-serif; color: #1f2937; }
  .wf { width: 900px; background: #fff; box-sizing: border-box; border: 1px solid #e5e7eb; }
  .hd { padding: 11px 16px 10px; border-bottom: 1px solid #e5e7eb; background: #fff; }
  .hd .k { font-size: 10px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase;
           color: #4f46e5; }
  .hd h2 { margin: 2px 0 0; font-size: 16px; color: #111827; }
  .hd p { margin: 3px 0 0; font-size: 11px; color: #6b7280; line-height: 1.5; }
  .app { display: flex; height: 330px; background: #f2f4f7; }
  .top { display: flex; align-items: center; gap: 9px; padding: 7px 13px;
         border-bottom: 1px solid #e5e7eb; background: #fff; font-size: 10px; color: #6b7280; }
  .top .brand { font-weight: 800; color: #111827; font-size: 12px; }
  .top .sp { flex: 1; }
  .rail { width: 126px; flex: 0 0 126px; background: #fff; border-right: 1px solid #e5e7eb;
          padding: 9px 7px; }
  .rail .it { display: flex; gap: 6px; align-items: flex-start; padding: 6px 7px;
              border-radius: 8px; font-size: 10px; color: #374151; margin-bottom: 3px; }
  .rail .it.on { background: #eef2ff; color: #3730a3; font-weight: 700; }
  .rail .it small { display: block; font-weight: 400; color: #9ca3af; font-size: 8px;
                    margin-top: 1px; line-height: 1.3; }
  .canvas { flex: 1; padding: 10px; min-width: 0; }
  .frame { background: #fff; border: 1px solid #d1d5db; border-radius: 8px; height: 100%;
           box-sizing: border-box; padding: 9px; position: relative; overflow: hidden; }
  .pane { width: 244px; flex: 0 0 244px; background: #fff; border-left: 1px solid #e5e7eb;
          padding: 9px; box-sizing: border-box; }
  .pane h4 { margin: 0 0 2px; font-size: 11px; color: #111827; }
  .pane .ctx { font-size: 9px; color: #6b7280; margin-bottom: 8px; }
  .fld { margin-bottom: 8px; }
  .fld .lb { font-size: 9px; color: #6b7280; margin-bottom: 3px; display: flex;
             justify-content: space-between; align-items: center; gap: 6px; }
  .ctrl { border: 1px solid #d1d5db; border-radius: 6px; padding: 5px 7px; font-size: 9px;
          color: #374151; background: #fff; }
  .tiles { display: flex; gap: 5px; }
  .tiles .t { flex: 1; border: 1px solid #d1d5db; border-radius: 6px; height: 28px;
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
  .mock .cap2 { height: 20px; border-bottom: 1px solid #eef2f7; display: flex; gap: 5px;
                align-items: center; font-size: 8px; color: #9ca3af; }
  .mock .row { display: flex; gap: 6px; margin-top: 7px; }
  .mock .box { border: 1px solid #e5e7eb; border-radius: 6px; flex: 1; height: 54px; }
  .mock .sel { outline: 2px solid #4f46e5; outline-offset: 1px; position: relative; }
  .mock .sel::after { content: "⚙ настройки этой области"; position: absolute; top: -8px; left: 5px;
                      background: #4f46e5; color: #fff; font-size: 7px; padding: 1px 5px;
                      border-radius: 999px; }
  .cap { padding: 11px 16px 13px; background: #fafafa; border-top: 1px solid #e5e7eb;
         font-size: 11px; line-height: 1.55; color: #374151; }
  .cap b { color: #111827; }
  .tag { display: inline-block; font-size: 10px; font-weight: 600; padding: 2px 7px;
         border-radius: 999px; background: #dcfce7; color: #166534; margin-right: 4px; }
  .tag.warn { background: #fef3c7; color: #92400e; }
  .tag.bad { background: #fee2e2; color: #991b1b; }
  .tag.new { background: #dbeafe; color: #1e40af; }
  .doc { padding: 18px 22px; box-sizing: border-box; }
  .doc h1 { font-size: 19px; margin: 0 0 3px; color: #111827; }
  .doc h2 { font-size: 12px; margin: 15px 0 5px; color: #111827; }
  .doc p, .doc li { font-size: 11px; line-height: 1.6; color: #374151; }
  .doc ul { margin: 4px 0 0; padding-left: 17px; }
  .doc .lead { color: #6b7280; font-size: 11px; margin-bottom: 2px; }
  table.cmp { border-collapse: collapse; width: 100%; font-size: 10px; margin-top: 6px; }
  table.cmp th, table.cmp td { border: 1px solid #e5e7eb; padding: 5px 7px;
                               text-align: left; vertical-align: top; }
  table.cmp th { background: #f9fafb; font-weight: 600; color: #111827; }
  .ask { border: 1px solid #4f46e5; background: #eef2ff; border-radius: 9px;
         padding: 10px 12px; margin: 9px 0; }
  .ask b { color: #3730a3; }
  .ask p { margin: 3px 0 0; }
  .abc { display: flex; gap: 10px; padding: 12px 16px; }
  .abc > div { flex: 1; border: 1px solid #e5e7eb; border-radius: 9px; padding: 10px; }
  .abc h5 { margin: 0 0 6px; font-size: 11px; color: #111827; }
  .abc .note { font-size: 10px; color: #6b7280; line-height: 1.45; margin-top: 7px; }
</style>
"""


def head(kicker, title, sub):
    return f'<div class="hd"><div class="k">{kicker}</div><h2>{title}</h2><p>{sub}</p></div>'


def top_bar(page_label):
    return f"""
  <div class="top"><span class="brand">Studio</span><span>↶ ↷</span><span>🖥 📱</span>
    <span class="sp"></span><span>{page_label}</span>
    <span class="pill">Просмотр</span><span class="pill own">Сохранить</span></div>"""


def canvas_mock(title, sel_index, boxes):
    rows = "".join(
        f'<div class="{"box ph sel" if i == sel_index else "box ph"}"></div>'
        for i, _b in enumerate(boxes)
    )
    return f"""
    <div class="canvas"><div class="frame mock">
      <div class="cap2">▢ {title}</div>
      <div class="row">{rows}</div>
      <div class="row"><div class="box ph"></div><div class="box ph"></div></div>
      <div class="row"><div class="box ph" style="height:34px"></div></div>
    </div></div>"""


def wrap(body, cap, width=900):
    return f"""<!-- STU canvas -->{CSS}
<div class="wf" style="width:{width}px">{body}<div class="cap">{cap}</div></div>"""


# ─────────────────── A0: что не так сегодня ───────────────────
A0 = wrap(
    head(
        "Что не так сегодня",
        "Настройки лежат не там, где их ищут",
        "Один и тот же экран Студии показывает всё сразу — и то, что относится ко всему сайту, "
        "и то, что относится к одной странице. Настройки страницы акций вообще лежат в «Теме».",
    ),
    "",
    900,
).replace(
    '<div class="cap"></div>',
    """
  <div style="padding:12px 16px 16px">
    <table class="cmp">
      <tr><th style="width:190px">Что настраиваю</th><th>Где это сегодня</th><th>Проблема</th></tr>
      <tr><td>Цвет, шрифт, Look — <b>весь сайт</b></td><td>Студия → «Тема»</td>
          <td>то же самое ещё на двух экранах: <i>/design/</i> и мастер</td></tr>
      <tr><td>Секции главной</td><td>Студия → «sections»</td><td>ок</td></tr>
      <tr><td>Шаблон страницы <b>акций</b></td><td>Студия → «Тема» (!)</td>
          <td>видно на любой странице и <b>не видно на своей</b></td></tr>
      <tr><td>Раскладка каталога / услуг / номеров</td><td>Студия <b>и</b> отдельный экран
          <i>/site/pages/</i></td><td>два экрана пишут одно и то же</td></tr>
      <tr><td>Шаблон <b>конкретной категории</b></td><td>только форма категории</td>
          <td><b>в Студии нет вообще</b></td></tr>
      <tr><td>Форма карточки <b>конкретного товара / акции</b></td><td>только форма товара / акции</td>
          <td><b>в Студии нет вообще</b></td></tr>
      <tr><td>Шаблон <b>группы акций</b></td><td>только список акций</td>
          <td><b>в Студии нет вообще</b></td></tr>
    </table>
    <p style="font-size:11px;color:#374151;line-height:1.6;margin-top:9px">
      <span class="tag bad">итог</span> В данных давно есть три уровня: <b>весь сайт → тип страницы
      → конкретный товар/категория</b>, и «своё побеждает общее» уже работает. В интерфейсе этих
      уровней нет — поэтому и ощущение каши.</p>
  </div>""",
)

# ─────────────────── A1: как будет (главный экран) ───────────────────
A1 = wrap(
    head(
        "Как будет",
        "Слева — уровень, справа — настройки того, что вижу",
        "Стою на странице товара → панель показывает настройки страницы товара. Перешёл в "
        "категорию → настройки категории. «Дизайн сайта» — отдельным входом слева.",
    )
    + top_bar("Страница товара · Bio-Apfelsaft")
    + """
  <div class="app">
    <div class="rail">
      <div class="it"><span>🎨</span><span>Дизайн сайта<small>Look, цвет, шрифт — на всё</small></span></div>
      <div class="it on"><span>📄</span><span>Эта страница<small>Страница товара</small></span></div>
      <div class="it"><span>🧱</span><span>Блоки<small>добавить на страницу</small></span></div>
      <div class="it"><span>🖼</span><span>Медиа</span></div>
    </div>"""
    + canvas_mock("/sortiment/bio-apfelsaft/", 1, ("Галерея", "Цена и кнопка", "Описание"))
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
        <div class="ctrl">☑ Отзывы &nbsp; ☑ Похожие &nbsp; ☐ Недавно смотрели</div></div>
      <div class="fld"><div class="lb"><span><span class="dot"></span>Форма карточки</span>
        <span class="pill own">только здесь ▾</span></div>
        <div class="tiles"><div class="t"></div><div class="t on"></div><div class="t"></div></div></div>
    </div>
  </div>""",
    "Три вещи, которых сегодня нет: <b>(1)</b> «Дизайн сайта» и «Эта страница» — РАЗНЫЕ входы, "
    "не свалка в одной панели; <b>(2)</b> панель знает, на какой странице стоит канва, и "
    "показывает настройки именно этого типа; <b>(3)</b> у каждой настройки видно, действует она "
    "на всё или только здесь — <span class='pill'>для всех</span> / "
    "<span class='pill own'>только здесь</span>, переопределённые помечены точкой. "
    "Клик по области на канве открывает эту же панель — на ЛЮБОМ типе страницы, не только на главной.",
)

# ─────────────────── A2: где показывать «для всех / только здесь» ───────────────────
A2 = f"""<!-- STU canvas -->{CSS}
<div class="wf" style="width:900px">
  {
    head(
        "Единственный выбор, который нужен от вас",
        "Где стоит переключатель «для всех / только здесь»",
        "Сам механизм одинаков во всех трёх — отличается только место переключателя. "
        "Всё остальное (уровни слева, панель по типу страницы, клик по области) делаю одинаково.",
    )
}
  <div class="abc">
    <div>
      <h5>A · У каждой настройки</h5>
      <div class="fld"><div class="lb">Макет <span class="pill">для всех ▾</span></div>
        <div class="tiles"><div class="t on"></div><div class="t"></div></div></div>
      <div class="fld"><div class="lb"><span><span class="dot"></span>Галерея</span>
        <span class="pill own">только здесь ▾</span></div>
        <div class="ctrl">Слева ▾</div></div>
      <div class="note">Можно смешивать: макет — всем, галерея — только этому товару.
        Точкой видно, что переопределено. <span class="tag">рекомендую</span></div>
    </div>
    <div>
      <h5>B · Один на всю панель</h5>
      <div class="seg"><div class="on">Всем товарам</div><div>Только этому</div></div>
      <div class="fld"><div class="lb">Макет</div>
        <div class="tiles"><div class="t on"></div><div class="t"></div></div></div>
      <div class="fld"><div class="lb">Галерея</div><div class="ctrl">Слева ▾</div></div>
      <div class="note">Проще на вид. Но чтобы часть настроек задать всем, а часть — одному
        товару, придётся переключать туда-сюда.</div>
    </div>
    <div>
      <h5>C · Три режима вверху</h5>
      <div class="seg"><div>Весь сайт</div><div class="on">Этот тип</div><div>Только этот</div></div>
      <div class="fld"><div class="lb">Макет</div>
        <div class="tiles"><div class="t on"></div><div class="t"></div></div></div>
      <div class="note">Уровень выбирается сегментом, а не слева. Тогда отдельного входа
        «Дизайн сайта» слева нет — против того, что вы просили.</div>
    </div>
  </div>
  <div class="cap"><b>Почему это вообще выбор.</b> «Применить всем или только этому товару» —
  ваши слова. Механика в коде уже есть (у товара, категории, акции своё поле, оно побеждает
  общее). Вопрос только в том, как это показать: <b>A</b> — гибко, но элементов больше;
  <b>B</b> — чище, но переключаться чаще; <b>C</b> — компактно, но теряется отдельный вход
  «Дизайн сайта».</div>
</div>"""


# ─────────────────── Типы страниц ───────────────────
def page_type(kicker, title, sub, ctx, fields, boxes, sel, cap):
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
        head(kicker, title, sub)
        + top_bar(ctx)
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
    "Тип страницы 1 из 4",
    "Главная",
    "Стою на главной — панель про главную.",
    "Главная",
    [
        ("Порядок и состав секций", "▤ Баннер · Акции · Категории · Отзывы …", False),
        ("Вид баннера", "Split · текст слева, фото справа ▾", False),
        ("Секция акций", "Spotlight · 1 крупная + 2 плитки ▾", False),
        ("Ряды плиток", "Verteilen (по центру) ▾", False),
    ],
    ("Баннер", "Акции", "Категории"),
    1,
    "<b>Главная.</b> Ничего не переезжает — то же, что сегодня в области «секции». Просто "
    "перестаёт лежать вперемешку с настройками всего сайта.",
)

P_CAT = page_type(
    "Тип страницы 2 из 4",
    "Категория товаров",
    "Стою в категории «Getränke» — панель про категорию.",
    "Категория товаров",
    [
        ("Шаблон страницы категории", "Schaufenster ▾", True),
        ("Раскладка товаров", "4 в ряд · Verteilen ▾", False),
        ("Фильтры", "☑ показывать · ☑ подкатегории первыми", False),
        ("Форма карточки", "Regal ▾", False),
    ],
    ("Шапка категории", "Подкатегории", "Сетка товаров"),
    2,
    "<b>Категория.</b> Ровно то, чего в Студии нет: шаблон страницы КАТЕГОРИИ правится только "
    "в форме категории. Здесь он на месте, с выбором «всем категориям / только этой». "
    "Подкатегория — тот же экран, отдельный тип не нужен.",
)

P_PROMO = page_type(
    "Тип страницы 3 из 4",
    "Страница акций",
    "Стою на /aktionen/ — панель про акции.",
    "Страница акций",
    [
        ("Шаблон обзора", "Prospekt ▾", False),
        ("Группировка", "по темам ▾ (или по времени)", False),
        ("Вид групп", "лентами со стрелками ▾", False),
        ("Форма карточки акции", "Preis zuerst ▾", False),
    ],
    ("Kopfbild", "Чипы групп", "Группа «Wochenangebote»"),
    2,
    "<b>Акции.</b> Сегодня эти настройки лежат в «Теме»: видны на любой странице и НЕ видны на "
    "своей. Здесь они там, где их ищут. Страница отдельной группы акций — такой же экран с "
    "выбором «всем группам / только этой».",
)

P_TEXT = page_type(
    "Тип страницы 4 из 4",
    "Текстовая страница",
    "Стою на «О нас» — панель про текстовую страницу.",
    "Текстовая страница",
    [
        ("Ширина текста", "узкая колонка ▾", False),
        ("Блоки страницы", "Заголовок · Текст+фото · Команда · FAQ", False),
        ("Шапка", "с фото ▾", False),
    ],
    ("Заголовок", "Текст + фото", "Команда"),
    1,
    "<b>Текстовые и правовые.</b> Сегодня на них панель показывает контролы ГЛАВНОЙ. "
    "Здесь — только применимое: блоки страницы и ширина.",
)

# ─────────────────── Сводка ───────────────────
MAIN = f"""<!-- STU canvas -->{CSS}
<div class="wf" style="width:820px"><div class="doc">
  <div class="lead">Запрос владельца 2026-09-03 · дизайн на утверждение</div>
  <h1>Studio: два уровня вместо одной свалки</h1>
  <p>Ваши слова: «есть 2 уровня — настройка дизайна сайта общая и настройка макета каждого типа
  страниц… если я нахожусь на странице товара, показывает настройки именно этого типа…
  применить для всех или изменить только для этого товара или категории… а то сейчас там каша».</p>

  <h2>Что предлагается (одинаково во всех вариантах)</h2>
  <ul>
    <li>Слева — <b>уровни</b>: «Дизайн сайта» · «Эта страница» · «Блоки» · «Медиа».
      Сейчас слева области, которые не совпадают с тем, что внутри.</li>
    <li>«Эта страница» подписана <b>типом</b> той страницы, на которой стоит канва, и показывает
      только её настройки.</li>
    <li><b>Клик по области</b> на канве открывает эту панель на ЛЮБОМ типе страницы —
      сейчас так работает только главная.</li>
    <li>В Студию приходит то, чего в ней не было: шаблон конкретной категории, форма карточки
      конкретного товара и акции, шаблон группы акций.</li>
  </ul>

  <h2>Что уберём (чтобы не мешало)</h2>
  <table class="cmp">
    <tr><th>Убираем</th><th>Почему</th><th>Куда переедет</th></tr>
    <tr><td>Экран «Design»</td><td>третье место с теми же Look и сборками</td>
        <td>уровень «Дизайн сайта»</td></tr>
    <tr><td>Экран «Pages»</td><td>второй экран, пишущий те же раскладки</td>
        <td>уровень «Эта страница»</td></tr>
    <tr><td>«Layout-Vorlagen» в Студии</td><td>перезаписывают секции, спорят со сборкой</td>
        <td>сборки — «Дизайн сайта», демо-контент — мастер</td></tr>
    <tr><td>Пустой раздел «Footer», дубль настройки меню, мёртвый код</td>
        <td>ничего не делают</td><td>—</td></tr>
  </table>

  <div class="ask"><b>Вопрос 1 — единственный обязательный.</b>
    <p>Где показывать «для всех / только здесь»: <b>A</b> у каждой настройки (рекомендую),
    <b>B</b> один переключатель на панель, <b>C</b> три режима вверху? Смотрите артборд
    «Единственный выбор».</p></div>

  <div class="ask"><b>Вопрос 2 — если есть возражения.</b>
    <p>Список «что уберём» выше. Если возражений нет — сношу как написано, с редиректами,
    чтобы старые ссылки не ломались.</p></div>

  <p style="margin-top:10px;color:#6b7280">Всё остальное я решу сам по ходу: какие типы страниц
  завести (главная, каталог, категория, товар, акции, группа акций, акция, услуги/номера/события,
  корзина, оформление заказа, текстовые, правовые) и что именно открывать по клику в область
  (макет типа + блоки этой области одной панелью). Миграций не потребуется — поля у товара,
  категории и акции уже есть.</p>
</div></div>"""

BOARDS = [
    ("Main.dc.html", MAIN, 820, 1080, "① Сводка и вопросы"),
    ("A0.dc.html", A0, 900, 560, "② Что не так сегодня"),
    ("A1.dc.html", A1, 900, 640, "③ Как будет"),
    ("A2.dc.html", A2, 900, 470, "④ Единственный выбор: A / B / C"),
    ("PHome.dc.html", P_HOME, 900, 660, "Тип: Главная"),
    ("PCat.dc.html", P_CAT, 900, 660, "Тип: Категория"),
    ("PPromo.dc.html", P_PROMO, 900, 660, "Тип: Акции"),
    ("PText.dc.html", P_TEXT, 900, 640, "Тип: Текстовая"),
]

# две колонки: слева сводка, справа стопка — компактно, без длинной горизонтали
POS = [
    (0, 0),
    (1020, 0),
    (1020, 690),
    (1020, 1460),
    (0, 1210),
    (1020, 2060),
    (0, 2000),
    (1020, 2850),
]

arts = []
for (name, html, w, h, title), (x, y) in zip(BOARDS, POS, strict=True):
    (HERE / name).write_text(html, encoding="utf-8")
    arts.append({"file": name, "x": x, "y": y, "w": w, "h": h, "title": title})

(HERE / "canvas.json").write_text(
    json.dumps({"artboards": arts, "launch": {"view": "canvas"}}, ensure_ascii=False, indent=1),
    encoding="utf-8",
)
print("ok:", len(arts), "artboards")
