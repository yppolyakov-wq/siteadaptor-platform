"""FB-33 M5a: стенд страницы 404 витрины с блоками (1440/390, de/ru, без JS и с JS).

Посетитель: неизвестный адрес → код 404, один h1, блок «Suche» (там же, где поиск есть в шапке),
плитки «Beliebt» = пункты верхнего уровня меню, без горизонтального скролла, цели ≥ 24 px,
ни одной новой cookie, вне индекса; поиск из блока уходит GET-запросом `?q=`. Превью анониму —
404. Неизвестный хост платформы — прежняя простая страница (ревью плана, R1).
Владелец: тип «Seite nicht gefunden» в «Seitenaufbau», блоки по умолчанию строками, окно блока
«Schnellzugriff» с набором «Hauptmenü», превью отвечает 200. Стенд ничего не сохраняет.

`handler404` Django зовёт только при DEBUG=False — сервер стенда поднимается с `STAND_DEBUG=0`
(`config/settings/stand.py`) и `--insecure` (статика без DEBUG):

    DB_NAME=<стенд-БД> uv run python scripts/text_pages_stand.py --setup     # один раз (ptx)
    DB_NAME=<стенд-БД> STAND_DEBUG=0 python manage.py runserver 0.0.0.0:8051 \\
        --settings=config.settings.stand --noreload --insecure
    DB_NAME=<стенд-БД> STAND_URL=http://ptx.siteadaptor.de:8051 \\
        uv run --no-project --with playwright python scripts/fb33_m5a_404_stand.py <папка>

Меню для сверки плиток скрипт читает из той же стенд-БД (`manage.py shell`) и там же включает
бизнесу стенда русский язык витрины (иначе проход «ru» шёл бы по-немецки). Итог «N ✓, 0 ✗».
"""

from __future__ import annotations

import json
import subprocess
import sys
from urllib.parse import urlsplit

import fb33_m3_9_owner_stand as owner
import standlib as sl

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fb33_m5a_404"
SLUG = "ptx"
MISSING = "/gibt-es-nicht-m5a/"
PREVIEW = "/seite-nicht-gefunden/vorschau/"
AUFBAU = "/dashboard/site/aufbau/?seite=not_found"
TILES_MAX = 8  # hero_tiles.MENU_TILES_MAX
H1 = {"de": "Seite nicht gefunden.", "ru": "Страница не найдена."}

MENU = f"""
import json
from django_tenants.utils import schema_context
from apps.tenants import menu, siteconfig
from apps.tenants.models import Tenant
t = Tenant.objects.get(schema_name={SLUG!r})
if "ru" not in (t.enabled_locales or []):  # витрина говорит только на языках бизнеса
    t.enabled_locales = [*(t.enabled_locales or ["de"]), "ru"]
    t.save(update_fields=["enabled_locales"])
with schema_context({SLUG!r}):
    items = menu.resolve_menu(t, "top", siteconfig.normalize(t.site_config))
print("MENU" + json.dumps([i["url"] for i in items if i.get("url") and i.get("label")]))
"""


def menu_urls() -> list[str]:
    res = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "manage.py",
            "shell",
            "--settings=config.settings.stand",
            "-c",
            MENU,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    line = next((ln for ln in res.stdout.splitlines() if ln.startswith("MENU")), None)
    if line is None:
        sys.exit("меню стенда не прочитано:\n" + res.stderr[-600:])
    return json.loads(line[4:])


def visitor(browser, rep, w, h, lang, js, want_tiles):
    tag = f"{w} {lang} {'js' if js else 'nojs'}"
    name = f"{w}_{lang}_{'js' if js else 'nojs'}"
    page = sl.open_page(browser, w, h, js=js, lang=lang)
    before = {c["name"] for c in page.context.cookies()}
    resp = page.goto(sl.BASE_URL + MISSING)
    sl.settle(page, js, rep)
    rep.check(resp.status == 404, f"{tag}: неизвестный адрес → {resp.status}", code="status")
    if not rep.check(page.locator("[data-not-found]").count() == 1, f"{tag}: страница с блоками"):
        page.context.close()
        return
    rep.check(page.locator("h1").count() == 1, f"{tag}: один h1")
    rep.check(page.locator("h1").inner_text().strip() == H1[lang], f"{tag}: h1 на языке сайта")
    rep.check(
        page.locator("body").get_attribute("data-stu-page") == "not_found",
        f"{tag}: тип страницы для Студии",
    )
    rep.check(page.locator('meta[name=robots][content^="noindex"]').count() >= 1, f"{tag}: noindex")
    rep.check("noindex" in (resp.headers.get("x-robots-tag") or ""), f"{tag}: X-Robots-Tag")
    rep.check(page.locator("link[rel=canonical]").count() == 0, f"{tag}: без canonical")
    rep.check(
        page.locator('script[type="application/ld+json"]').count() == 0, f"{tag}: без JSON-LD"
    )
    after = {c["name"] for c in page.context.cookies()}
    rep.check(after == before, f"{tag}: ни одной новой cookie ({sorted(after - before)})")

    has_search = page.locator(".sf-hsearch").count() > 0
    form = page.locator("[data-block-site-search] form[role=search]")
    rep.check(form.count() == int(has_search), f"{tag}: блок поиска там, где поиск есть в шапке")
    hrefs = page.locator("[data-block-quick-links] a").evaluate_all(
        "els => els.map(e => e.getAttribute('href'))"
    )
    rep.check(hrefs == want_tiles, f"{tag}: плитки = пункты меню ({hrefs} ≠ {want_tiles})")
    over = sl.overflow(page)
    rep.check(over <= 0, f"{tag}: без гор. скролла ({over}px)", code="overflow")
    small = owner.targets(page, "main", owner.PAGE_MIN)
    rep.check(not small, f"{tag}: цели ≥ {owner.PAGE_MIN}px ({small[:3]})", sigs=small or None)
    if has_search and form.count():
        box = form.locator("button[type=submit]").bounding_box()
        rep.check(box and box["height"] >= 44, f"{tag}: кнопка поиска ≥ 44px ({box})")
        rep.check(
            form.locator("input[name=q]").evaluate("e => e.labels.length") == 1,
            f"{tag}: поле поиска подписано",
        )
    rep.check(not page.js_errors, f"{tag}: без ошибок JS ({page.js_errors[:2]})")
    sl.shot(page, OUT, f"404_{name}", full=True)
    if has_search and form.count():
        form.locator("input[name=q]").fill("tee")
        with page.expect_navigation():
            form.locator("button[type=submit]").click()
        url = urlsplit(page.url)
        rep.check("q=tee" in url.query, f"{tag}: поиск ушёл GET-запросом ({page.url})")
        rep.check(page.locator("[data-not-found]").count() == 0, f"{tag}: поиск открыл листинг")
    resp = page.goto(sl.BASE_URL + PREVIEW)
    rep.check(resp.status == 404, f"{tag}: превью анониму → {resp.status}", code="status")
    page.context.close()


def cabinet(browser, rep, w, h, lang, js):
    tag = f"{w} {lang} {'js' if js else 'nojs'} владелец"
    name = f"{w}_{lang}_{'js' if js else 'nojs'}"
    page = sl.open_page(browser, w, h, js=js, lang=lang)
    if not rep.check(sl.login(page, sl.BASE_URL, sl.EMAIL, sl.PASSWORD), f"{tag}: вход"):
        page.context.close()
        return
    resp = page.goto(sl.BASE_URL + AUFBAU)
    sl.settle(page, js, rep)
    rep.check(resp.status == 200, f"{tag}: «Seitenaufbau» → {resp.status}", code="status")
    rep.check(page.locator('select option[value="not_found"]').count() >= 1, f"{tag}: тип в выборе")
    for ref in ("nf-search", "nf-popular"):
        rep.check(page.locator(f'[data-schema-block="{ref}"]').count() >= 1, f"{tag}: строка {ref}")
    over = sl.overflow(page)
    rep.check(over <= 0, f"{tag}: без гор. скролла ({over}px)", code="overflow")
    sl.shot(page, OUT, f"aufbau_{name}")
    resp = page.goto(sl.BASE_URL + AUFBAU + "&block=nf-popular")
    sl.settle(page, js, rep)
    rep.check(resp.status == 200, f"{tag}: окно «Schnellzugriff» → {resp.status}", code="status")
    picked = page.locator("select[name=f_set]")
    rep.check(
        picked.count() == 1 and picked.input_value() == "menu", f"{tag}: набор «Hauptmenü» выбран"
    )
    rep.check(
        page.locator("[data-tile-row]").count() == 0, f"{tag}: у набора меню нет строк плиток"
    )
    over = sl.overflow(page)
    rep.check(over <= 0, f"{tag}: окно без гор. скролла ({over}px)", code="overflow")
    rep.check(not page.js_errors, f"{tag}: без ошибок JS ({page.js_errors[:2]})")
    sl.shot(page, OUT, f"fenster_{name}")
    resp = page.goto(sl.BASE_URL + AUFBAU + "&block=nf-search")
    rep.check(resp.status == 200, f"{tag}: окно «Suche» → {resp.status}", code="status")
    resp = page.goto(sl.BASE_URL + PREVIEW)
    sl.settle(page, js, rep)
    rep.check(resp.status == 200, f"{tag}: превью → {resp.status}", code="status")
    rep.check(page.locator("[data-not-found]").count() == 1, f"{tag}: превью — та же страница")
    page.context.close()


def unknown_host(browser, rep):
    """R1: `Http404` из middleware (хост без бизнеса) приходит в обработчик витрины — он
    обязан отдать прежнюю простую страницу."""
    base = urlsplit(sl.BASE_URL)
    url = f"{base.scheme}://gibt-es-nicht-m5a.{sl.BASE_DOMAIN}:{base.port}/irgendwo/"
    page = sl.open_page(browser, 1440, 900, js=False, lang="de", url=url)
    resp = page.goto(url)
    rep.check(resp.status == 404, f"неизвестный хост → {resp.status}", code="status")
    rep.check(page.locator("[data-not-found]").count() == 0, "неизвестный хост: простая страница")
    rep.check(page.locator("h1").count() == 1, "неизвестный хост: страница нарисована")
    page.context.close()


def main():
    want = menu_urls()[:TILES_MAX]
    rep = sl.Report()
    with sl.launch() as browser:
        unknown_host(browser, rep)
        for w, h, lang, js in sl.matrix():
            visitor(browser, rep, w, h, lang, js, want)
            cabinet(browser, rep, w, h, lang, js)
    rep.finish("fb33 m5a 404")


if __name__ == "__main__":
    main()
