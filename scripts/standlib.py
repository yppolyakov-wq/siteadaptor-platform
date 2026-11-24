"""T-13.4: общий каркас Playwright-стендов (`scripts/*_stand.py`).

Каждый стенд раньше заново писал запуск Chromium, вход, счётчик ✓/✗ и размеры экранов — и
заново наступал на те же грабли (кабинет по-английски, вечное ожидание бесконечной анимации,
`playwright install`). Здесь это одно место: `Report`, `SIZES`/`LANGS`/`JS_MODES`, `launch`,
`open_page`, `login`, `settle`, `overflow`, `shot`, `matrix`. Доступность (T-14.5) —
`a11y_check` на каждой открытой странице: цели касания, фокус внутри `aria-hidden`, имена
элементов управления, контраст текста; возврат фокуса после закрытия окна — `focus_returns`.

Правило: **новые стенды — только через каркас; старые переносим при следующей правке**
(замок — `apps/core/tests/test_standlib.py`, список `LEGACY_STANDS` можно только сокращать).

Запуск стенда (тенант `ptx` ставит `scripts/text_pages_stand.py --setup`, один раз):

    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand --noreload
    uv run --no-project --with playwright python scripts/<имя>_stand.py <папка-скриншотов>
    uv run --no-project --with playwright python scripts/standlib.py --selftest

Сервер на другом порту или хосте — `STAND_URL=http://ptx.siteadaptor.de:<порт>`. Chromium —
`/opt/pw-browsers/chromium` (`playwright install` не запускать). В CI стенды не входят (там нет
браузера); `--selftest` проверяет сам каркас без сервера и БД — гонять после правки каркаса.

Новый стенд (лежит в `scripts/`, поэтому `import standlib` работает без установки):

    import sys

    import standlib as sl

    rep = sl.Report()
    with sl.launch() as browser:
        for w, h, lang, js in sl.matrix():
            page = sl.open_page(browser, w, h, js=js, lang=lang)
            tag = f"{w} {lang} {'js' if js else 'nojs'}"
            if rep.check(sl.login(page, sl.BASE_URL, sl.EMAIL, sl.PASSWORD), f"{tag}: вход"):
                resp = page.goto(sl.BASE_URL + "/dashboard/site/aufbau/")
                sl.settle(page, js, rep)
                rep.check(resp.status < 400, f"{tag}: ответ {resp.status}", code="status")
                over = sl.overflow(page)
                rep.check(over <= 0, f"{tag}: без гор. скролла ({over}px)", code="overflow")
                rep.check(not page.js_errors, f"{tag}: без ошибок JS ({page.js_errors[:2]})")
                sl.a11y_check(rep, page, tag, minimum=44)  # кабинет; витрина — 24
                sl.shot(page, sys.argv[1], f"aufbau_{w}_{lang}_{'js' if js else 'nojs'}")
            page.context.close()
    rep.finish()

Проверки вести по data-атрибутам, а не по тексту; после клика ждать результат
(`wait_for_selector`), а не загрузку. Остальные грабли — скилл `sa-stand`.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import sys
import tempfile
from itertools import product

# playwright импортируется лениво, внутри `launch`: замок каркаса (`test_standlib.py`) и CI
# грузят модуль там, где пакета нет.

CHROME = "/opt/pw-browsers/chromium"
BASE_DOMAIN = "siteadaptor.de"
#: адрес тенанта стенда; другой порт/хост — переменной `STAND_URL`
BASE_URL = os.environ.get("STAND_URL", f"http://ptx.{BASE_DOMAIN}:8000").rstrip("/")
#: владелец тенанта `ptx` (`scripts/text_pages_stand.py --setup`)
EMAIL = "owner@ptx.test"
PASSWORD = "Stand-Passwort-123"
#: приёмка вёрстки: компьютер и телефон
SIZES = ((1440, 900), (390, 844))
LANGS = ("de", "ru")
#: сначала без JS (обязательный проход), затем с JS
JS_MODES = (False, True)
LANGUAGE_COOKIE = "django_language"  # settings.LANGUAGE_COOKIE_NAME (умолчание Django)
LOGIN_PATH = "/accounts/login/"


class Report:
    """Счёт ✓/✗. Повтор того же дефекта (подпись `sigs`) печатается один раз, в сводке —
    с числом; `code` — код проверки, давшей ✗ (замки сверяют коды, не текст)."""

    def __init__(self, quiet: bool = False):
        self.quiet = quiet  # большой обход: ✓ не печатать
        self.ok = 0
        self.fail: list[str] = []
        self.sigs: dict[str, list] = {}  # подпись дефекта → [число, первый пример]
        self.notes: dict[str, int] = {}
        self.codes: list[str] = []

    def check(self, cond, label, *, sigs=None, code="other", quiet=None) -> bool:
        """`sigs` — подпись дефекта (строка или список); без неё подписью служит `label`."""
        if cond:
            self.ok += 1
            if not (self.quiet if quiet is None else quiet):
                print("  ✓ " + label)
            return True
        self.fail.append(label)
        self.codes.append(code)
        if sigs is None:
            sigs = [label]
        elif isinstance(sigs, str):
            sigs = [sigs]
        new = False
        for sig in sigs:
            seen = self.sigs.setdefault(sig, [0, label])
            seen[0] += 1
            new = new or seen[0] == 1
        if new:
            print("  ✗ " + label)
        return False

    def note(self, sig) -> None:
        """Наблюдение (не ✗): печатается один раз, в сводке — с числом."""
        self.notes[sig] = self.notes.get(sig, 0) + 1
        if self.notes[sig] == 1:
            print("  · " + sig)

    @property
    def exit_code(self) -> int:
        return 1 if self.fail else 0

    def summary(self, title: str = "") -> str:
        """Печатает наблюдения, сводку дефектов и итоговую строку; возвращает итоговую строку."""
        if self.notes:
            print(f"\nнаблюдения ({len(self.notes)}):")
            for sig, n in sorted(self.notes.items(), key=lambda kv: -kv[1]):
                print(f"  ×{n:<4} {sig}")
        if self.sigs:
            print(f"\nсводка дефектов ({len(self.sigs)} разных):")
            for sig, (n, first) in sorted(self.sigs.items(), key=lambda kv: -kv[1][0]):
                print(f"  ×{n:<4} {sig}")
                if first != sig:
                    print(f"         напр.: {first[:220]}")
        line = f"{title + ': ' if title else ''}{self.ok} ✓, {len(self.fail)} ✗"
        print("\n" + line)
        return line

    def finish(self, title: str = "") -> None:
        """Сводка и выход: есть ✗ → код 1."""
        self.summary(title)
        sys.exit(self.exit_code)


def matrix(sizes=SIZES, langs=LANGS, js_modes=JS_MODES):
    """Сочетания обхода `(ширина, высота, язык, js)`: режим JS — внешний цикл (проход)."""
    for js, (w, h), lang in product(js_modes, sizes, langs):
        yield w, h, lang, js


@contextlib.contextmanager
def launch(**kwargs):
    """Chromium стенда: `/opt/pw-browsers/chromium`, если он есть (версия браузера там не
    совпадает с пакетом — путь задаём сами; `playwright install` не запускать). Поддомены
    `*.siteadaptor.de` ведут на 127.0.0.1."""
    from playwright.sync_api import sync_playwright

    if os.path.exists(CHROME):
        kwargs.setdefault("executable_path", CHROME)
    kwargs.setdefault("args", [f"--host-resolver-rules=MAP *.{BASE_DOMAIN} 127.0.0.1"])
    with sync_playwright() as p:
        browser = p.chromium.launch(**kwargs)
        try:
            yield browser
        finally:
            browser.close()


def open_page(browser, width, height, *, js=True, lang="de", url=None):
    """Страница в своём контексте: размер, JS вкл/выкл, язык. Язык — и `locale`, и кука
    `django_language` (кабинет на стенде иначе открывается по-английски). Ошибки страницы
    копятся в `page.js_errors`. Закрывать — `page.context.close()`."""
    ctx = browser.new_context(
        viewport={"width": width, "height": height},
        locale=f"{lang}-DE",
        java_script_enabled=js,
        device_scale_factor=1,
    )
    ctx.add_cookies([{"name": LANGUAGE_COOKIE, "value": lang, "url": url or BASE_URL}])
    page = ctx.new_page()
    page.js_errors = []
    page.on("pageerror", lambda e: page.js_errors.append(str(e)[:160]))
    return page


def login(page, url, email, password) -> bool:
    """Вход владельца (allauth); `True` — ушли со страницы входа."""
    page.goto(url.rstrip("/") + LOGIN_PATH)
    page.fill("input[name=login]", email)
    page.fill("input[name=password]", password)
    with page.expect_navigation():  # ответ на POST, а не «загрузка» прежней страницы
        page.click("button[type=submit]")
    page.wait_for_load_state()
    return LOGIN_PATH not in page.url


#: нет идущих КОНЕЧНЫХ анимаций (бесконечные — слайдер, бегущая строка — не ждём)
_NO_FINITE_ANIMATIONS = (
    "!document.getAnimations().filter(a => a.effect && "
    "a.effect.getTiming().iterations !== Infinity && a.playState === 'running').length"
)


def settle(page, js, rep: Report | None = None) -> bool:
    """С JS: страница загружена и закончились конечные анимации (открытие окна — 160 мс).
    Не `networkidle`: кадр предпросмотра держит сеть. Таймаут — не сбой стенда, а наблюдение
    (`rep.note`), замер идёт по текущему состоянию; `False` — не дождались."""
    if not js:
        return True
    try:
        page.wait_for_load_state("load", timeout=10000)
        page.wait_for_function(_NO_FINITE_ANIMATIONS, timeout=5000)
    except Exception:  # noqa: BLE001 — таймаут Playwright; пакет импортируется лениво
        if rep is not None:
            rep.note("settle timeout: страница не успокоилась (load/анимации) — замер как есть")
        return False
    return True


def overflow(page) -> int:
    """Горизонтальный скролл страницы в px (≤ 0 — нет). Работает и без JS на странице."""
    return page.evaluate("document.documentElement.scrollWidth - window.innerWidth")


def shot(page, out_dir, name, *, full=False) -> str:
    """Скриншот `<out_dir>/<name>.png`; папка создаётся."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name if name.endswith(".png") else name + ".png")
    page.screenshot(path=path, full_page=full)
    return path


# --- доступность (T-14.5): механически проверяемая часть, на любой открытой странице ------

#: цели касания: витрина — WCAG 2.5.8 (обе стороны, с исключениями «Inline» и «Spacing»);
#: кабинет и окно блока — контракт M3-2 (только высота, без исключений)
TARGET_MIN = 24
WINDOW_TARGET_MIN = 44
#: контраст текста (WCAG 1.4.3): обычный и крупный (≥ 24 px или ≥ 18.66 px жирный)
CONTRAST_MIN = 4.5
CONTRAST_LARGE = 3.0
#: коды проверок `a11y_check` (замки сверяют коды, не текст)
A11Y_CODES = ("a11y-target", "a11y-hidden-focus", "a11y-name", "a11y-contrast")

#: одна функция на все проверки: `[вид, область, параметры]` → список (или `null` — области нет).
#: Считаются только видимые элементы. Работает и на странице с выключенным JS.
_A11Y_JS = r"""([kind, scope, opt]) => {
  const root = document.querySelector(scope || 'body');
  if (!root) return null;
  const all = sel => [...root.querySelectorAll(sel)];
  const style = e => getComputedStyle(e);
  const shown = e => e.getClientRects().length > 0 && style(e).visibility !== 'hidden';
  const srOnly = e => {
    if (e.closest('.sr-only')) return true;
    const r = e.getBoundingClientRect();
    return r.width <= 1 && r.height <= 1;
  };
  const squash = s => (s || '').trim().replace(/\s+/g, ' ');
  const desc = e => {
    const cls = squash(e.getAttribute('class')).split(' ').filter(Boolean).slice(0, 2);
    const text = squash(e.textContent) || squash(e.getAttribute('aria-label')) ||
      e.getAttribute('name') || e.getAttribute('type') || '';
    return e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + cls.map(c => '.' + c).join('') +
      ' «' + text.slice(0, 24) + '»';
  };

  if (kind === 'targets') {
    const min = opt.min, spacing = opt.spacing;
    const sel = 'a[href],button,summary,select,input:not([type=hidden]),textarea,' +
      '[role=button],[role=tab],[role=switch],[role=checkbox]';
    const seen = new Set(), list = [];
    for (let e of all(sel)) {
      if (!shown(e) || e.disabled) continue;
      const cs = style(e);
      if (cs.display === 'contents') continue;
      if (e.closest('[hidden],[aria-hidden="true"],[inert]') || srOnly(e)) continue;
      // ссылка внутри строки текста — исключение 2.5.8 «Inline»: у родителя есть свой текст
      if (e.tagName === 'A' && cs.display === 'inline' && e.parentElement &&
          e.parentElement.textContent.trim().length > e.textContent.trim().length) continue;
      if (e.type === 'radio' || e.type === 'checkbox') e = e.closest('label') || e;
      if (seen.has(e)) continue;
      seen.add(e);
      const r = e.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      // окно (44) — только высота; экран и витрина (24, 2.5.8) — обе стороны
      list.push({e, r, small: r.height < min || (spacing && r.width < min),
        cx: r.left + r.width / 2, cy: r.top + r.height / 2});
    }
    // 2.5.8 «Spacing»: мелкая цель допустима, если круг Ø24 вокруг её центра не задевает
    // другие цели и круги других мелких целей (только для порога 24)
    const dist = (x, y, r) => Math.hypot(Math.max(r.left - x, 0, x - r.right),
                                         Math.max(r.top - y, 0, y - r.bottom));
    const bad = [];
    for (const t of list) {
      if (!t.small) continue;
      if (spacing && !list.some(o => o !== t && !o.e.contains(t.e) && !t.e.contains(o.e) &&
          (dist(t.cx, t.cy, o.r) < 12 || (o.small && Math.hypot(o.cx - t.cx, o.cy - t.cy) < 24))))
        continue;
      bad.push(desc(t.e) + ': цель ' + t.r.width.toFixed(0) + '×' + t.r.height.toFixed(0) +
        ' < ' + min);
    }
    return bad;
  }

  if (kind === 'hidden') {
    const sel = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[tabindex],' +
      '[contenteditable=""],[contenteditable=true]';
    const bad = [];
    for (const e of all(sel)) {
      const host = e.closest('[aria-hidden="true"]');
      if (!host || !shown(e) || e.disabled) continue;
      if (e.closest('[inert],fieldset[disabled]')) continue;
      if (parseInt(e.getAttribute('tabindex'), 10) < 0) continue;
      bad.push(desc(e) + ': в порядке фокуса, но aria-hidden' +
        (host === e ? '' : ' у предка ' + host.tagName.toLowerCase() +
          (host.id ? '#' + host.id : '')));
    }
    return bad;
  }

  if (kind === 'names') {
    const gone = e => { const cs = style(e); return cs.display === 'none' ||
      cs.visibility === 'hidden'; };
    const text = n => {
      if (n.nodeType === 3) return n.nodeValue;
      if (n.nodeType !== 1) return '';
      if (/^(SELECT|TEXTAREA|OPTION|SCRIPT|STYLE)$/.test(n.tagName)) return '';
      if (n.getAttribute('aria-hidden') === 'true' || gone(n)) return '';
      if (squash(n.getAttribute('aria-label'))) return n.getAttribute('aria-label');
      if (n.tagName === 'IMG') return n.getAttribute('alt') || '';
      if (n.tagName.toLowerCase() === 'svg') {
        const t = n.querySelector('title');
        return t ? t.textContent : '';
      }
      let s = '';
      for (const c of n.childNodes) s += ' ' + text(c);
      return s;
    };
    const byIds = ids => squash(ids).split(' ').filter(Boolean)
      .map(id => document.getElementById(id)).map(n => (n ? n.textContent : '')).join(' ');
    const why = e => {
      if (squash(byIds(e.getAttribute('aria-labelledby')))) return '';
      if (squash(e.getAttribute('aria-label')) || squash(e.getAttribute('title'))) return '';
      const tag = e.tagName;
      if (tag === 'IFRAME') return 'iframe без title';
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') {
        if ([...(e.labels || [])].some(l => squash(text(l)))) return '';
        const t = (e.getAttribute('type') || 'text').toLowerCase();
        if (t === 'submit' || t === 'reset') return '';
        if (t === 'button' && squash(e.value)) return '';
        if (t === 'image' && squash(e.getAttribute('alt'))) return '';
        return 'поле без подписи' + (e.getAttribute('placeholder') ? ' (только placeholder)' : '');
      }
      return squash(text(e)) ? '' : 'нет доступного имени';
    };
    const sel = 'button,a[href],input:not([type=hidden]),select,textarea,iframe,' +
      '[role=button],[role=tab],[role=switch],[role=checkbox]';
    const bad = [];
    for (const e of all(sel)) {
      if (!shown(e) || e.closest('[aria-hidden="true"],[inert]')) continue;
      const w = why(e);
      if (w) bad.push(desc(e) + ': ' + w);
    }
    return bad;
  }

  if (kind === 'contrast') {
    const parse = c => {
      const m = c.match(/^(rgba?|color)\(([^)]+)\)$/);
      if (!m) return null;
      const srgb = m[1] === 'color';
      if (srgb && !/^srgb\s/.test(m[2])) return null;
      const p = m[2].replace(/^srgb\s+/, '').split(/[\s,\/]+/).filter(Boolean).map(parseFloat);
      if (p.length < 3 || p.some(isNaN)) return null;
      const k = srgb ? 255 : 1;
      return [p[0] * k, p[1] * k, p[2] * k, p.length > 3 ? p[3] : 1];
    };
    const inView = r => r.left + r.width / 2 >= 0 && r.left + r.width / 2 < innerWidth &&
      r.top + r.height / 2 >= 0 && r.top + r.height / 2 < innerHeight;
    const items = [], skipped = [], seen = new Set();
    const range = document.createRange();
    const rectOf = n => {
      range.selectNodeContents(n);
      return [...range.getClientRects()].find(x => x.width > 1 && x.height > 1);
    };
    const sx = scrollX, sy = scrollY;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (!/[\p{L}\p{N}]/u.test(n.nodeValue)) continue;
      const e = n.parentElement;
      if (!e || seen.has(e)) continue;
      if (/^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE|OPTION|TITLE)$/.test(e.tagName)) continue;
      if (e.closest('svg')) continue;
      let r = rectOf(n);
      if (!r) continue;
      seen.add(e);
      if (!shown(e) || srOnly(e)) continue;
      if (e.closest(':disabled,[aria-disabled="true"],[inert]')) continue;
      const cs = style(e);
      let fg = parse(cs.color), why = '', bg = null, bgEl = null, op = 1;
      if (!fg) why = 'цвет текста не разобран';
      else if (fg[3] === 0 || cs.webkitTextFillColor !== cs.color)
        why = 'текст залит не цветом (прозрачный или градиент)';
      for (let a = e; a && a.nodeType === 1; a = a.parentElement) {
        const s = style(a);
        op *= parseFloat(s.opacity);
        if (bg || why) continue;
        if (s.backgroundImage !== 'none') { why = 'над картинкой или градиентом'; continue; }
        const c = parse(s.backgroundColor);
        if (!c) { why = 'цвет фона не разобран'; continue; }
        if (c[3] >= 1) { bg = c; bgEl = a; continue; }
        if (c[3] > 0) { why = 'полупрозрачный фон'; continue; }
        if (s.position === 'absolute' || s.position === 'fixed')
          why = 'слой поверх страницы без своего фона';
      }
      if (op === 0) continue;
      if (!why && op < 1) why = 'полупрозрачный элемент (opacity)';
      if (!why) {
        // что на самом деле лежит под текстом: соседний слой (фото под подписью) предки не знают
        if (!inView(r)) {
          scrollTo({left: sx, top: sy + r.top - innerHeight / 2, behavior: 'instant'});
          r = rectOf(n) || r;
        }
        if (!inView(r)) why = 'за краем экрана — слой под текстом не проверить';
        else {
          const stack = document.elementsFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          const i = stack.indexOf(e);
          if (i < 0) { scrollTo({left: sx, top: sy, behavior: 'instant'}); continue; }
          for (const o of stack.slice(i + 1)) {
            if (o === bgEl) break;
            if (o.contains(e)) continue;
            const os = style(o), oc = parse(os.backgroundColor);
            if (/^(IMG|VIDEO|CANVAS|PICTURE|IFRAME)$/.test(o.tagName) || o.closest('svg') ||
                os.backgroundImage !== 'none' || !oc || oc[3] > 0) {
              why = 'под текстом другой слой (картинка или подложка)';
              break;
            }
          }
        }
        scrollTo({left: sx, top: sy, behavior: 'instant'});
      }
      if (why) { skipped.push(desc(e) + ': ' + why); continue; }
      bg = bg || [255, 255, 255, 1];  // до корня фона нет — холст браузера белый
      const px = parseFloat(cs.fontSize), bold = (parseInt(cs.fontWeight, 10) || 400) >= 700;
      items.push({d: desc(e), fg: fg.slice(0, 3).map((v, k) => v * fg[3] + bg[k] * (1 - fg[3])),
        bg: bg.slice(0, 3), large: px >= 24 || (px >= 18.66 && bold)});
    }
    return {items, skipped};
  }
  throw new Error('standlib: неизвестная проверка ' + kind);
}"""

_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f-]{27}|[0-9a-f]{32}")


def _a11y(page, kind: str, scope: str, opt: dict | None = None):
    found = page.evaluate(_A11Y_JS, [kind, scope, opt or {}])
    if found is None:
        raise LookupError(f"область «{scope}» не найдена на странице — проверка ничего не видит")
    return found


def _unique(items) -> list[str]:
    return list(dict.fromkeys(items))


def _rgb(color) -> tuple[float, float, float]:
    """Тройка 0–255 или строка `#rgb` / `#rrggbb`."""
    if isinstance(color, str):
        h = color.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6:
            raise ValueError(f"не цвет: {color!r}")
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    r, g, b = list(color)[:3]
    return (r, g, b)


def _hex(color) -> str:
    return "#" + "".join(f"{round(v):02x}" for v in _rgb(color))


def _luminance(color) -> float:
    def channel(v: float) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(rgb1, rgb2) -> float:
    """Контраст двух цветов по WCAG (1…21): `(L1 + 0.05) / (L2 + 0.05)`, L — относительная
    яркость. Цвет — тройка 0–255 или `#rrggbb`; порядок аргументов не важен."""
    hi, lo = sorted((_luminance(rgb1), _luminance(rgb2)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def small_targets(page, scope: str = "body", minimum: int = TARGET_MIN) -> list[str]:
    """Цели касания (ссылки, кнопки, поля) меньше `minimum`. Порог 24 — обе стороны, с
    исключениями WCAG 2.5.8: ссылка внутри строки текста и одинокая мелкая цель (круг Ø24 вокруг
    центра никого не задевает). Порог от 44 (окно, кабинет) — только высота, без исключений."""
    opt = {"min": minimum, "spacing": minimum < WINDOW_TARGET_MIN}
    return _unique(_a11y(page, "targets", scope, opt))


def hidden_focusable(page, scope: str = "body") -> list[str]:
    """Элемент в порядке фокуса с `aria-hidden="true"` (своим или предка): клавиатура на него
    приходит, читалка молчит. Не нарушение — `inert`, `disabled`, `tabindex="-1"`. Невидимая
    sr-only кнопка БЕЗ aria-hidden — правильно (решение M3-5c), сюда не попадает."""
    return _unique(_a11y(page, "hidden", scope))


def unnamed_controls(page, scope: str = "body") -> list[str]:
    """Кнопка, ссылка, поле, `[role=button|tab|switch|checkbox]` без доступного имени (текст,
    `aria-label`, `aria-labelledby`, `<label>`, `alt` картинки внутри, `title`); `iframe` без
    `title`. Поле с одним `placeholder` — нарушение (подпись исчезает при вводе)."""
    return _unique(_a11y(page, "names", scope))


def low_contrast(
    page, scope: str = "body", minimum: float = CONTRAST_MIN
) -> tuple[list[str], list[str]]:
    """`(нарушители, не измерено)`. Контраст текста против ближайшего непрозрачного фона
    предков; крупный текст — порог 3.0. Текст над картинкой, градиентом, полупрозрачным фоном
    или чужим слоем не судим — он во втором списке (ложный ✗ хуже пропуска)."""
    found = _a11y(page, "contrast", scope)
    low = []
    for item in found["items"]:
        limit = min(minimum, CONTRAST_LARGE) if item["large"] else minimum
        ratio = contrast_ratio(item["fg"], item["bg"])
        if ratio < limit:
            fg, bg = (_hex(item[k]) for k in ("fg", "bg"))
            low.append(f"{item['d']}: контраст {ratio:.2f} < {limit:g} ({fg} на {bg})")
    return _unique(low), _unique(found["skipped"])


def focus_returns(page, opener_selector: str, close, *, opened=None, timeout: int = 2000) -> bool:
    """Кликнуть открывающий элемент, выполнить `close(page)` (например
    `lambda p: p.keyboard.press("Escape")`) и ответить, вернулся ли фокус на открывающий.
    `opened` — селектор открытого окна: дождаться его до закрытия. Фокус проверяется не сразу
    (браузер и скрипт двигают его после закрытия), а через 300 мс и затем до `timeout`."""
    page.click(opener_selector)
    if opened:
        page.wait_for_selector(opened, timeout=timeout)
    close(page)
    back = "s => document.activeElement === document.querySelector(s)"
    waited = 300
    page.wait_for_timeout(waited)
    while not page.evaluate(back, opener_selector):
        if waited >= timeout:
            return False
        page.wait_for_timeout(100)
        waited += 100
    return True


def a11y_check(
    rep: Report, page, tag: str, *, scope: str = "body", minimum: int = TARGET_MIN, contrast=True
) -> bool:
    """Все проверки доступности на открытой странице: по одному `check` на класс (коды
    `A11Y_CODES`), подпись дефекта — элемент без адреса страницы (повтор на сотне страниц
    печатается один раз). «Не измерено» по контрасту — наблюдение, не ✗. Звать на КАЖДОЙ
    странице стенда; витрина — `minimum=24`, кабинет и окно блока — 44."""
    try:
        runs = [
            ("a11y-target", f"цели ≥ {minimum}px", small_targets(page, scope, minimum)),
            ("a11y-hidden-focus", "нет фокуса внутри aria-hidden", hidden_focusable(page, scope)),
            ("a11y-name", "у элементов управления есть имя", unnamed_controls(page, scope)),
        ]
        unmeasured: list[str] = []
        if contrast:
            low, unmeasured = low_contrast(page, scope)
            runs.append(("a11y-contrast", f"контраст текста ≥ {CONTRAST_MIN:g}", low))
    except LookupError as exc:
        return rep.check(False, f"{tag}: {exc}", sigs=f"a11y: нет области {scope}", code="a11y")
    good = True
    for code, title, bad in runs:
        good &= rep.check(
            not bad,
            f"{tag}: {title} ({len(bad)}: {bad[:3]})" if bad else f"{tag}: {title}",
            sigs=[f"{code}: {_ID.sub('<id>', x)}" for x in bad],
            code=code,
        )
    for item in unmeasured:
        rep.note(f"a11y-contrast не измерено — {_ID.sub('<id>', item)}")
    return good


# --- замок каркаса: страницы через set_content, без сервера и БД --------------------------

_HEAD = '<!doctype html><html><meta name=viewport content="width=device-width">'
#: скрипт ставит метку; конечная анимация 300 мс и бесконечная (её settle ждать не должен)
_GOOD = (
    _HEAD + "<style>@keyframes a{from{opacity:.2}to{opacity:1}}"
    "#fin{animation:a .3s linear 1}#inf{animation:a 1s linear infinite}</style>"
    '<body style="margin:0"><main><p id="fin">Конечная</p><p id="inf">Бесконечная</p></main>'
    "<script>document.documentElement.setAttribute('data-js', '1')</script></body></html>"
)
_WIDE = _GOOD.replace("<main>", '<main><div style="width:800px">широкая полоса</div>')
_BOOM = _GOOD.replace("</script>", ";throw new Error('selftest-boom')</script>")
_LOGIN_FORM = (
    _HEAD + '<body><form method="post"><input name="login"><input name="password" '
    'type="password"><button type="submit">Anmelden</button></form></body></html>'
)
_SELF_URL = "http://selftest.local"
_HAS_JS = "document.documentElement.getAttribute('data-js') === '1'"
_FINITE_RUNNING = "document.getAnimations().some(a => a.effect.getTiming().iterations === 1)"


def _fake_login(page, accept: bool) -> dict:
    """Вход без сервера: страницу входа и ответ на POST отдаёт маршрут. Перенаправление из
    маршрута браузер повёл бы в сеть, поэтому «принят/отклонён» задаёт адрес формы."""
    seen = {}
    action = "/dashboard/" if accept else LOGIN_PATH
    form = _LOGIN_FORM.replace('method="post"', f'method="post" action="{action}"')

    def serve(route):
        if route.request.method == "POST":
            seen["post"] = route.request.post_data or ""
            body = _GOOD if accept else form
        else:
            body = form
        route.fulfill(status=200, body=body, content_type="text/html; charset=utf-8")

    page.route(_SELF_URL + "/**", serve)
    return seen


def _selftest_report(lock: Report) -> None:
    """`Report`: счёт, коды, повтор подписи — одна строка, сводка и код выхода."""
    rep = Report()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rep.check(True, "хорошо")
        rep.check(False, "плохо А", sigs="один дефект", code="x")
        rep.check(False, "плохо Б", sigs="один дефект", code="x")
        rep.note("наблюдение")
        rep.note("наблюдение")
        line = rep.summary("проба")
    out = buf.getvalue()
    lock.check((rep.ok, len(rep.fail)) == (1, 2), "Report: счёт 1 ✓ и 2 ✗")
    lock.check(rep.codes == ["x", "x"] and rep.exit_code == 1, "Report: коды ✗ и код выхода 1")
    lock.check(
        out.count("  ✗ ") == 1 and out.count("  · ") == 1,
        "Report: повтор подписи и наблюдения печатается один раз",
    )
    lock.check(
        line == "проба: 1 ✓, 2 ✗" and "×2    один дефект" in out,
        f"Report: сводка с числом повторов и итоговая строка ({line!r})",
    )
    lock.check(Report().exit_code == 0, "Report: без ✗ код выхода 0")


_SR_ONLY = (
    ".sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;"
    "clip:rect(0,0,0,0);white-space:nowrap;border:0}"
)
_A11Y_HEAD = (
    _HEAD + "<style>body{margin:0;font:16px sans-serif;color:#111;background:#fff}"
    "button,input,select{min-height:32px;min-width:32px}"
    ".tiny{width:16px;height:16px;min-width:0;min-height:0;padding:0;border:0}"
    ".photo{position:absolute;inset:0;width:100%;height:100%}" + _SR_ONLY + "</style><body>"
)
_GIF = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="
#: без нарушений: ссылка в строке текста, sr-only кнопка без aria-hidden, имя из aria-label,
#: alt, <label>, title; скрытое от читалки — вне порядка фокуса; подпись над градиентом
_A11Y_CLEAN = (
    _A11Y_HEAD + '<main><p>Text mit <a href="#x">Link in der Zeile</a> und mehr Text.</p>'
    '<a href="#y" style="display:inline-block;padding:8px">Weiter</a> '
    '<button type="button">Speichern</button>'
    '<button type="button" class="sr-only">Übernehmen</button>'
    '<label for="n">Name</label> <input id="n"> '
    '<button type="button" aria-label="Schließen"><svg aria-hidden="true" width="16" '
    'height="16"></svg></button> '
    f'<a href="#i" style="display:inline-block"><img alt="Start" width="32" height="32" '
    f'src="{_GIF}"></a>'
    '<div aria-hidden="true"><a href="#h" tabindex="-1">dekorativ</a></div>'
    '<div aria-hidden="true" inert><a href="#k">inert</a></div>'
    '<iframe title="Karte" srcdoc="" width="100" height="40"></iframe>'
    '<p style="font-size:24px;color:#888">Große Zeile</p><p style="color:#767676">Grau</p>'
    '<div style="background-image:linear-gradient(#000,#333);color:#fff;padding:8px">'
    "Text über Verlauf</div></main></body></html>"
)
#: две мелкие цели вплотную (✗ при 24) и одинокая (при 24 — исключение «Spacing», при 44 — ✗)
_A11Y_TARGETS = (
    _A11Y_HEAD + '<button class="tiny" aria-label="A"></button>'
    '<button class="tiny" aria-label="B"></button>'
    '<button class="tiny" aria-label="C" style="position:absolute;left:300px;top:300px">'
    "</button></body></html>"
)
#: три нарушения (ссылка в скрытом предке, скрытая кнопка, sr-only кнопка С aria-hidden) и
#: три исключения (inert, disabled, tabindex=-1)
_A11Y_HIDDEN = (
    _A11Y_HEAD + '<div aria-hidden="true"><a href="#a">Versteckt</a></div>'
    '<button aria-hidden="true">Zu</button>'
    '<button class="sr-only" aria-hidden="true">Übernehmen</button>'
    '<div aria-hidden="true" inert><a href="#b">inert</a></div>'
    '<button aria-hidden="true" disabled>aus</button>'
    '<div aria-hidden="true"><a href="#c" tabindex="-1">raus</a></div></body></html>'
)
#: пять нарушений (кнопка-иконка, поле с placeholder, ссылка-картинка без alt, iframe, select)
#: и четыре имени не из текста (title, aria-labelledby, обёртка label, sr-only текст)
_A11Y_NAMES = (
    _A11Y_HEAD + '<button type="button"><svg aria-hidden="true" width="16" height="16"></svg>'
    '</button> <input placeholder="Suche"> '
    f'<a href="#z" style="display:inline-block"><img width="32" height="32" src="{_GIF}"></a>'
    '<iframe srcdoc="" width="100" height="40"></iframe> <select><option>A</option></select>'
    '<input title="Menge"> <span id="lb">Farbe</span><input aria-labelledby="lb"> '
    "<label>Ort <select><option>B</option></select></label> "
    '<button type="button"><span class="sr-only">Menü</span></button></body></html>'
)
#: ✗: серый #999 на белом (2.85), обычный и крупный. Не измерено: градиент, полупрозрачный
#: фон, фото под подписью — на экране и далеко за ним
_PHOTO = (
    f'<div style="position:relative;padding:8px"><img class="photo" src="{_GIF}" alt="">'
    '<span style="position:relative;color:#fff">%s</span></div>'
)
_A11Y_CONTRAST = (
    _A11Y_HEAD + '<p id="grey" style="color:#999">grauer Text</p>'
    '<p id="big" style="color:#999;font-size:24px">grau und groß</p>'
    '<p style="color:#888;font-size:24px">groß reicht</p>'
    '<div id="grad" style="background-image:linear-gradient(#000,#333);color:#fff">Verlauf</div>'
    '<div id="half" style="background-color:rgba(0,0,0,.5);color:#fff">halb</div>'
    + _PHOTO % "Foto oben"
    + '<div style="height:3000px"></div>'
    + _PHOTO % "Foto unten"
    + "</body></html>"
)
_DIALOG = (
    _A11Y_HEAD + '<button id="open" onclick="document.getElementById(\'dlg\').showModal()">'
    'Öffnen</button> <button id="other">Anderes</button>'
    '<dialog id="dlg"><button>Schließen</button></dialog><!--script--></body></html>'
)
_DIALOG_GOOD = _DIALOG
_DIALOG_BAD = _DIALOG.replace(
    "<!--script-->",
    "<script>document.getElementById('dlg').addEventListener('close', () => "
    "document.getElementById('other').focus())</script>",
)


def _selftest_a11y(lock: Report, browser) -> None:
    """Проверки доступности: страница без нарушений — 0 находок, с нарушением — находка."""

    def page_with(html, *, js=True):
        page = open_page(browser, 390, 844, js=js, url=_SELF_URL)
        page.set_content(html)
        return page

    print("— доступность: страница без нарушений")
    page = page_with(_A11Y_CLEAN)
    for name, got in (
        ("small_targets 24", small_targets(page)),
        ("hidden_focusable", hidden_focusable(page)),
        ("unnamed_controls", unnamed_controls(page)),
    ):
        lock.check(not got, f"{name}: чистая страница — 0 находок ({got})")
    low, unmeasured = low_contrast(page)
    lock.check(not low, f"low_contrast: чистая страница — 0 находок ({low})")
    lock.check(
        len(unmeasured) == 1 and "над картинкой или градиентом" in unmeasured[0],
        f"low_contrast: текст над background-image — «не измерено», не ✗ ({unmeasured})",
    )
    clean = Report(quiet=True)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = a11y_check(clean, page, "чистая")
    lock.check(
        ok and clean.ok == 4 and not clean.fail and len(clean.notes) == 1,
        f"a11y_check: чистая страница — 4 ✓, 0 ✗, одно наблюдение ({clean.fail}, {clean.notes})",
    )
    try:
        small_targets(page, "#no-such-scope")
        missing = False
    except LookupError:
        missing = True
    with contextlib.redirect_stdout(buf):
        a11y_check(clean, page, "чистая", scope="#no-such-scope")
    lock.check(
        missing and clean.codes == ["a11y"],
        "нет области scope — ошибка и ✗, а не молчаливые «0 находок»",
    )
    page.context.close()

    print("— доступность: цели касания")
    page = page_with(_A11Y_TARGETS)
    got = small_targets(page)
    lock.check(
        len(got) == 2 and all("16×16 < 24" in x for x in got) and "«C»" not in str(got),
        f"small_targets: две цели 16×16 вплотную ловятся, одинокая — исключение 2.5.8 ({got})",
    )
    got = small_targets(page, "body", WINDOW_TARGET_MIN)
    lock.check(len(got) == 3, f"small_targets: при пороге 44 — все три, без исключений ({got})")
    page.context.close()

    print("— доступность: фокус внутри aria-hidden")
    page = page_with(_A11Y_HIDDEN)
    got = hidden_focusable(page)
    lock.check(
        len(got) == 3 and "у предка div" in got[0] and "sr-only" in got[2],
        f"hidden_focusable: ссылка в aria-hidden, кнопка и sr-only кнопка с aria-hidden ({got})",
    )
    lock.check(
        not any(word in str(got) for word in ("inert", "«aus»", "«raus»")),
        "hidden_focusable: inert, disabled и tabindex=-1 — не нарушение",
    )
    page.context.close()

    print("— доступность: имена")
    page = page_with(_A11Y_NAMES, js=False)  # проверки работают и без JS на странице
    got = unnamed_controls(page)
    lock.check(
        len(got) == 5
        and [x.split(" ")[0] for x in got] == ["button", "input", "a", "iframe", "select"],
        f"unnamed_controls: кнопка, поле, ссылка-картинка, iframe и select без имени ({got})",
    )
    lock.check(
        len(got) == 5 and "только placeholder" in got[1] and "iframe без title" in got[3],
        "unnamed_controls: причина названа (placeholder, title у iframe)",
    )
    page.context.close()

    print("— доступность: контраст")
    page = page_with(_A11Y_CONTRAST)
    low, unmeasured = low_contrast(page)
    lock.check(
        len(low) == 2 and "p#grey" in low[0] and "2.85 < 4.5 (#999999 на #ffffff)" in low[0],
        f"low_contrast: серый #999 на белом — 2.85 < 4.5 ({low})",
    )
    lock.check(
        len(low) == 2 and "p#big" in low[1] and "< 3" in low[1],
        "low_contrast: крупный текст судится по порогу 3.0 (#999 — ✗, #888 — нет)",
    )
    reasons = " | ".join(unmeasured)
    lock.check(
        len(unmeasured) == 4
        and "div#grad" in reasons
        and "полупрозрачный фон" in reasons
        and reasons.count("под текстом другой слой") == 2,
        f"low_contrast: градиент, полупрозрачный фон и фото под подписью — не измерено ({reasons})",
    )
    lock.check(page.evaluate("scrollY") == 0, "low_contrast: прокрутка страницы возвращена")
    bad = Report(quiet=True)
    with contextlib.redirect_stdout(buf):
        a11y_check(bad, page, "страница А")
        a11y_check(bad, page, "страница Б")
    lock.check(
        bad.codes == ["a11y-contrast"] * 2 and all(n == 2 for n, _ in bad.sigs.values()),
        f"a11y_check: ✗ с кодом a11y-contrast, подпись дефекта не зависит от страницы ({bad.codes})",
    )
    page.context.close()

    print("— доступность: a11y_check на странице с нарушениями всех классов")
    page = page_with(_A11Y_TARGETS.replace("</body>", _A11Y_HIDDEN.split("<body>")[1]))
    page.evaluate(
        "document.body.insertAdjacentHTML('beforeend', "
        '\'<input placeholder="Suche"><p style="color:#999">grau</p>\')'
    )
    bad = Report(quiet=True)
    with contextlib.redirect_stdout(buf):
        ok = a11y_check(bad, page, "плохая")
    lock.check(
        not ok and tuple(bad.codes) == A11Y_CODES,
        f"a11y_check: по одному ✗ на класс, коды {A11Y_CODES} ({bad.codes})",
    )
    page.context.close()

    print("— доступность: возврат фокуса")
    for html, want in ((_DIALOG_GOOD, True), (_DIALOG_BAD, False)):
        page = page_with(html)
        got = focus_returns(
            page, "#open", lambda p: p.keyboard.press("Escape"), opened="#dlg[open]", timeout=600
        )
        lock.check(
            got is want and not page.evaluate("document.getElementById('dlg').open"),
            f"focus_returns: диалог {'возвращает' if want else 'НЕ возвращает'} фокус → {got}",
        )
        page.context.close()


def selftest() -> None:
    """Каркас на заведомо хороших и сломанных страницах; сломанный каркас → ✗ и код 1."""
    lock = Report()
    _selftest_report(lock)
    combos = list(matrix())
    lock.check(
        len(combos) == 8 and len(set(combos)) == 8 and not combos[0][3],
        f"matrix: 2 размера × 2 языка × 2 режима = 8 сочетаний, первым — без JS ({len(combos)})",
    )
    with launch() as browser:
        print("— хорошая страница (390, ru, с JS)")
        good = Report(quiet=True)
        page = open_page(browser, 390, 844, js=True, lang="ru", url=_SELF_URL)
        page.set_content(_GOOD)
        lock.check(page.evaluate(_FINITE_RUNNING), "до settle идёт конечная анимация")
        calm = settle(page, True, good)
        lock.check(
            calm and not good.notes and not page.evaluate(_FINITE_RUNNING),
            "settle: дождался конечной анимации, бесконечную не ждал",
        )
        good.check(overflow(page) <= 0, "без гор. скролла", code="overflow")
        good.check(not page.js_errors, "без ошибок JS", code="jserror")
        lock.check(good.ok == 2 and not good.fail, f"хорошая страница: 0 ✗ ({good.fail})")
        lock.check(page.evaluate(_HAS_JS), "с JS скрипт страницы исполнился")
        lock.check(
            page.evaluate("[window.innerWidth, window.innerHeight]") == [390, 844],
            "open_page: размер окна 390×844",
        )
        cookies = {c["name"]: c["value"] for c in page.context.cookies(_SELF_URL)}
        lock.check(
            page.evaluate("navigator.language") == "ru-DE" and cookies == {LANGUAGE_COOKIE: "ru"},
            f"open_page: язык ru — locale и кука {LANGUAGE_COOKIE} ({cookies})",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = shot(page, os.path.join(tmp, "новая"), "good")
            lock.check(
                path.endswith("good.png") and os.path.getsize(path) > 500,
                "shot: скриншот записан, папка создана",
            )
        page.context.close()

        print("— переполнение по ширине")
        for w, h in SIZES:
            page = open_page(browser, w, h, url=_SELF_URL)
            page.set_content(_WIDE)
            over = overflow(page)
            want = 800 - w
            lock.check(
                over == want if want > 0 else over <= 0,
                f"overflow: полоса 800px при {w} → {over}px ({'ловится' if want > 0 else 'нет'})",
            )
            page.context.close()

        print("— без JS")
        page = open_page(browser, 390, 844, js=False, url=_SELF_URL)
        page.set_content(_GOOD)
        lock.check(not page.evaluate(_HAS_JS), "без JS скрипт страницы не исполнился")
        lock.check(settle(page, False), "settle: без JS не ждёт")
        page.set_content(_WIDE)
        lock.check(overflow(page) == 410, "overflow меряет и без JS (410px)")
        page.context.close()

        print("— ошибка JS")
        page = open_page(browser, 1440, 900, url=_SELF_URL)
        page.set_content(_BOOM)
        settle(page, True)
        page.wait_for_timeout(100)
        lock.check(
            any("selftest-boom" in e for e in page.js_errors),
            f"open_page: ошибка страницы попала в js_errors ({page.js_errors})",
        )
        page.context.close()

        print("— вход")
        for want in (True, False):
            page = open_page(browser, 1440, 900, url=_SELF_URL)
            seen = _fake_login(page, accept=want)
            got = login(page, _SELF_URL, EMAIL, PASSWORD)
            lock.check(
                got is want and seen.get("post") == f"login=owner%40ptx.test&password={PASSWORD}",
                f"login: вход {'принят' if want else 'отклонён'} → {got} ({page.url})",
            )
            page.context.close()
        _selftest_a11y(lock, browser)
    lock.finish("standlib selftest")


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        selftest()
    else:
        sys.exit(__doc__)
