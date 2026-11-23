"""FB-33 стопка 11 (M5c-4m, C3m): стенд «Menü» открывается на вкладке из адреса `?tab=`
(1440/390, de/ru, с JS и без; демо-киты friseur и shop).

Что проверяет (план `docs/fb33-stack11-plan-2026-11-23.md` §2 C3m, §4 C3m, §8.1 L4):
- `/dashboard/site/menu/?tab=footer` открывает «Fußzeile»: кнопка вкладки `aria-selected=true`,
  видна панель подвала и её вводная, панели шапки и нижней полосы скрыты — и без JS;
- `?tab=bottom`, а чужое значение (`?tab=zzz`) — как без параметра: «Kopfzeile»;
- скрытое поле `tab` формы несёт открытую вкладку;
- с JS: клик по вкладке обновляет поле `tab`, «Speichern» возвращает на ту же вкладку
  (адрес `?tab=<вкладка>`, она открыта после перезагрузки);
- клавиатура как раньше: Tab переходит между тремя кнопками вкладок, Enter открывает вкладку;
- без горизонтальной прокрутки, без ошибок JS; ru — подпись вкладки подвала переведена.

Без JS конструктор меню не работает и до правки (дерево рисует скрипт) — это не регресс;
стенд без JS проверяет только, что открыта нужная вкладка и видна её вводная.

Запуск (стенд-БД — копия с демо-китами, вход `<kit>@example.com` / `demo-12345678`):
    DB_NAME=<стенд-БД> python manage.py runserver 0.0.0.0:8047 --settings=config.settings.stand --noreload
    STAND_URL=http://friseur.siteadaptor.de:8047 \\
        uv run --no-project --with playwright python scripts/fb33_m5c3m_menu_tab_stand.py <папка>
«Speichern» пишет меню без изменений (то же дерево) — данные стенд-БД не меняются по сути.
Итог: «N ✓, M ✗». Не входит в CI (там нет браузера).
"""

from __future__ import annotations

import sys
from urllib.parse import urlparse

import standlib as sl

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fb33_m5c3m_shots"
PORT = urlparse(sl.BASE_URL).port or 80
DEMO_PASSWORD = "demo-12345678"
KITS = ("friseur", "shop")
PATH = "/dashboard/site/menu/"
TABS = ("top", "bottom", "footer")

STATE_JS = """() => {
  const vis = el => !!el && !el.hidden && getComputedStyle(el).display !== 'none'
    && el.getBoundingClientRect().height > 0;
  const out = {sel: [], open: [], field: null};
  document.querySelectorAll('[data-tab]').forEach(b => {
    if (b.getAttribute('aria-selected') === 'true') out.sel.push(b.dataset.tab); });
  document.querySelectorAll('[data-pane]').forEach(p => { if (vis(p)) out.open.push(p.dataset.pane); });
  const f = document.querySelector('#menu-form input[name=tab]');
  out.field = f ? f.value : null;
  const intro = document.querySelector('[data-pane=footer] > p');
  out.introVisible = vis(intro);
  const ft = document.querySelector('[data-tab=footer]');
  out.footerLabel = ft ? ft.textContent.trim() : '';
  out.overflow = document.documentElement.scrollWidth - window.innerWidth;
  return out; }"""


def base_of(slug):
    return f"http://{slug}.{sl.BASE_DOMAIN}:{PORT}"


def state(page):
    return page.evaluate(STATE_JS)


def check_open(rep, page, tag, key):
    st = state(page)
    rep.check(st["sel"] == [key], f"{tag}: выбрана вкладка {key} ({st['sel']})", code="tab")
    rep.check(st["open"] == [key], f"{tag}: открыта панель {key} ({st['open']})", code="pane")
    rep.check(st["field"] == key, f"{tag}: поле tab = {key} ({st['field']})", code="field")
    rep.check(st["overflow"] <= 0, f"{tag}: без гор. скролла ({st['overflow']}px)", code="overflow")
    return st


def run():
    rep = sl.Report()
    with sl.launch() as browser:
        for slug in KITS:
            base = base_of(slug)
            for w, h, lang, js in sl.matrix():
                page = sl.open_page(browser, w, h, js=js, lang=lang, url=base)
                tag = f"{slug} {w} {lang} {'js' if js else 'nojs'}"
                if not rep.check(
                    sl.login(page, base, f"{slug}@example.com", DEMO_PASSWORD), f"{tag}: вход"
                ):
                    page.context.close()
                    continue
                resp = page.goto(base + PATH + "?tab=footer")
                sl.settle(page, js, rep)
                rep.check(resp.status == 200, f"{tag}: ответ {resp.status}", code="status")
                st = check_open(rep, page, f"{tag} ?tab=footer", "footer")
                rep.check(st["introVisible"], f"{tag}: видна вводная подвала", code="intro")
                if lang == "ru":
                    rep.check(
                        st["footerLabel"] and st["footerLabel"] != "Fußzeile",
                        f"{tag}: подпись вкладки переведена ({st['footerLabel']!r})",
                        code="ru",
                    )
                sl.shot(page, OUT, f"{slug}_footer_{w}_{lang}_{'js' if js else 'nojs'}")

                page.goto(base + PATH + "?tab=bottom")
                sl.settle(page, js, rep)
                check_open(rep, page, f"{tag} ?tab=bottom", "bottom")
                page.goto(base + PATH + "?tab=zzz")
                sl.settle(page, js, rep)
                check_open(rep, page, f"{tag} ?tab=zzz", "top")
                page.goto(base + PATH)
                sl.settle(page, js, rep)
                check_open(rep, page, f"{tag} без параметра", "top")

                if js:
                    # клик вкладки → поле tab; «Speichern» возвращает на неё
                    page.click("[data-tab=footer]")
                    check_open(rep, page, f"{tag} клик footer", "footer")
                    with page.expect_navigation():
                        page.click("#menu-form button[type=submit]")
                    sl.settle(page, js, rep)
                    rep.check(
                        page.url.endswith(PATH + "?tab=footer"),
                        f"{tag}: после сохранения адрес ?tab=footer ({page.url})",
                        code="redirect",
                    )
                    check_open(rep, page, f"{tag} после сохранения", "footer")
                    page.click("[data-tab=top]")
                    with page.expect_navigation():
                        page.click("#menu-form button[type=submit]")
                    sl.settle(page, js, rep)
                    rep.check(
                        page.url.endswith(PATH),
                        f"{tag}: «Kopfzeile» сохраняется на прежний адрес ({page.url})",
                        code="redirect",
                    )
                    check_open(rep, page, f"{tag} после сохранения top", "top")

                    # клавиатура как раньше: Tab между кнопками, Enter открывает
                    page.focus("[data-tab=top]")
                    page.keyboard.press("Tab")
                    focused = page.evaluate(
                        "() => document.activeElement && document.activeElement.dataset.tab"
                    )
                    rep.check(
                        focused == "bottom", f"{tag}: Tab → вкладка bottom ({focused})", code="kbd"
                    )
                    page.keyboard.press("Tab")
                    page.keyboard.press("Enter")
                    check_open(rep, page, f"{tag} Enter на footer", "footer")
                    page.keyboard.press("Shift+Tab")
                    page.keyboard.press("Space")
                    check_open(rep, page, f"{tag} Space на bottom", "bottom")
                rep.check(
                    not page.js_errors, f"{tag}: без ошибок JS ({page.js_errors[:2]})", code="js"
                )
                page.context.close()
    rep.finish("fb33 m5c3m menu tab")


if __name__ == "__main__":
    run()
