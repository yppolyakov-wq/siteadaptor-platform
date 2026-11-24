"""FB-33 M5c: замер «до/после» стопки 11 — что срезы M5c не задевают (план стопки 11 §1 п.4, §3).

Метод — стопки 10 §8.7 (тот скрипт жил в scratchpad и потерялся; этот — в репозитории и
остаётся для стопки 12). Без браузера и без сервера: `django.test.Client` в процессе, под
владельцем бизнеса (сессия в кэше, без сигнала входа — `fb33_m5d_inventory.owner_client`;
сессия удаляется в `finally`). Страницы — как у стенда владельца и инвентаризации M5d:
все коды `site_schema.type_groups` + первый объект каждого вида (`schema_pages`).

По каждой странице (`--json <файл>`):

- **(а) витрина** — sha256 ответа `PageRow.preview_url` каждого хоста: анонимно, но с непустой
  сессией (мимо кэша страниц `pagecache`), без значений `csrfmiddlewaretoken`, `form_token`
  и `nonce`;
- **(б) site_config** — sha256 текста `site_config` бизнеса (как его хранит Postgres) до и после
  POST `op=save` без правок: без черновика (`save_plain`) и с черновиком «выше + ниже»
  (`save_updown`, нетто без изменений). Всё — в транзакции с откатом: в базе ничего не остаётся;
  постановка задач Celery на это время глушится (имена задач — в отчёт);
- **(в) вставка** — `items` черновика после POST `op=add` (тип `text`) без `after` и с
  `after=<ref второго блока>`; понял ли сервер `after` — фактом (`honored`: новый блок сразу за
  целью); после каждой — `op=discard`;
- **(г) SQL** — запросов на GET экрана «Seitenaufbau» (`?seite=<код>`), на POST `op=up` и
  `op=add`, и одного `site_schema.blocks_for` в процессе (допуск POST);
- **(д) разметка** — значения `data-schema-block` и число рядов схемы (`data-schema-row`) и
  других меток строк (только печать — срезы меняют их намеренно).

Запуск — только настройки стенда и стенд-БД (`…_stand`, иначе выход):

    DB_NAME=platform_meas_stand uv run python scripts/fb33_m5c_measure.py --json after.json \\
        [--only shop,friseur] [--sample 10]
    # тем же скриптом — старый код (папка `git archive <база> | tar -x -C <папка>`):
    DB_NAME=platform_meas_stand uv run python scripts/fb33_m5c_measure.py \\
        --code <папка> --json before.json
    uv run python scripts/fb33_m5c_measure.py --compare before.json after.json [--sql-slack N]

`--code` перезапускает скрипт тем же интерпретатором (тот же `.venv`) с `cwd=<папка>` и кодом
приложения из неё (`PYTHONPATH`, `M5C_MEASURE_CODE`); недостающие `.mo` папки собираются polib-ом.
`--sample N` — N страниц бизнеса, равномерно по списку (детерминированно, объекты тоже попадают).

Сверка (`--compare`): (а) хэши витрины — все равны; (б) `site_config` — байт в байт (`after`
каждого сохранения; `before` двух файлов разные — значит, мерили на разных БД); (в) `items`
вставки без `after` — равны по ключу/данным/позиции (новый id — `<new>`); (г) SQL экрана —
±`--screen-slack` (1), POST — не больше базы + `--sql-slack` (по умолчанию — SQL одного
`blocks_for` этой страницы на базе); (д) — печать. Код выхода 1 — есть расхождения (а)–(г).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve()
#: корень кода приложения: свой репозиторий или папка `--code` (переменная ставится перезапуском)
ROOT = Path(os.environ.get("M5C_MEASURE_CODE") or SCRIPT.parents[1]).resolve()
AUFBAU = "/dashboard/site/aufbau/"
#: поддомены пяти китов стенда владельца — как `fb33_m5d_inventory.DEFAULT_SLUGS`
DEFAULT_SLUGS = ("shop", "restaurant-demo", "friseur", "hotel", "retreat")
ADD_TYPE = "text"
#: допуск SQL экрана: два прогона базы подряд плавают на ±1 (стопка 10 §8.7)
SCREEN_SLACK = 1
NEW_ID = "<new>"

#: значения, которые меняются от запроса к запросу (замок `test_fb33_m5c_measure.py`)
_VOLATILE = (
    re.compile(r'(name="(?:csrfmiddlewaretoken|form_token)"[^>]*?\bvalue=")[^"]*(")'),
    re.compile(r'(\bvalue=")[^"]*("[^>]*?name="(?:csrfmiddlewaretoken|form_token)")'),
    re.compile(r'(\bnonce=")[^"]*(")'),
)
_BLOCK = re.compile(r'\bdata-schema-block="([^"]*)"')
#: метки строк схемы в разметке экрана (имена атрибутов шаблона `tenant/site_schema.html`)
_MARKS = ("row", "drag", "pinned", "shared", "hidden", "title-hint", "add")


# --- чистые функции: разметка ---------------------------------------------------------------


def strip_volatile(html: str) -> str:
    """Разметка без значений, которые меняются от запроса к запросу."""
    for rx in _VOLATILE:
        html = rx.sub(r"\1\2", html)
    return html


def page_sha(html: str) -> str:
    return hashlib.sha256(strip_volatile(html).encode("utf-8")).hexdigest()


def schema_marks(html: str) -> dict:
    """(д): значения `data-schema-block` по порядку и число меток строк схемы."""
    counts = {m: len(re.findall(rf"\bdata-schema-{re.escape(m)}\b(?!-)", html)) for m in _MARKS}
    return {"blocks": _BLOCK.findall(html), "rows": counts["row"], "counts": counts}


def norm_items(items, known) -> list[dict]:
    """`items` черновика для сверки: id, которого не было до вставки (`known` — ref строк
    страницы), — `<new>`."""
    out = []
    for pos, it in enumerate(items or []):
        it = dict(it) if isinstance(it, dict) else {"raw": it}
        if it.get("id") and it["id"] not in known:
            it["id"] = NEW_ID
        out.append({"pos": pos, **it})
    return out


def inserted_at(items, known) -> int | None:
    """Индекс нового блока (id не из `known`), None — вставки нет."""
    for i, it in enumerate(items or []):
        if isinstance(it, dict) and it.get("id") and it["id"] not in known:
            return i
    return None


def _ref(it) -> str:
    return (it.get("id") or it.get("key") or "") if isinstance(it, dict) else ""


def after_honored(items, known, target: str) -> bool | None:
    """Понял ли сервер `after`: новый блок сразу за `target`. None — не различить (цель —
    последний блок, вставка в хвост дала бы то же) или вставки нет."""
    at = inserted_at(items, known)
    if at is None:
        return None
    rest = [_ref(it) for i, it in enumerate(items) if i != at]
    if rest and rest[-1] == target and at == len(items) - 1:
        return None
    return at > 0 and _ref(items[at - 1]) == target


def _after_target(own: list[dict], tail_items: list[dict]) -> str:
    """Цель `after`: ref второго блока, а если он последний в `items` — первого (иначе вставку
    в хвост не отличить от вставки за целью); «» — блоков меньше двух."""
    refs = [b["ref"] for b in own]
    last = next((_ref(it) for it in reversed(tail_items) if it.get("id") != NEW_ID), "")
    for ref in refs[1:2] + refs[:1]:
        if len(refs) > 1 and ref != last and any(_ref(it) == ref for it in tail_items):
            return ref
    return refs[1] if len(refs) > 1 else ""


def sample(rows: list, n: int) -> list:
    """N строк равномерно по списку (детерминированно); 0 — все."""
    if not n or n >= len(rows):
        return list(rows)
    step = len(rows) / n
    return [rows[int(i * step)] for i in range(n)]


# --- чистые функции: сверка -----------------------------------------------------------------


def compare(before: dict, after: dict, *, sql_slack: int | None = None, screen_slack=SCREEN_SLACK):
    """Расхождения «до» → «после» по разделам a–d (каждый — список строк) и печать «e».

    `sql_slack=None` — допуск POST равен SQL одного `blocks_for` этой страницы на базе."""
    out = {"a": [], "b": [], "c": [], "d": [], "e": [], "missing": []}
    fb, fa = before.get("storefront", {}), after.get("storefront", {})
    for key in sorted(set(fb) | set(fa)):
        b, a = fb.get(key), fa.get(key)
        if b is None or a is None:
            out["missing"].append(f"витрина {key}: только в «{'до' if a is None else 'после'}»")
        elif (b.get("status"), b.get("sha256")) != (a.get("status"), a.get("sha256")):
            out["a"].append(
                f"витрина {key}: {b.get('status')} {str(b.get('sha256'))[:12]} → "
                f"{a.get('status')} {str(a.get('sha256'))[:12]}"
            )
    pb, pa = before.get("pages", {}), after.get("pages", {})
    for key in sorted(set(pb) | set(pa)):
        b, a = pb.get(key), pa.get(key)
        if b is None or a is None:
            out["missing"].append(f"страница {key}: только в «{'до' if a is None else 'после'}»")
            continue
        if b.get("skipped") or a.get("skipped"):
            if b.get("skipped") != a.get("skipped"):
                out["d"].append(f"{key}: пропуск {b.get('skipped')!r} → {a.get('skipped')!r}")
            continue
        _compare_page(key, b, a, out, sql_slack, screen_slack)
    return out


def _compare_page(key, b, a, out, sql_slack, screen_slack) -> None:
    for name in ("save_plain", "save_updown"):
        sb, sa = b.get(name) or {}, a.get(name) or {}
        if sb.get("before") != sa.get("before"):
            out["missing"].append(f"{key} {name}: site_config до разный — разные БД?")
        if sb.get("after") != sa.get("after"):
            out["b"].append(
                f"{key} {name}: site_config после «Speichern» "
                f"{str(sb.get('after'))[:12]} → {str(sa.get('after'))[:12]}"
            )
    tb, ta = b.get("add_tail") or {}, a.get("add_tail") or {}
    if tb.get("items") != ta.get("items"):
        out["c"].append(
            f"{key}: items после add без after разные "
            f"(новый блок {tb.get('new_index')} → {ta.get('new_index')})"
        )
    ab, aa = b.get("add_after") or {}, a.get("add_after") or {}
    if ab.get("honored") != aa.get("honored"):
        out["e"].append(
            f"{key}: add after={aa.get('target')}: понят {ab.get('honored')} → {aa.get('honored')}"
        )
    sb, sa = (b.get("screen") or {}).get("sql"), (a.get("screen") or {}).get("sql")
    if sb is not None and sa is not None and abs(sa - sb) > screen_slack:
        out["d"].append(f"{key}: SQL экрана {sb} → {sa} (допуск ±{screen_slack})")
    slack = max(b.get("blocks_for_sql") or 0, 1) if sql_slack is None else sql_slack
    for name in ("up", "add_tail"):
        qb, qa = (b.get(name) or {}).get("sql"), (a.get(name) or {}).get("sql")
        if qb is not None and qa is not None and qa > qb + slack:
            out["d"].append(f"{key}: SQL POST {name} {qb} → {qa} (допуск +{slack})")
    mb, ma = (b.get("screen") or {}).get("marks"), (a.get("screen") or {}).get("marks")
    if mb != ma:
        out["e"].append(f"{key}: разметка {_marks_diff(mb or {}, ma or {})}")


def _marks_diff(mb: dict, ma: dict) -> str:
    parts = []
    if mb.get("blocks") != ma.get("blocks"):
        parts.append(f"data-schema-block {mb.get('blocks')} → {ma.get('blocks')}")
    cb, ca = mb.get("counts") or {}, ma.get("counts") or {}
    for m in sorted(set(cb) | set(ca)):
        if cb.get(m) != ca.get(m):
            parts.append(f"{m} {cb.get(m)} → {ca.get(m)}")
    return "; ".join(parts) or "—"


SECTIONS = {
    "a": "(а) витрина: хэши",
    "b": "(б) site_config после «Speichern» без правок",
    "c": "(в) items после add без after",
    "d": "(г) SQL",
    "e": "(д) разметка схемы и факты (только печать)",
    "missing": "нет пары / разные БД",
}


def report(diff: dict) -> tuple[str, bool]:
    """Текст сверки и «чисто ли» по (а)–(г) и парам."""
    lines, clean = [], True
    for sec, title in SECTIONS.items():
        rows = diff.get(sec) or []
        if sec != "e" and rows:
            clean = False
        lines.append(f"## {title}: {'чисто' if not rows else len(rows)}")
        lines += [f"- {r}" for r in rows]
    lines.append("")
    lines.append("Итог: чисто." if clean else "Итог: есть расхождения.")
    return "\n".join(lines) + "\n", clean


# --- прогон (Django поднят) -------------------------------------------------------------------


@contextlib.contextmanager
def _no_celery(sent: list):
    """Задачи Celery не уходят в брокер (запись откатывается); имена — в отчёт."""
    from celery.app.task import Task

    orig = Task.apply_async

    def fake(self, *args, **kwargs):
        sent.append(self.name)

    Task.apply_async = fake
    try:
        yield
    finally:
        Task.apply_async = orig


def _sql(fn):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as ctx:
        result = fn()
    return result, len(ctx.captured_queries)


def _config_sha(tenant) -> str:
    from django.db import connection

    table = connection.ops.quote_name(type(tenant)._meta.db_table)
    with connection.cursor() as cur:
        cur.execute(f"SELECT site_config::text FROM public.{table} WHERE id = %s", [tenant.pk])
        row = cur.fetchone()
    return hashlib.sha256((row[0] or "").encode("utf-8")).hexdigest()


def _items(client, code: str) -> list:
    draft = (client.session.get("aufbau_draft") or {}).get(code) or {}
    return list(draft.get("items") or [])


def _post(client, code: str, **data):
    return client.post(AUFBAU, {"seite": code, **data})


def storefront(host: str, urls) -> dict:
    """(а): {url: {status, sha256, length, location}} анонимно, с непустой сессией."""
    from django.conf import settings
    from django.test import Client

    client = Client(HTTP_HOST=host)
    session = client.session
    session["fb33_m5c_measure"] = 1  # непустая сессия — мимо кэша страниц
    session.save()
    client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
    out = {}
    try:
        for url in urls:
            try:
                resp = client.get(url)
            except Exception as exc:  # noqa: BLE001 — сбой страницы виден строкой
                out[url] = {"status": None, "sha256": f"{type(exc).__name__}: {exc}"}
                continue
            body = resp.content.decode("utf-8", "replace")
            out[url] = {
                "status": resp.status_code,
                "sha256": page_sha(body),
                "length": len(body),
                "location": resp.get("Location", ""),
            }
    finally:
        client.session.delete()
    return out


def measure_page(tenant, client, saved, row) -> dict:
    """(б)–(д) одной страницы; записи — в транзакции с откатом."""
    from django.db import transaction

    from apps.core import site_schema

    code = row.code
    page: dict = {"code": code, "host": row.host or "", "preview_url": row.preview_url}
    resp, n = _sql(lambda: client.get(AUFBAU, {"seite": code}))
    html = resp.content.decode("utf-8", "replace")
    page["screen"] = {"status": resp.status_code, "sql": n, "marks": schema_marks(html)}
    if resp.status_code != 200:
        page["skipped"] = f"экран: ответ {resp.status_code}"
        return page
    blocks, page["blocks_for_sql"] = _sql(
        lambda: site_schema.blocks_for(saved, code, host=row.host or None, tenant=tenant)
    )
    own = [b for b in blocks if not b.get("shared")]
    sent: list[str] = []
    try:
        with _no_celery(sent), transaction.atomic():
            base = {b["ref"] for b in blocks}  # id и ключи строк до вставки
            # (в) + (г): add без after (SQL) → discard
            r, n = _sql(lambda: _post(client, code, op="add", type=ADD_TYPE))
            items = _items(client, code)
            page["add_tail"] = {
                "status": r.status_code,
                "sql": n,
                "new_index": inserted_at(items, base),
                "items": norm_items(items, base),
            }
            _post(client, code, op="discard")
            # (в): add с after=<ref второго блока>; старый сервер поле не знает — факт
            target = _after_target(own, page["add_tail"]["items"])
            if target:
                r = _post(client, code, op="add", type=ADD_TYPE, after=target)
                items = _items(client, code)
                page["add_after"] = {
                    "target": target,
                    "status": r.status_code,
                    "new_index": inserted_at(items, base),
                    "honored": after_honored(items, base, target),
                    "items": norm_items(items, base),
                }
                _post(client, code, op="discard")
            # (б): «Speichern» без черновика
            sha0 = _config_sha(tenant)
            _post(client, code, op="save")
            page["save_plain"] = {"before": sha0, "after": _config_sha(tenant)}
            page["save_plain"]["same"] = page["save_plain"]["after"] == sha0
            # (г) + (б): up (SQL), down — нетто без правок, затем «Speichern»
            mover = next((b for b in own if b.get("can_up")), None)
            if mover is not None:
                r, n = _sql(lambda: _post(client, code, op="up", ref=mover["ref"]))
                page["up"] = {"ref": mover["ref"], "status": r.status_code, "sql": n}
                _post(client, code, op="down", ref=mover["ref"])
                # черновик, равный сохранённому, экран не держит — «Speichern» идёт без него
                page["up"]["draft_after_down"] = bool(_items(client, code))
                _post(client, code, op="save")
                page["save_updown"] = {"before": sha0, "after": _config_sha(tenant)}
                page["save_updown"]["same"] = page["save_updown"]["after"] == sha0
            transaction.set_rollback(True)
    finally:
        _post(client, code, op="discard")
    page["tasks"] = sorted(set(sent))
    return page


def _inventory():
    """`fb33_m5d_inventory` рядом с этим скриптом (не из папки `--code`): вход владельца и
    перечень страниц — одни на оба прогона."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "fb33_m5d_inventory", SCRIPT.parent / "fb33_m5d_inventory.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(slugs, n_sample: int = 0, log=sys.stderr) -> dict:
    """Прогон по поддоменам китов на текущей БД."""
    from django.db import connection

    from apps.tenants import siteconfig
    from apps.tenants.models import Domain, Tenant

    inv = _inventory()
    result: dict = {"pages": {}, "storefront": {}, "skipped": []}
    for slug in slugs:
        connection.set_schema_to_public()
        tenant = Tenant.objects.filter(slug=slug).first()
        if tenant is None:
            result["skipped"].append(f"{slug}: нет бизнеса")
            continue
        host = (
            Domain.objects.filter(tenant=tenant, is_primary=True)
            .values_list("domain", flat=True)
            .first()
        )
        connection.set_tenant(tenant)
        client = None
        try:
            saved = siteconfig.normalize(tenant.site_config)
            rows = sample(inv.schema_pages(tenant, saved), n_sample)
            urls = list(dict.fromkeys(r.preview_url for r in rows if r.preview_url))
            t0 = time.monotonic()
            for url, val in storefront(host, urls).items():
                result["storefront"][f"{slug}|{url}"] = val
            print(f"{slug}: витрина {len(urls)} за {time.monotonic() - t0:.0f} с", file=log)
            connection.set_tenant(tenant)
            client = inv.owner_client(tenant, host)
            t0 = time.monotonic()
            for row in rows:
                connection.set_tenant(tenant)
                key = f"{slug}|{row.code}"
                try:
                    result["pages"][key] = {"kit": slug, **measure_page(tenant, client, saved, row)}
                except Exception as exc:  # noqa: BLE001 — сбой одной страницы виден строкой
                    result["pages"][key] = {
                        "kit": slug,
                        "code": row.code,
                        "skipped": f"{type(exc).__name__}: {exc}",
                    }
            print(f"{slug}: страниц {len(rows)} за {time.monotonic() - t0:.0f} с", file=log)
        except Exception as exc:  # noqa: BLE001 — бизнес не прошёл целиком: видно строкой
            result["skipped"].append(f"{slug}: {type(exc).__name__}: {exc}")
        finally:
            if client is not None:  # сессия владельца не остаётся в кэше
                client.session.delete()
            connection.set_schema_to_public()
    return result


def _build_mo(root: Path) -> None:
    """`.mo` в папке кода (в `git archive` их нет) — polib, как бриф исполнителя."""
    import polib

    for po in sorted(root.glob("locale/*/LC_MESSAGES/django.po")):
        mo = po.with_suffix(".mo")
        if not mo.exists():
            polib.pofile(str(po)).save_as_mofile(str(mo))
            print(f"собран {mo}", file=sys.stderr)


def _rerun(code_dir: str, argv: list[str]) -> int:
    root = Path(code_dir).resolve()
    if not (root / "manage.py").exists():
        sys.exit(f"--code: в {root} нет manage.py")
    _build_mo(root)
    rest, skip = [], False
    for a in argv:
        if skip:
            skip = False
            continue
        if a == "--code":
            skip = True
            continue
        if a.startswith("--code="):
            continue
        rest.append(a)
    # путь `--json` — от текущей папки, а не от папки кода
    for i, a in enumerate(rest):
        if i and rest[i - 1] == "--json":
            rest[i] = str(Path(a).resolve())
        elif a.startswith("--json="):
            rest[i] = "--json=" + str(Path(a.split("=", 1)[1]).resolve())
    env = {
        **os.environ,
        "M5C_MEASURE_CODE": str(root),
        "PYTHONPATH": os.pathsep.join([str(root), os.environ.get("PYTHONPATH", "")]).rstrip(
            os.pathsep
        ),
    }
    return subprocess.call([sys.executable, str(SCRIPT), *rest], cwd=str(root), env=env)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", default="", help="поддомены китов через запятую")
    ap.add_argument("--sample", type=int, default=0, help="N страниц бизнеса (0 — все)")
    ap.add_argument("--json", default="", help="куда записать замер (JSON)")
    ap.add_argument("--code", default="", help="папка со старым кодом (git archive)")
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    ap.add_argument("--sql-slack", type=int, default=None, help="допуск SQL POST")
    ap.add_argument("--screen-slack", type=int, default=SCREEN_SLACK, help="допуск SQL экрана")
    args = ap.parse_args(argv)
    if args.compare:
        before, after = (json.loads(Path(p).read_text(encoding="utf-8")) for p in args.compare)
        text, clean = report(
            compare(before, after, sql_slack=args.sql_slack, screen_slack=args.screen_slack)
        )
        sys.stdout.write(text)
        return 0 if clean else 1
    if args.code:
        return _rerun(args.code, argv)
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.stand")
    if os.environ["DJANGO_SETTINGS_MODULE"] != "config.settings.stand":
        sys.exit("замер — только на настройках стенда (config.settings.stand)")
    import django

    django.setup()
    from django.conf import settings

    db = settings.DATABASES["default"]["NAME"]
    if not str(db).endswith("_stand"):
        sys.exit(f"замер — только на стенд-БД (…_stand), а DB_NAME={db}")
    slugs = [s for s in args.only.split(",") if s] or list(DEFAULT_SLUGS)
    t0 = time.monotonic()
    result = run(slugs, args.sample)
    from apps.core import site_schema

    result["meta"] = {
        "code": str(ROOT),
        "site_schema": site_schema.__file__,  # откуда на деле взят код приложения
        "db": db,
        "kits": slugs,
        "sample": args.sample,
        "seconds": round(time.monotonic() - t0, 1),
    }
    if args.json:
        Path(args.json).write_text(
            json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
        )
    pages = result["pages"].values()
    print(
        f"страниц {len(result['pages'])} (пропущено {sum(1 for p in pages if p.get('skipped'))}),"
        f" витрин {len(result['storefront'])}, за {result['meta']['seconds']} с;"
        f" add after понят: {sum(1 for p in pages if (p.get('add_after') or {}).get('honored'))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
