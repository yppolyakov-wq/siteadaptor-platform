"""FB-33 стопка 13, D6: стенд «select анкеты события — только из списка» (витрина retreat).

Что проверяет (1440×900 и 390×844, de и ru, без JS и с JS; плюс 844×390):
- форма брони: подделанный вариант select (с JS — `page.evaluate` дописывает `<option>` и
  отправляет форму; без JS — `context.request.post` с CSRF) → билета нет (остались на
  странице события), сообщение с подписью поля, введённое вернулось в поля, у select
  `aria-invalid` и `aria-describedby` на существующий текст ошибки, фокус — на поле;
- негативный контроль: вариант из списка проходит (переход на подтверждение билета);
- страница участников гостя: подделка → 200 с формой из присланного и ошибкой у поля;
- на каждой открытой странице — `a11y_check` (витрина, 24 px) и отсутствие гор. скролла.

Запуск (только стенд-БД, имя кончается на `_stand`):

    DB_NAME=platform_s13_d6_stand uv run python scripts/fb33_d6_select_stand.py --setup <папка>
    DB_NAME=platform_s13_d6_stand DB_CONN_MAX_AGE=0 uv run python manage.py runserver \\
        0.0.0.0:8064 --settings=config.settings.stand --noreload
    STAND_URL=http://retreat.siteadaptor.de:8064 \\
        uv run --no-project --with playwright==1.55.0 python scripts/fb33_d6_select_stand.py <папка>

`--setup` (ORM, тенант `retreat`) включает бизнесу русский язык витрины, заводит бесплатное
событие «D6 Stand-Retreat» с select-анкетой и билет на 2 места; пишет `<папка>/setup.json`.
Итог «N ✓, 0 ✗».
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from urllib.parse import urlsplit

import standlib as sl

SLUG = "retreat"
FORGED = '=HYPERLINK("http://evil.example/","x")'
LABEL = {"de": "Ernährung", "ru": "Питание"}
SIZES = (*sl.SIZES, (844, 390))
#: свои элементы среза: метка select с полем и текст ошибки под ней
BOOK_SCOPE = "form[data-rv1] label:has(select[name=reg_diet])"
GUEST_SCOPE = "form[data-participants-form]"
_IP = iter(range(1, 250))


def _page(browser, w, h, js, lang):
    """Страница со своим адресом клиента: лимит брони витрины — 5 запросов за 10 минут с
    адреса (`ratelimit.client_ip` читает `X-Forwarded-For`), обход матрицы иначе упрётся в 429."""
    page = sl.open_page(browser, w, h, js=js, lang=lang)
    page.context.set_extra_http_headers({"X-Forwarded-For": f"10.64.{next(_IP)}.1"})
    return page


SETUP = f"""
import json
from datetime import timedelta
from django.utils import timezone
from django_tenants.utils import schema_context
from apps.tenants.models import Tenant
t = Tenant.objects.get(schema_name={SLUG!r})
if "ru" not in (t.enabled_locales or []):
    t.enabled_locales = [*(t.enabled_locales or ["de"]), "ru"]
    t.save(update_fields=["enabled_locales"])
with schema_context({SLUG!r}):
    from apps.events import participants
    from apps.events.models import Event
    from apps.events.services import book_ticket
    ev, _ = Event.objects.get_or_create(
        title="D6 Stand-Retreat",
        defaults=dict(
            starts_at=timezone.now() + timedelta(days=60),
            status=Event.STATUS_PUBLISHED,
            price_cents=0,
            capacity=0,
            questions=["Anreise mit?"],
            registration_fields=["country", "diet", "experience", "medical"],
        ),
    )
    ticket = ev.tickets.filter(quantity=2).first() or book_ticket(
        ev, name="Stand Gast", email="d6-stand@example.com", quantity=2, auto_confirm=True
    )
    print("SETUP" + json.dumps({{"event": str(ev.pk), "token": participants.token(ticket)}}))
"""


def setup(out: str) -> None:
    db = os.environ.get("DB_NAME", "")
    if not db.endswith("_stand"):
        sys.exit("--setup только на стенд-БД (DB_NAME=…_stand)")
    res = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "manage.py",
            "shell",
            "--settings=config.settings.stand",
            "-c",
            SETUP,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    line = next((ln for ln in res.stdout.splitlines() if ln.startswith("SETUP")), None)
    if line is None:
        sys.exit("setup не удался:\n" + res.stderr[-1200:])
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "setup.json"), "w") as fh:
        fh.write(line[5:])
    print("setup:", line[5:])


def _field_state(page, name):
    return page.evaluate(
        """(name) => {
          const el = document.querySelector(`[name="${name}"]`);
          if (!el) return null;
          const ids = (el.getAttribute('aria-describedby') || '').split(' ').filter(Boolean);
          const desc = ids.map(i => document.getElementById(i)).filter(Boolean);
          return {
            invalid: el.getAttribute('aria-invalid'),
            described: desc.map(d => d.textContent.trim()).join(' '),
            visible: !!(el.offsetWidth || el.offsetHeight),
            focused: document.activeElement === el,
            value: el.value,
          };
        }""",
        name,
    )


def _wait_focus(page, name):
    """`autofocus` браузер ставит после разбора страницы, не сразу — ждём до 2 с (не дождались —
    проверка ниже даст ✗)."""
    try:
        page.wait_for_function(
            "n => document.activeElement && document.activeElement.name === n",
            arg=name,
            timeout=2000,
        )
    except Exception:  # noqa: BLE001 — таймаут Playwright; пакет импортируется лениво
        pass


def _forge_and_submit(page, select_name, fill):
    """С JS: дописать подделанный `<option>`, выбрать его и отправить форму (как подделка)."""
    page.evaluate(
        """([name, forged, fill]) => {
          const sel = document.querySelector(`select[name="${name}"]`);
          for (const [k, v] of Object.entries(fill)) {
            const el = sel.form.querySelector(`[name="${k}"]`);
            if (el) el.value = v;
          }
          const opt = document.createElement('option');
          opt.value = forged; opt.textContent = 'x';
          sel.appendChild(opt); sel.value = forged;
          sel.form.submit();
        }""",
        [select_name, FORGED, fill],
    )


def _post_nojs(page, url, form_selector, data):
    """Без JS: тот же POST запросом контекста (CSRF — из страницы и куки контекста). Запрос
    контекста не знает правила `--host-resolver-rules` браузера: идём на 127.0.0.1 с заголовком
    `Host` поддомена и куками контекста вручную (иначе DNS уведёт поддомен на внешний сервер)."""
    token = page.locator(f"{form_selector} input[name=csrfmiddlewaretoken]").first.get_attribute(
        "value"
    )
    action = page.locator(form_selector).first.get_attribute("action") or urlsplit(url).path
    base = urlsplit(sl.BASE_URL)
    path = urlsplit(action).path if action.startswith("http") else action
    cookies = "; ".join(f"{c['name']}={c['value']}" for c in page.context.cookies(sl.BASE_URL))
    res = page.context.request.post(
        f"{base.scheme}://127.0.0.1:{base.port}{path}",
        form={"csrfmiddlewaretoken": token, **data},
        headers={"Host": base.netloc, "Cookie": cookies, "Referer": url},
        max_redirects=0,
    )
    # куки ответа (сессия с введённым, сообщения) легли бы на 127.0.0.1 — переносим на поддомен
    jar = []
    for h in res.headers_array:
        if h["name"].lower() == "set-cookie":
            name, _, rest = h["value"].partition("=")
            jar.append({"name": name.strip(), "value": rest.split(";")[0], "url": sl.BASE_URL})
    if jar:
        page.context.add_cookies(jar)
    return res


def _a11y(rep, page, tag, scope):
    """`a11y_check` по своим элементам (поле с ошибкой и её текст); вся страница — наблюдением:
    у формы брони события есть прежние дефекты (поля только с placeholder, серый текст),
    срез D6 их не трогает — их видно в сводке «наблюдения», они не ✗ этого среза."""
    sl.a11y_check(rep, page, tag, scope=scope, minimum=24)
    for title, bad in (
        ("цели", sl.small_targets(page, "body", 24)),
        ("фокус в aria-hidden", sl.hidden_focusable(page, "body")),
        ("имя", sl.unnamed_controls(page, "body")),
        ("контраст", sl.low_contrast(page, "body")[0]),
    ):
        for item in bad:
            rep.note(f"прежнее (вся страница, {title}): {item}")


def _one_message(rep, page, tag, lang):
    """Одна ошибка — одно объявление: одно сводное сообщение, подпись поля — только у поля."""
    msgs = page.locator("main [role=status], main [role=alert]").all_inner_texts()
    rep.check(len(msgs) == 1, f"{tag}: одно сообщение над формой ({len(msgs)}: {msgs[:2]})")
    rep.check(
        not any(LABEL[lang] in m for m in msgs), f"{tag}: подробность — у поля, не в сообщении"
    )


def _clear_of_bars(rep, page, tag, name, js=True):
    """Поле с ошибкой целиком в окне и не под нижней панелью покупки (`[data-buybar]`).
    Плавная прокрутка (без reduced-motion) идёт до ~1 с — ждём, пока `scrollY` не замрёт."""
    if js:  # без JS таймеры страницы не идут — и плавной прокрутки нет
        page.evaluate(
            """() => new Promise(done => { let last = -1, still = 0, n = 0;
          const tick = () => { n += 1; still = scrollY === last ? still + 1 : 0; last = scrollY;
            if (still >= 3 || n > 60) done(); else setTimeout(tick, 50); }; tick(); })"""
        )
    got = page.evaluate(
        """(name) => {
          const el = document.querySelector(`[name="${name}"]`);
          if (!el) return null;
          const r = el.getBoundingClientRect();
          const bars = [...document.querySelectorAll('[data-buybar]')].filter(
            b => b.offsetWidth && getComputedStyle(b).display !== 'none');
          const hit = bars.some(b => { const q = b.getBoundingClientRect();
            return r.bottom > q.top && r.top < q.bottom && r.right > q.left && r.left < q.right; });
          return {inView: r.top >= 0 && r.bottom <= innerHeight, hit};
        }""",
        name,
    )
    got = got or {}
    rep.check(got.get("inView"), f"{tag}: поле с ошибкой в окне", code="scroll")
    rep.check(got.get("hit") is False, f"{tag}: поле не под нижней панелью", code="scroll")


def motion(browser, rep, event_pk):
    """prefers-reduced-motion: «Weiter» и открытие шага 2 при ошибке — без плавной прокрутки."""
    url = f"{sl.BASE_URL}/veranstaltung/{event_pk}/"
    probe = "() => new Promise(r => { const a = scrollY; setTimeout(() => r([a, scrollY]), 400); })"
    for w, h in ((390, 844), (844, 390)):
        tag = f"{w}×{h} de js reduce"
        page = _page(browser, w, h, True, "de")
        page.emulate_media(reduced_motion="reduce")
        page.goto(url)
        sl.settle(page, True, rep)
        page.click("[data-rv1-next]")
        a, b = page.evaluate(probe)
        rep.check(a == b, f"{tag}: «Weiter» — прокрутка мгновенная ({a} → {b})", code="motion")
        page.goto(url)
        with page.expect_navigation():
            _forge_and_submit(page, "reg_diet", {"name": "Reduce Stand"})
        a, b = page.evaluate(probe)
        rep.check(a == b, f"{tag}: ошибка — прокрутка мгновенная ({a} → {b})", code="motion")
        _wait_focus(page, "reg_diet")
        _clear_of_bars(rep, page, tag, "reg_diet")
        page.context.close()


def booking(browser, rep, w, h, lang, js, event_pk, control):
    tag = f"{w}×{h} {lang} {'js' if js else 'nojs'} бронь"
    page = _page(browser, w, h, js, lang)
    url = f"{sl.BASE_URL}/veranstaltung/{event_pk}/"
    resp = page.goto(url)
    sl.settle(page, js, rep)
    rep.check(resp.status == 200, f"{tag}: страница события {resp.status}", code="status")
    rep.check(page.locator("select[name=reg_diet]").count() == 1, f"{tag}: есть select анкеты")
    rep.check(page.locator("[aria-invalid]").count() == 0, f"{tag}: без ввода — без ошибки поля")
    _a11y(rep, page, f"{tag} до", BOOK_SCOPE)
    fill = {"name": "Erika Stand", "email": "erika@example.com", "reg_country": "Österreich"}
    if js:
        with page.expect_navigation():
            _forge_and_submit(page, "reg_diet", fill)
    else:
        res = _post_nojs(page, url, "form[data-rv1]", {**fill, "quantity": "1", "reg_diet": FORGED})
        rep.check(res.status == 302, f"{tag}: подделка → redirect ({res.status})", code="status")
        location = res.headers.get("location", "")
        page.goto(location if location.startswith("http") else sl.BASE_URL + location)
    sl.settle(page, js, rep)
    rep.check(f"/veranstaltung/{event_pk}/" in page.url, f"{tag}: билета нет — та же страница")
    body = page.content()
    rep.check("HYPERLINK" not in body and "evil.example" not in body, f"{tag}: подделка не эхом")
    _one_message(rep, page, tag, lang)
    _wait_focus(page, "reg_diet")
    _clear_of_bars(rep, page, tag, "reg_diet", js)
    st = _field_state(page, "reg_diet") or {}
    rep.check(st.get("invalid") == "true", f"{tag}: aria-invalid у select", code="a11y")
    rep.check(LABEL[lang] in st.get("described", ""), f"{tag}: aria-describedby → текст ошибки")
    rep.check(st.get("visible"), f"{tag}: поле с ошибкой видно (шаг 2 открыт)")
    rep.check(st.get("focused"), f"{tag}: фокус на поле с ошибкой", code="focus")
    rep.check(st.get("value") == "", f"{tag}: подделанный вариант не выбран")
    for name, want in fill.items():
        got = (_field_state(page, name) or {}).get("value")
        rep.check(got == want, f"{tag}: «{name}» вернулось ({got!r})")
    over = sl.overflow(page)
    rep.check(over <= 0, f"{tag}: без гор. скролла ({over}px)", code="overflow")
    rep.check(not page.js_errors, f"{tag}: без ошибок JS ({page.js_errors[:2]})")
    _a11y(rep, page, f"{tag} ошибка", BOOK_SCOPE)
    sl.a11y_check(rep, page, f"{tag} текст ошибки", scope="#reg_diet-error", minimum=24)
    sl.shot(page, OUT, f"book_{w}x{h}_{lang}_{'js' if js else 'nojs'}", full=True)
    # повтор страницы: введённое показано один раз
    page.goto(url)
    rep.check((_field_state(page, "name") or {}).get("value") == "", f"{tag}: введённое — один раз")
    if control:
        _control(page, rep, tag, url, js)
    page.context.close()


def _control(page, rep, tag, url, js):
    """Негативный контроль: вариант из списка проходит — переход на подтверждение билета."""
    page.goto(url)
    sl.settle(page, js, rep)
    if js:
        page.click("[data-rv1-next]")
    page.fill("input[name=name]", "Kontrolle Stand")
    page.fill("input[name=email]", "kontrolle@example.com")
    page.select_option("select[name=reg_diet]", "Vegan")
    with page.expect_navigation():
        page.click("form[data-rv1] button[type=submit]")
    rep.check("/e/" in page.url, f"{tag}: контроль — вариант из списка проходит ({page.url})")


def guest(browser, rep, w, h, lang, js, token):
    tag = f"{w}×{h} {lang} {'js' if js else 'nojs'} участники"
    page = _page(browser, w, h, js, lang)
    url = f"{sl.BASE_URL}/e/teilnehmer/{token}/"
    resp = page.goto(url)
    sl.settle(page, js, rep)
    rep.check(resp.status == 200, f"{tag}: страница {resp.status}", code="status")
    _a11y(rep, page, f"{tag} до", GUEST_SCOPE)
    fill = {"p1_name": "Erika Stand", "p2_name": "Ben Stand"}
    if js:
        with page.expect_navigation():
            _forge_and_submit(page, "p2_reg_diet", fill)
    else:
        res = _post_nojs(page, url, "form[data-participants-form]", {**fill, "p2_reg_diet": FORGED})
        rep.check(res.status == 200, f"{tag}: подделка → 200 ({res.status})", code="status")
        rep.check(
            "no-store" in res.headers.get("cache-control", ""), f"{tag}: Cache-Control no-store"
        )
        html = res.text()
        # тот же ответ — в браузер (CSS и шрифты идут с сервера стенда)
        page.route(
            url, lambda route: route.fulfill(status=200, body=html, content_type="text/html")
        )
        page.goto(url)
        page.unroute(url)
    body = page.content()
    rep.check("HYPERLINK" not in body, f"{tag}: подделка не эхом")
    _one_message(rep, page, tag, lang)
    _wait_focus(page, "p2_reg_diet")
    _clear_of_bars(rep, page, tag, "p2_reg_diet", js)
    st = _field_state(page, "p2_reg_diet") or {}
    rep.check(st.get("invalid") == "true", f"{tag}: aria-invalid у select", code="a11y")
    rep.check(LABEL[lang] in st.get("described", ""), f"{tag}: aria-describedby → текст ошибки")
    rep.check(st.get("focused"), f"{tag}: фокус на поле с ошибкой", code="focus")
    for name, want in fill.items():
        got = (_field_state(page, name) or {}).get("value")
        rep.check(got == want, f"{tag}: «{name}» из присланного ({got!r})")
    over = sl.overflow(page)
    rep.check(over <= 0, f"{tag}: без гор. скролла ({over}px)", code="overflow")
    rep.check(not page.js_errors, f"{tag}: без ошибок JS ({page.js_errors[:2]})")
    _a11y(rep, page, f"{tag} ошибка", GUEST_SCOPE)
    sl.shot(page, OUT, f"guest_{w}x{h}_{lang}_{'js' if js else 'nojs'}", full=True)
    # негативный контроль: вариант из списка сохраняется (redirect на ту же страницу)
    page.goto(url)
    page.select_option("select[name=p2_reg_diet]", "Vegan")
    with page.expect_navigation():
        page.click("form[data-participants-form] button[type=submit]")
    st = _field_state(page, "p2_reg_diet") or {}
    rep.check(st.get("value") == "Vegan" and not st.get("invalid"), f"{tag}: контроль сохранён")
    page.context.close()


def main():
    with open(os.path.join(OUT, "setup.json")) as fh:
        cfg = json.load(fh)
    rep = sl.Report()
    done_control = set()
    with sl.launch() as browser:
        for w, h, lang, js in sl.matrix(sizes=SIZES):
            control = js not in done_control
            done_control.add(js)
            booking(browser, rep, w, h, lang, js, cfg["event"], control)
            guest(browser, rep, w, h, lang, js, cfg["token"])
        motion(browser, rep, cfg["event"])
    rep.finish("fb33 d6 select")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--setup"]
    OUT = args[0] if args else "/tmp/fb33_d6_select"
    if "--setup" in sys.argv:
        setup(OUT)
    else:
        main()
