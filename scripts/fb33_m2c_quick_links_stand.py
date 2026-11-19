"""FB-33 M2c: стенд «Schnellzugriff» — главная до/после `detach_quick_links` (1440 и 390).

    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run --with playwright==1.55.0 python scripts/fb33_m2c_quick_links_stand.py <папка> <метка> [сайты]

Печатает ширину прокрутки, наличие блока и кнопки баннера, ошибки JS; снимает скриншоты.
Не входит в CI (там нет браузера).
"""

import sys

from playwright.sync_api import sync_playwright

out, tag = sys.argv[1], sys.argv[2]
SITES = sys.argv[3].split(",") if len(sys.argv) > 3 else ("ptx", "r9friseur")
with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/opt/pw-browsers/chromium",
        args=["--host-resolver-rules=MAP *.siteadaptor.de 127.0.0.1"],
    )
    for site in SITES:
        for w, h in ((1440, 900), (390, 844)):
            pg = b.new_page(viewport={"width": w, "height": h})
            errs = []
            pg.on("pageerror", lambda e, errs=errs: errs.append(str(e)))
            pg.goto(f"http://{site}.siteadaptor.de:8000/", wait_until="networkidle")
            sw = pg.evaluate("document.documentElement.scrollWidth")
            block = pg.locator("[data-block-quick-links]").count()
            cta = pg.locator("[data-hero-cta]").count()
            pg.screenshot(path=f"{out}/m2c-{tag}-{site}-{w}.png")
            print(tag, site, w, "scrollW", sw, "block", block, "cta", cta, "errs", errs)
            pg.close()
    b.close()
