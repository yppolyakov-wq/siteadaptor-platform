"""M21.11: стенд фото в редакторе страниц — ширина за угол (шаг 5 %), поле «Breite in %»,
кадрирование (новый файл), витрина и телефон.

    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run python scripts/text_pages_stand.py --setup     # один раз (тенант ptx)
    uv run --with playwright==1.55.0 python scripts/editor_photo_stand.py
"""

from __future__ import annotations

import io
import re
import tempfile

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"
SLUG = "ptx"
PASSWORD = "Stand-Passwort-123"


def _png() -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (800, 400), (60, 120, 200)).save(buf, "PNG")
    f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    f.write(buf.getvalue())
    f.close()
    return f.name


def main():  # noqa: PLR0915 — один линейный сценарий стенда
    from playwright.sync_api import sync_playwright

    ok, fail = 0, []

    def check(cond, label):
        nonlocal ok
        ok += bool(cond)
        if not cond:
            fail.append(label)
        print(("  ✓ " if cond else "  ✗ ") + label)

    url = f"http://{SLUG}.{BASE}:8000"
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
        )
        page = browser.new_context(
            viewport={"width": 1440, "height": 900}, locale="de-DE"
        ).new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url + "/accounts/login/")
        page.fill("input[name=login]", f"owner@{SLUG}.test")
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_load_state()
        page.goto(url + "/dashboard/site/seiten/neu/")
        page.fill("input[name=title]", "Foto Stand")
        page.fill("input[name=slug]", "foto-stand")
        area = page.locator(".rte-area")
        area.click()
        page.keyboard.type("Text vor dem Bild. " * 20)
        with page.expect_file_chooser() as fc:
            page.click("[data-rte-cmd=insertImage]")
        fc.value.set_files(_png())
        page.wait_for_selector(".rte-pop")
        pop = page.locator(".rte-pop")
        pop.locator("input[type=number]").fill("40")
        pop.locator("input[type=number]").press("Tab")
        check(area.locator("figure.sf-w-40").count() == 1, "поле «Breite»: 40 %")
        pop.locator("input[id$='-alt']").fill("Blaues Bild")
        page.keyboard.press("Escape")

        print("Ecke ziehen")
        popup_before = page.locator(".rte-pop").count()
        fig = area.locator("figure").first
        fig.click()
        page.keyboard.press("Escape")
        handle = fig.locator(".rte-resize")
        hb = handle.bounding_box()
        check(hb is not None, "ручка на углу видна")
        page.mouse.move(hb["x"] + 6, hb["y"] + 6)
        page.mouse.down()
        page.mouse.move(hb["x"] + 200, hb["y"] + 6, steps=8)
        badge = page.evaluate(
            "() => document.querySelector('.rte-area figure').getAttribute('data-rte-w')"
        )
        page.mouse.up()
        cls = fig.get_attribute("class")
        m = re.search(r"sf-w-(\d+)", cls or "")
        check(
            m and int(m.group(1)) > 40 and int(m.group(1)) % 5 == 0, f"тянем вправо → шире ({cls})"
        )
        check(bool(badge) and "%" in badge, f"значок ширины во время ({badge})")
        check(fig.get_attribute("data-rte-w") is None, "значок убран после")
        page.wait_for_timeout(100)
        check(
            page.locator(".rte-pop").count() == popup_before,
            "перетаскивание не открывает окно фото",
        )

        print("Zuschneiden")
        fig.click()
        page.wait_for_selector(".rte-pop")
        old_src = fig.locator("img").get_attribute("src")
        page.locator(".rte-pop button:has-text('Zuschneiden')").click()
        dlg = page.locator("dialog.rte-crop")
        check(dlg.is_visible(), "окно кадрирования")
        dlg.locator("button:has-text('1:1')").click()
        box = dlg.locator(".rte-crop-box")
        bb = box.bounding_box()
        check(abs(bb["width"] - bb["height"]) < 4, "1:1 даёт квадрат")
        x0 = box.bounding_box()["x"]
        dlg.locator("button[aria-label='Nach rechts']").click()
        check(box.bounding_box()["x"] > x0, "кнопка «→» сдвигает рамку (без перетаскивания)")
        page.wait_for_timeout(400)
        check("Prozent" in dlg.locator("[role=status]").inner_text(), "положение объявлено")
        box.focus()
        page.keyboard.press("ArrowRight")
        dlg.locator("button.ui-btn-primary").click()
        page.wait_for_function(
            "(s) => document.querySelector('.rte-area figure img').getAttribute('src') !== s",
            arg=old_src,
        )
        check(not dlg.count() or not dlg.is_visible(), "окно закрылось, картинка заменена")
        page.click("button:has-text('Speichern')")
        page.wait_for_load_state()

        print("Витрина")
        page.goto(url + "/foto-stand/")
        f2 = page.locator("[data-page-body] figure")
        w = page.evaluate(
            "() => document.querySelector('[data-page-body] figure').getBoundingClientRect().width"
        )
        body = page.evaluate(
            "() => document.querySelector('[data-page-body]').getBoundingClientRect().width"
        )
        pct = round(w / body * 100)
        check(f2.count() == 1 and 40 < pct < 100, f"ширина на витрине {pct} %")
        size = page.evaluate(
            "() => { const i = document.querySelector('[data-page-body] img'); return [i.naturalWidth, i.naturalHeight]; }"
        )
        check(abs(size[0] - size[1]) <= 2, f"кадрирование 1:1 на витрине {size}")
        page.set_viewport_size({"width": 390, "height": 800})
        w2 = page.evaluate(
            "() => document.querySelector('[data-page-body] figure').getBoundingClientRect().width"
        )
        b2 = page.evaluate(
            "() => document.querySelector('[data-page-body]').getBoundingClientRect().width"
        )
        check(w2 >= b2 * 0.95, "на телефоне фото во всю ширину")
        check(not errors, "без JS-ошибок: " + "; ".join(errors[:3]))
        browser.close()
    print(f"\n{ok}/{ok + len(fail)}")
    raise SystemExit(1 if fail else 0)


if __name__ == "__main__":
    main()
