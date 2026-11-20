"""FB-33 M3-3d: стенд «Von einer Seite ↔ Eigener Text» в окне блока (1440 и 390, с JS и без).

Смена вида туда-обратно: свой текст и выбранная страница помнятся, «Abbrechen» возвращает
вид и текст на момент открытия окна.

    uv run python scripts/text_pages_stand.py --setup        # один раз (тенант ptx)
    uv run python scripts/fb33_m3_3d_text_source_stand.py --setup   # блок и страница
    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run --no-project --with playwright python scripts/fb33_m3_3d_text_source_stand.py <папка>
Сервер на другом порту — `STAND_URL=http://ptx.siteadaptor.de:<порт>`. Итог: «N ✓, 0 ✗».
Chromium — /opt/pw-browsers/chromium (playwright install не запускать). Не входит в CI.
"""

import os
import subprocess
import sys

U = os.environ.get("STAND_URL", "http://ptx.siteadaptor.de:8000")
REF = "m3d1"
TITLE, BODY = "Eigener Titel M3d", "Eigener Text M3d"

SETUP = f"""
from django_tenants.utils import schema_context
from apps.tenants.models import Tenant
from apps.tenants import siteconfig
t = Tenant.objects.get(schema_name="ptx")
with schema_context("ptx"):
    from apps.core.models import ContentPage
    page, _ = ContentPage.objects.update_or_create(slug="geschichte-m3d",
        defaults={{"title": "Geschichte M3d", "body": "<p>Seitentext M3d</p>", "is_published": True}})
cfg = siteconfig.normalize(t.site_config)
rows = [r for r in cfg["sections"] if r.get("id") != {REF!r}]
rows.append({{"key": "text", "id": {REF!r}, "enabled": True,
    "data": {{"title": {TITLE!r}, "body": {BODY!r}}}}})
cfg["sections"] = rows
t.site_config = siteconfig.normalize(cfg)
t.save(update_fields=["site_config"])
print("PAGE", page.pk)
"""

ok, fail = 0, []


def check(c, label):
    global ok
    ok += bool(c)
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fail.append(label)


def page_pk():
    out = subprocess.run(
        [sys.executable, "manage.py", "shell", "--settings=config.settings.stand", "-c", SETUP],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return next(line.split()[1] for line in out.splitlines() if line.startswith("PAGE"))


def run(out_dir):  # noqa: PLR0915 — линейный сценарий стенда
    from playwright.sync_api import sync_playwright

    def open_tab(pg, tab):
        # внутри открытого окна — по вкладке (токен открытия тот же: «Abbrechen» вернёт к
        # моменту ПЕРВОГО открытия); окно закрыто — открыть ссылкой
        link = pg.locator(f"[data-window-tab-link={tab}]")
        if f"block={REF}" in pg.url and link.count():
            if link.first.get_attribute("aria-selected") != "true":
                link.first.click()
                pg.wait_for_load_state()
            return
        pg.goto(f"{U}/dashboard/site/aufbau/?seite=home&block={REF}&tab={tab}")
        pg.wait_for_load_state()

    def switch(pg, js, view):
        open_tab(pg, "wie")
        form = pg.locator("form[data-schema-switch]")
        # стопка FB-33: смена вида — плитки-кнопки (M3-3a), не выпадающий список
        form.locator(f"button[name=value][value={view}]").click()
        pg.wait_for_load_state()
        if js:
            pg.wait_for_function(
                "!+document.documentElement.getAttribute('data-schema-busy')", timeout=15000
            )

    def current_view(pg):
        open_tab(pg, "wie")
        on = pg.locator("form[data-schema-switch] button[name=value][aria-pressed=true]")
        return on.first.get_attribute("value") if on.count() else ""

    def field(pg, name):
        for tab in ("texte", "was", "wie"):
            if f"block={REF}" in pg.url and not pg.locator(f"[data-window-tab-link={tab}]").count():
                continue  # вкладки у этого вида нет
            open_tab(pg, tab)
            loc = pg.locator(f"[data-schema-fields] [name=f_{name}]")
            if loc.count() and loc.first.is_visible():
                return loc.first
        return None

    with sync_playwright() as p:
        b = p.chromium.launch(
            executable_path="/opt/pw-browsers/chromium",
            args=["--host-resolver-rules=MAP *.siteadaptor.de 127.0.0.1"],
        )
        pk = os.environ["M3D_PAGE"]
        for js in (True, False):
            for w, h in ((1440, 900), (390, 844)):
                tag = f"{w}{'' if js else '_nojs'}"
                print(f"— {tag}")
                ctx = b.new_context(viewport={"width": w, "height": h}, java_script_enabled=js)
                pg = ctx.new_page()
                pg.goto(U + "/accounts/login/")
                pg.fill("input[name=login]", "owner@ptx.test")
                pg.fill("input[name=password]", "Stand-Passwort-123")
                pg.click("button[type=submit]")
                pg.wait_for_load_state()
                opts = pg.goto(f"{U}/dashboard/site/aufbau/?seite=home&block={REF}&tab=wie")
                check(opts.ok, f"{tag}: окно блока открыто")
                values = pg.locator("form[data-schema-switch] button[name=value]")
                got = sorted(values.evaluate_all("bs => bs.map(b => b.value)"))
                check(got == ["image_text", "text", "textpage"], f"{tag}: три вида ({got})")
                switch(pg, js, "textpage")
                check(f"block={REF}" in pg.url, f"{tag}: окно осталось открытым после смены")
                check(current_view(pg) == "textpage", f"{tag}: вид — «Von einer Seite»")
                pick = field(pg, "page")
                check(pick is not None, f"{tag}: у «Von einer Seite» — выбор страницы")
                if pick is not None:
                    pick.select_option(pk)
                    if js:
                        pick.evaluate("el => el.blur()")
                        pg.wait_for_timeout(300)
                    form = pick.locator("xpath=ancestor::form[1]")
                    apply = form.locator("[data-schema-apply], button[value=update]")
                    if apply.count() and apply.first.is_visible():
                        apply.first.click()
                        pg.wait_for_load_state()
                    if js:
                        pg.wait_for_function(
                            "!+document.documentElement.getAttribute('data-schema-busy')",
                            timeout=15000,
                        )
                pg.screenshot(path=f"{out_dir}/m33d_textpage_{tag}.png")
                over = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                check(over <= 0, f"{tag}: без горизонтального вылета ({over})")
                switch(pg, js, "text")
                title = field(pg, "title")
                check(
                    title is not None and title.input_value() == TITLE,
                    f"{tag}: «Eigener Text» — свой заголовок на месте",
                )
                pg.screenshot(path=f"{out_dir}/m33d_text_{tag}.png")
                switch(pg, js, "textpage")
                pick = field(pg, "page")
                check(
                    pick is not None and pick.input_value() == pk,
                    f"{tag}: снова «Von einer Seite» — выбранная страница помнится",
                )
                # «Abbrechen»: вид и текст — как при открытии окна
                open_tab(pg, "wie")
                pg.click("[data-window-actions] button[value=revert]")
                pg.wait_for_load_state()
                if js:
                    pg.wait_for_url(lambda u: "block=" not in u, timeout=15000)
                check("block=" not in pg.url, f"{tag}: «Abbrechen» закрыл окно")
                check(current_view(pg) == "text", f"{tag}: «Abbrechen» вернул вид «Nur Text»")
                title = field(pg, "title")
                check(
                    title is not None and title.input_value() == TITLE,
                    f"{tag}: «Abbrechen» — текст на месте",
                )
                ctx.close()
        b.close()


if __name__ == "__main__":
    if "--setup" in sys.argv:
        print(page_pk())
        sys.exit(0)
    run(sys.argv[1])
    print(f"{ok} ✓, {len(fail)} ✗")
    sys.exit(1 if fail else 0)
