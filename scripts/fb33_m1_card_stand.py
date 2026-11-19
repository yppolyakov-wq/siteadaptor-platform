"""FB-33 M1: стенд JS строки «Liste» в Студии — «Kartenform» скрыта у вида без карточки.

    uv run --with playwright==1.55.0 python scripts/fb33_m1_card_stand.py

Берёт обработчик смены полей из templates/tenant/site_home.html как есть и гоняет его
на минимальной строке в Chromium (/opt/pw-browsers). Не входит в CI (там нет браузера).
"""

import sys

from playwright.sync_api import sync_playwright

src = open("templates/tenant/site_home.html", encoding="utf-8").read()
i = src.index("    // LB-1: строка блока «Liste»")
j = src.index("syncGroupSummaries(row);  // сводка групп", i)
j = src.index("});", j) + 3
js = "function syncGroupSummaries(){}\n" + src[i:j]
html = (
    """<div data-lb-row>
<select data-lb-source><option value="products" selected>p</option><option value="promotions">a</option><option value="categories">c</option></select>
<select data-lb-style><option value="">std</option>
<option value="preisliste" data-lb-opt="products">pl</option>
<option value="rows" data-lb-opt="promotions">rows</option><option value="spotlight" data-lb-opt="promotions">sp</option></select>
<div id="card" data-lb-src="products promotions" data-lb-cardless="rows preisliste">card</div>
</div><script>"""
    + js
    + "</script>"
)
ok = True


def check(c, label):
    global ok
    ok &= c
    print(("ok  " if c else "FAIL ") + label)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    pg = b.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.set_content(html)

    def hidden():
        return pg.eval_on_selector("#card", "e => e.hidden")

    pg.select_option("[data-lb-style]", "preisliste")
    check(hidden(), "прайс-лист → поле скрыто")
    pg.select_option("[data-lb-style]", "")
    check(not hidden(), "сетка → поле видно")
    pg.select_option("[data-lb-source]", "promotions")
    pg.select_option("[data-lb-style]", "rows")
    check(hidden(), "акции · строки → скрыто")
    pg.select_option("[data-lb-style]", "spotlight")
    check(not hidden(), "акции · spotlight → видно")
    pg.select_option("[data-lb-source]", "products")
    check(not hidden(), "смена источника: вид spotlight скрыт → сброс на сетку, поле видно")
    pg.select_option("[data-lb-style]", "preisliste")
    pg.select_option("[data-lb-source]", "categories")
    check(hidden(), "категории → скрыто (нет карточки)")
    check(not errs, f"без ошибок JS {errs}")
    b.close()
sys.exit(0 if ok else 1)
