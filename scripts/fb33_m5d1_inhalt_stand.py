"""FB-33 стопка 11 (M5d-1, D1): стенд окна «Inhalt» неподвижных строк страниц-форм (G2)
(1440/390, de/ru, с JS и без; пять демо-китов).

Что проверяет (план `docs/fb33-stack11-plan-2026-11-23.md` §2 D1, §4 D1, §8.2 B5; макет
M5dWindow, вариант A):
- у строки G2 есть окно: с JS — `<dialog>` открыт, без JS — та же часть колонкой в панели
  (`[data-window-part=inhalt]`), полосы вкладок нет (у Gutschein-Formular — одна вкладка с
  плашкой § 312j под «Inhalt»);
- «Dieser Block zeigt …», «🔒 fest» (🔒 `aria-hidden`, «fest» видимо), подсказка про «＋ Block»;
- ссылка «Inhalt bearbeiten: <экран>»: имя = видимый текст, подчёркнута, ≥ 44 px, ведёт на
  экран (ответ < 400); без «⋯», «Platz», «Vorschau»;
- с JS: «Fertig» → фокус на строке (⚙) этого блока;
- нет горизонтальной прокрутки, нет ошибок JS; ru — без немецких подписей новой части.

Сотрудник без права: на стенд-БД демо-китов сотрудников нет — проверка браузером не делается
(«не проверено», замок — `apps/core/tests/test_fb33_m5d1_inhalt.py`).

Запуск (стенд-БД — копия с пятью китами, вход `<kit>@example.com` / `demo-12345678`):
    DB_NAME=<стенд-БД> python manage.py runserver 0.0.0.0:8046 --settings=config.settings.stand --noreload
    STAND_URL=http://ptx.siteadaptor.de:8046 \\
        uv run --no-project --with playwright python scripts/fb33_m5d1_inhalt_stand.py <папка>
Ничего не сохраняет (только GET и «Fertig» окна без правок). Итог: «N ✓, M ✗».
"""

from __future__ import annotations

import sys
from urllib.parse import urlparse

import standlib as sl

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fb33_m5d1_shots"
PORT = urlparse(sl.BASE_URL).port or 80
DEMO_PASSWORD = "demo-12345678"
DLG = "dialog.ui-bwin"
AUFBAU = "/dashboard/site/aufbau/"

#: кит → страницы G2 (код страницы, ref строки) — как их нашёл `scripts/fb33_m5d_inventory.py`
TARGETS = {
    "shop": (("loyalty", "programs"), ("contact", "form")),
    "restaurant-demo": (
        ("booking_slots", "slots"),
        ("event_calendar", "calendar"),
        ("loyalty", "programs"),
        ("contact", "form"),
    ),
    "friseur": (
        ("booking_slots", "slots"),
        ("passes", "plans"),
        ("finder", "wizard"),
        ("loyalty", "programs"),
        ("contact", "form"),
    ),
    "hotel": (("booking_slots", "slots"), ("contact", "form")),
    "retreat": (
        ("event_calendar", "calendar"),
        ("teachers", "teacherlist"),
        ("booking_slots", "slots"),
        ("contact", "form"),
    ),
}
#: начало ссылки по языку (`locale/ru/LC_MESSAGES/django.po`)
LINK_START = {"de": "Inhalt bearbeiten: ", "ru": "Изменить содержимое: "}
GERMAN_IN_RU = ("Inhalt bearbeiten", "Dieser Block zeigt", "Er gehört fest", "Eigene Blöcke")

PART_JS = """(root) => {
  const scope = root === 'dlg' ? document.querySelector('dialog.ui-bwin[open]')
                               : document.querySelector('[data-schema-panel]');
  if (!scope) return {scope: false};
  const part = scope.querySelector('[data-window-part=inhalt]');
  const out = {scope: true, part: !!part};
  if (!part) return out;
  const acc = el => { const c = el.cloneNode(true);
    c.querySelectorAll('[aria-hidden=true]').forEach(n => n.remove());
    return c.textContent.replace(/\\s+/g, ' ').trim(); };
  const r = part.getBoundingClientRect();
  out.visible = r.width > 0 && r.height > 0;
  out.text = part.innerText.replace(/\\s+/g, ' ');
  const lock = [...part.querySelectorAll('span')].find(s => s.textContent.trim() === '🔒');
  out.lockHidden = !!lock && lock.getAttribute('aria-hidden') === 'true';
  const fixed = part.querySelector('[data-inhalt-fixed]');
  out.fixedName = fixed ? acc(fixed) : '';
  const a = part.querySelector('a[data-inhalt-link]');
  out.link = !!a;
  if (a) {
    const ar = a.getBoundingClientRect();
    out.linkH = Math.round(ar.height);
    out.linkVisible = a.innerText.replace(/\\s+/g, ' ').trim();
    out.linkName = a.getAttribute('aria-label') || acc(a);
    out.linkDeco = getComputedStyle(a).textDecorationLine;
    out.href = a.getAttribute('href');
  }
  out.hint = !!part.querySelector('[data-inhalt-hint]');
  out.reason = !!part.querySelector('[data-inhalt-reason]');
  out.tabsNav = !!scope.querySelector('[data-window-tabs], [role=tablist]');
  out.parts = [...scope.querySelectorAll('[data-window-part]')].map(p => p.getAttribute('data-window-part'));
  out.platz = !!scope.querySelector('[data-window-part=platz]');
  out.more = !!scope.querySelector('[data-schema-more]');
  out.preview = !!document.querySelector('template[data-bw-preview], .ui-bwin-pv');
  out.overflow = document.documentElement.scrollWidth - window.innerWidth;
  return out; }"""


def base_of(slug):
    return f"http://{slug}.siteadaptor.de:{PORT}"


def check_part(rep, m, tag, lang):
    if not rep.check(m.get("scope") and m.get("part"), f"{tag}: часть «Inhalt» есть", code="part"):
        return
    rep.check(m["visible"], f"{tag}: часть видна", code="visible")
    rep.check(m["lockHidden"], f"{tag}: 🔒 aria-hidden", code="lock")
    rep.check(bool(m["fixedName"]), f"{tag}: «fest» видимым текстом ({m['fixedName']!r})")
    rep.check(m["hint"], f"{tag}: подсказка про «＋ Block»", code="hint")
    # владелец — ссылка есть; у гутшайнов без «loyalty» её нет (у китов стенда — есть)
    if rep.check(m["link"] and not m["reason"], f"{tag}: ссылка, без «Nur mit Berechtigung»"):
        rep.check(
            m["linkName"] == m["linkVisible"] and m["linkVisible"].startswith(LINK_START[lang]),
            f"{tag}: имя ссылки = видимый текст ({m['linkName']!r})",
            code="name",
        )
        rep.check(m["linkH"] >= 44, f"{tag}: ссылка ≥ 44 px ({m['linkH']})", code="h44")
        rep.check("underline" in m["linkDeco"], f"{tag}: ссылка подчёркнута", code="deco")
    rep.check(not m["platz"] and not m["more"], f"{tag}: без «Platz» и «⋯»", code="noplatz")
    rep.check(not m["preview"], f"{tag}: без «Vorschau»", code="nopreview")
    if m["parts"] == ["inhalt"]:
        rep.check(not m["tabsNav"], f"{tag}: одна вкладка — полосы нет", code="tabs")
    else:
        rep.check(m["parts"] == ["inhalt", "pinned"], f"{tag}: части {m['parts']}", code="parts")
    rep.check(m["overflow"] <= 0, f"{tag}: без гор. скролла ({m['overflow']}px)", code="overflow")
    if lang == "ru":
        leaked = [g for g in GERMAN_IN_RU if g in m["text"]]
        rep.check(not leaked, f"{tag}: ru без немецкого ({leaked})", code="german")


def run_page(rep, page, slug, code, ref, w, lang, js, linked):
    tag = f"{w} {lang} {'js' if js else 'nojs'} {slug}:{code}/{ref}"
    url = f"{base_of(slug)}{AUFBAU}?seite={code}&block={ref}"
    resp = page.goto(url)
    sl.settle(page, js, rep)
    if not rep.check(resp.status < 400, f"{tag}: ответ {resp.status}", code="status"):
        return
    if js:
        try:
            page.wait_for_selector(f"{DLG}[open]", timeout=5000)
            opened = True
        except Exception:  # noqa: BLE001 — таймаут Playwright
            opened = False
        if not rep.check(opened, f"{tag}: окно-диалог открыто", code="dialog"):
            return
        sl.settle(page, js, rep)
        m = page.evaluate(PART_JS, "dlg")
    else:
        m = page.evaluate(PART_JS, "panel")
    check_part(rep, m, tag, lang)
    sl.shot(page, OUT, f"inhalt_{slug}_{code}_{w}_{lang}_{'js' if js else 'nojs'}")
    if js:
        rep.check(not page.js_errors, f"{tag}: без ошибок JS ({page.js_errors[:2]})", code="jserr")
        # «Fertig» → фокус на строке (⚙) блока
        # кнопка «Fertig» окна — в `[data-window-actions]` (верхняя — только на телефоне)
        done = page.locator(f"{DLG}[open] [data-window-actions] button[value=window_done]")
        try:
            done.click()
            page.wait_for_url(lambda u: "block=" not in u, timeout=20000)
            page.wait_for_load_state()
            sl.settle(page, js, rep)
            page.wait_for_function(
                "(r) => { const a = document.activeElement;"
                " const b = a && a.closest('[data-schema-block]');"
                " return !!b && b.getAttribute('data-schema-block') === r; }",
                arg=ref,
                timeout=3000,
            )
        except Exception:  # noqa: BLE001 — таймаут виден строкой ниже (фокус как есть)
            pass
        try:
            focus = page.evaluate(
                "() => { const a = document.activeElement;"
                " const b = a && a.closest('[data-schema-block]');"
                " return b ? b.getAttribute('data-schema-block') : (a ? a.tagName : ''); }"
            )
        except Exception as exc:  # noqa: BLE001 — сбой клика виден строкой
            focus = f"ошибка: {type(exc).__name__}"
        rep.check(focus == ref, f"{tag}: «Fertig» → фокус на строке ({focus!r})", code="focus")
    if linked and m.get("href"):
        resp = page.goto(base_of(slug) + m["href"])
        rep.check(resp.status < 400, f"{tag}: ссылка ведёт на экран ({resp.status})", code="target")


def main():
    rep = sl.Report(quiet=True)
    with sl.launch() as browser:
        for w, h, lang, js in sl.matrix():
            for slug, pages in TARGETS.items():
                page = sl.open_page(browser, w, h, js=js, lang=lang, url=base_of(slug))
                tag = f"{w} {lang} {'js' if js else 'nojs'} {slug}"
                ok = sl.login(page, base_of(slug), f"{slug}@example.com", DEMO_PASSWORD)
                if rep.check(ok, f"{tag}: вход", code="login"):
                    for code, ref in pages:
                        linked = js and w == 1440 and lang == "de"
                        run_page(rep, page, slug, code, ref, w, lang, js, linked)
                page.context.close()
    rep.note("сотрудник без права: на стенде нет сотрудника — не проверено (замок pytest)")
    rep.finish()


if __name__ == "__main__":
    main()
