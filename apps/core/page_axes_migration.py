"""FB-31.7: перенос прежних кодов шаблонов страниц в строки-оси схемы «Seitenaufbau»
(`docs/fb31-7-materialize-plan-2026-11-16.md`).

Каждая поверхность переносится независимо и проверяется: вид страницы, вычисленный по
строкам БЕЗ кода, обязан совпасть с прежним видом (код + строки). Не совпал или перенос
невозможен (скрытая строка, которую сейчас заменяет код) — поверхность не трогается и
попадает в отчёт (решение владельца: допуск расхождений — ноль). Старые ключи остаются до
следующего релиза (решение владельца), поэтому витрина до сноса чтения кода видит то же.

Модуль чистый (без БД): на входе сырой `site_config`, на выходе новый и отчёт.
Срез B1a — девять страниц-списков (`page_styles`); остальные поверхности — следующими.
"""

from __future__ import annotations

import contextlib
import contextvars
import copy
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# FB-31.7 B1b-2: «вид после B3» — витрина не видит старых кодов шаблона у ОБЪЕКТОВ
# (Category/Promotion.page_style, promo_groups[*].style). Только сверка переноса и тесты.
_OBJECTS_BLIND: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "fb317_objects_blind", default=False
)


@contextlib.contextmanager
def objects_blind():
    token = _OBJECTS_BLIND.set(True)
    try:
        yield
    finally:
        _OBJECTS_BLIND.reset(token)


def is_objects_blind() -> bool:
    return _OBJECTS_BLIND.get()


#: итог одной поверхности
DONE, SAME, SKIP, MISMATCH = "done", "same", "skip", "mismatch"
RENDER_FAILED = "render-failed"
#: B1b-2: своим схемам не хватает места под потолком хостов — сайт не переносится
HOSTS_FULL = "hosts_full"


@dataclass
class Report:
    surfaces: dict[str, str] = field(default_factory=dict)
    #: B1b-2: заметки отчёта (`detached:<хост>`, `orphan:<группа>`, `purged:<n>`)
    notes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return any(v == DONE for v in self.surfaces.values())

    @property
    def mismatches(self) -> list[str]:
        # ревью B1b-1: сбой рендера сверки — тоже «сайт не перенесён», а не тишина
        return [
            k for k, v in self.surfaces.items() if v in (SKIP, MISMATCH, RENDER_FAILED, HOSTS_FULL)
        ]

    @property
    def busy(self) -> bool:
        return any(v == "busy" for v in self.surfaces.values())


def _listing_code(cfg: dict, surface: str) -> str:
    styles = cfg.get("page_styles") if isinstance(cfg, dict) else None
    code = styles.get(surface, "") if isinstance(styles, dict) else ""
    return code if isinstance(code, str) else ""


def _view(norm: dict, surface: str, host: str) -> tuple:
    """Всё, что видит посетитель от строк хоста листинга (ревью silent-failure B1a): свои
    блоки над и под ★, композиция страницы при всех гейтах данных (есть подразделы / нет,
    есть фото / нет), переводы своих блоков на каждом языке."""
    from apps.core import listing_composition
    from apps.tenants import siteconfig

    rows = (norm.get("page_blocks") or {}).get(host) or []
    above, below = siteconfig.split_at_main(rows)
    own = (
        tuple(r.get("id") for r in above if isinstance(r, dict) and r.get("id")),
        tuple(r.get("id") for r in below if isinstance(r, dict) and r.get("id")),
    )
    entry = [{"label": "x", "url": "?k=x", "active": False, "count": 1}]
    shelf = [{"label": "x", "slug": "x", "url": "?k=x", "total": 1, "items": []}]
    comps = []
    for entries in ([], entry):
        for photo in ("/media/x.jpg", ""):
            comps.append(
                listing_composition.context(
                    norm,
                    surface,
                    entries=entries,
                    shelves=shelf,
                    hero={"eyebrow": "", "text": "", "photo": photo},
                    carry="k",
                    kind="service",
                )
            )
    langs = []
    for loc in sorted((norm.get("i18n") or {}) if isinstance(norm.get("i18n"), dict) else {}):
        loc_rows = (siteconfig.localize(norm, loc).get("page_blocks") or {}).get(host) or []
        langs.append(
            (loc, tuple((r.get("id"), repr(r.get("data"))) for r in loc_rows if r.get("id")))
        )
    return own, repr(comps), tuple(langs)


def _with_host_rows(raw: dict, norm: dict, host: str, new_rows: list) -> dict:
    """Сырые настройки с новыми строками хоста `host` и переводами его блоков, выровненными по
    позициям (как в «Seitenaufbau»); остальные хосты и языки — байт-в-байт как были."""
    from apps.tenants import siteconfig

    out = raw
    blocks = copy.deepcopy(norm.get("page_blocks") or {})
    blocks[host] = new_rows
    # переводы блоков лежат по позициям — едут за своими блоками (как в «Seitenaufbau»)
    aligned = copy.deepcopy(norm)
    siteconfig.realign_block_overlays(aligned, new_page_blocks=blocks)
    # в сырые настройки — только этот хост и его переводы (ревью: остальные хосты и
    # языки остаются байт-в-байт как были, нормализация их не переписывает)
    candidate = copy.deepcopy(out)
    raw_blocks = candidate.get("page_blocks")
    raw_blocks = dict(raw_blocks) if isinstance(raw_blocks, dict) else {}
    raw_blocks[host] = new_rows
    candidate["page_blocks"] = raw_blocks
    for loc, layer in (aligned.get("i18n") or {}).items():
        moved = ((layer or {}).get("page_blocks") or {}).get(host)
        if moved is None:
            continue
        raw_i18n = candidate.setdefault("i18n", {})
        raw_layer = dict(raw_i18n.get(loc) or {})
        raw_pb = dict(raw_layer.get("page_blocks") or {})
        raw_pb[host] = moved
        raw_layer["page_blocks"] = raw_pb
        raw_i18n[loc] = raw_layer
    return candidate


def migrate_listings(raw: dict) -> tuple[dict, Report]:
    """Коды девяти листингов (`page_styles[surface]`) → строки хоста листинга. Сайт
    переносится целиком или не трогается (решение владельца: при любом расхождении)."""
    from apps.core import listing_parts
    from apps.core import page_parts as pp
    from apps.tenants import siteconfig

    report = Report()
    src = raw if isinstance(raw, dict) else {}
    out = copy.deepcopy(src)
    for surface in sorted(listing_parts.LISTINGS):
        norm = siteconfig.normalize(out)
        code = _listing_code(norm, surface)
        if not code:
            continue
        s = listing_parts.LISTINGS[surface]
        host = listing_parts.HOST_OF[surface]
        before = listing_parts.effective(norm, surface)
        rows = (norm.get("page_blocks") or {}).get(host) or []
        if pp.effective(s, norm, host) == before:
            report.surfaces[surface] = SAME  # строки уже задают тот же вид
            continue
        new_rows = pp.materialize_rows(s, rows, code)
        if new_rows is None:
            report.surfaces[surface] = SKIP
            continue
        candidate = _with_host_rows(out, norm, host, new_rows)
        after = siteconfig.normalize(candidate)
        no_code = copy.deepcopy(after)
        styles = dict(no_code.get("page_styles") or {})
        styles.pop(surface, None)
        no_code["page_styles"] = styles
        if (
            pp.effective(s, after, host) != before
            or listing_parts.effective(after, surface) != before
            or _view(no_code, surface, host) != _view(norm, surface, host)
            or _view(after, surface, host) != _view(norm, surface, host)
        ):
            report.surfaces[surface] = MISMATCH
            continue
        out = candidate
        report.surfaces[surface] = DONE
    if report.mismatches:
        return copy.deepcopy(src), report  # сайт не трогается целиком
    return out, report


# ───────── B1b-1: шаблоны страниц уровня сайта ─────────


def _old_code(cfg: dict, key: str) -> str:
    from apps.tenants import siteconfig

    _host, path = siteconfig.PAGE_TEMPLATE_HOSTS[key]
    node = cfg
    for part in path:
        node = node.get(part) if isinstance(node, dict) else None
    return node if isinstance(node, str) else ""


def _without_key(cfg: dict, key: str) -> dict:
    """Копия настроек без старого ключа шаблона (так их увидит витрина после B3)."""
    from apps.tenants import siteconfig

    _host, path = siteconfig.PAGE_TEMPLATE_HOSTS[key]
    out = copy.deepcopy(cfg)
    if len(path) == 1:
        out.pop(path[0], None)
    elif isinstance(out.get(path[0]), dict):
        out[path[0]].pop(path[1], None)
    return out


def template_rows(norm: dict, key: str) -> list | None:
    """Строки хоста шаблона `key`, которые без кода дают тот же вид, что код + строки; None —
    перенос невозможен без смены вида (скрытая строка «Kategorien», которую заменяет код)."""
    from apps.catalog import catalog_parts
    from apps.core import page_parts as pp
    from apps.tenants import siteconfig

    host, _path = siteconfig.PAGE_TEMPLATE_HOSTS[key]
    code = _old_code(norm, key)
    rows = siteconfig.page_rows(norm, host)
    if host in ("catalog", "category"):
        target = catalog_parts.effective(norm, host, code=code)
        cat = next((r for r in rows if r.get("key") == "categories" and not r.get("id")), None)
        if cat is not None and cat.get("enabled") is False:
            return None  # скрытую строку сейчас заменяет код — перенос сменил бы вид
        return catalog_parts.write_rows(rows, target, root=host == "catalog")
    return pp.materialize_rows(siteconfig._pp_surface(host), rows, code)


def migrate_templates(raw: dict, render=None) -> tuple[dict, Report]:
    """Шаблоны уровня сайта (`siteconfig.PAGE_TEMPLATE_HOSTS`) → строки их хостов. Старый ключ
    остаётся (решение владельца 4). Проверка: шаблон по строкам (со старым ключом и без него)
    тот же; `render(cfg, key) -> html | None` — та же отрисованная страница (None — страницы
    для сверки нет). Сайт переносится целиком или не трогается."""
    from apps.tenants import siteconfig

    report = Report()
    src = raw if isinstance(raw, dict) else {}
    out = copy.deepcopy(src)
    for key in sorted(siteconfig.PAGE_TEMPLATE_HOSTS):
        if key in siteconfig.OBJECT_BOUND_TEMPLATE_KEYS:
            continue  # B1b-2: переносится единицей вместе со своими кодами объектов
        norm = siteconfig.normalize(out)
        if not _old_code(norm, key):
            continue
        host, _path = siteconfig.PAGE_TEMPLATE_HOSTS[key]
        want = siteconfig.page_template_parts(norm, key)
        rows = template_rows(norm, key)
        if rows is None:
            report.surfaces[key] = SKIP
            continue
        candidate = _with_host_rows(out, norm, host, rows)
        after = siteconfig.normalize(candidate)
        stored = norm.get("page_blocks") or {}
        if host in stored and (after.get("page_blocks") or {}).get(host) == stored[host]:
            report.surfaces[key] = SAME  # строки уже задают этот вид
            continue
        bare = siteconfig.normalize(_without_key(candidate, key))
        # ревью B1b-1: сверка по ОСЯМ (код — лишь ближайшее имя набора осей)
        same = (
            siteconfig.page_template_parts(after, key) == want
            and siteconfig.page_template_parts(bare, key) == want
        )
        if same and render is not None:
            try:
                before_html = render(out, key)
                if before_html is not None:
                    same = (
                        render(candidate, key) == before_html
                        and render(_without_key(candidate, key), key) == before_html
                    )
            except Exception:  # noqa: BLE001 — сайт не переносится, отчёт говорит почему
                logger.exception("materialize_page_axes: render %s failed", key)
                report.surfaces[key] = RENDER_FAILED
                continue
        if not same:
            report.surfaces[key] = MISMATCH
            continue
        out = candidate
        report.surfaces[key] = DONE
    if report.mismatches:
        return copy.deepcopy(src), report
    return out, report


def migrate(raw: dict, render=None, objects=None) -> tuple[dict, Report]:
    """Все перенесённые поверхности: листинги (B1a), шаблоны уровня сайта (B1b-1) и свои
    шаблоны объектов (B1b-2, если передан `objects` — `page_axes_objects.ObjectIndex`). Сайт
    переносится целиком или не трогается."""
    src = copy.deepcopy(raw if isinstance(raw, dict) else {})
    out, report = migrate_listings(raw)
    if report.mismatches:
        return out, report
    out2, report2 = migrate_templates(out, render)
    report.surfaces.update(report2.surfaces)
    if report2.mismatches:
        return src, report
    if objects is not None:
        out3, report3 = migrate_objects(out2, objects, getattr(render, "at", None))
        report.surfaces.update(report3.surfaces)
        report.notes += report3.notes
        if report3.mismatches:
            return src, report
        return out3, report
    return out2, report


def migrate_objects(raw: dict, objects, render_at=None) -> tuple[dict, Report]:
    """B1b-2: единицы `page_axes_objects.UNITS` по очереди; каждая сверяется по осям (внутри
    единицы) и по отрисованным страницам: до == после == после без кодов объектов и без ключа
    «Alle Kategorien» (`objects_blind`). `render_at(cfg, path) -> html | None`."""
    from apps.core import page_axes_objects as pao

    report = Report()
    src = raw if isinstance(raw, dict) else {}
    out = copy.deepcopy(src)
    for name, unit in pao.UNITS:
        candidate, res = unit(out, objects)
        report.notes += [f"{name}:{n}" for n in res.notes]
        if not res.status:
            continue
        report.surfaces[name] = res.status
        if res.status != DONE:
            if res.status == SAME:
                continue
            return copy.deepcopy(src), report
        if render_at is not None:
            bare = _without_key(candidate, "category_page_style")
            try:
                for page in res.pages:
                    path = pao.page_url(name, page)
                    before_html = render_at(out, path)
                    if before_html is None:
                        continue
                    with objects_blind():
                        blind_html = render_at(bare, path)
                    if render_at(candidate, path) != before_html or blind_html != before_html:
                        report.surfaces[name] = MISMATCH
                        report.notes.append(f"{name}:render:{path}")
                        return copy.deepcopy(src), report
            except Exception:  # noqa: BLE001 — сайт не переносится, отчёт говорит почему
                logger.exception("materialize_page_axes: render %s failed", name)
                report.surfaces[name] = RENDER_FAILED
                return copy.deepcopy(src), report
        out = candidate
    return out, report


def templates_to_rows(raw: dict) -> dict:
    """FB-31.7 B1b (демо-киты и прочие сборщики конфига): старые ключи шаблонов уровня сайта
    → строки их хостов, ключ снимается. Вид тот же (строки = код + прежние строки); шаблон,
    который строками не выразить (скрытая строка «Kategorien»), остаётся ключом."""
    from apps.tenants import siteconfig

    out = copy.deepcopy(raw if isinstance(raw, dict) else {})
    for key in sorted(siteconfig.PAGE_TEMPLATE_HOSTS):
        if key in siteconfig.OBJECT_BOUND_TEMPLATE_KEYS:
            continue  # B1b-2: переносится единицей вместе со своими кодами объектов
        norm = siteconfig.normalize(out)
        if not _old_code(norm, key):
            continue
        host, _path = siteconfig.PAGE_TEMPLATE_HOSTS[key]
        rows = template_rows(norm, key)
        if rows is None:
            continue
        out = _without_key(_with_host_rows(out, norm, host, rows), key)
    return out


# ───────── сверка по отрисованной странице (B1b-1) ─────────

_CSRF = re.compile(r'(name="csrfmiddlewaretoken" value=")[^"]+')
_NONCE = re.compile(r'(nonce=")[^"]+')
#: одноразовые токены форм (`form_token`, `review_form_token`) — uuid4().hex на каждый показ
_TOKEN = re.compile(r"\b[0-9a-f]{32}\b")
#: B1b-2: метка редактора «чей хост держит блоки» — у отвязанной копии (D1) другая, посетитель
#: её не видит (только предпросмотр «Seitenaufbau»)
_PB_HOST = re.compile(r'(data-pb-host=")[^"]*')


def _page_path(cfg: dict, key: str) -> str:
    """Адрес страницы, по которой сверяется шаблон `key` (в схеме тенанта); "" — сверять
    нечего (нет записей). Берётся запись БЕЗ своего шаблона — её вид задаёт перенос."""
    from django.urls import reverse

    if key == "catalog_page_style":
        return reverse("storefront-products", urlconf="config.urls_tenant")
    if key == "promo_page_style":
        return reverse("storefront-aktionen", urlconf="config.urls_tenant")
    if key == "category_page_style":
        from apps.catalog.models import Category
        from apps.tenants import siteconfig

        own = {
            h
            for h in ((cfg.get("page_blocks") or {}) if isinstance(cfg, dict) else {})
            if str(h).startswith(siteconfig.CATEGORY_HOST_PREFIX)
        }
        for cat in Category.objects.filter(is_active=True, page_style="").order_by("pk")[:20]:
            if siteconfig.category_host(cat.slug) not in own:
                return reverse("storefront-category", args=[cat.slug], urlconf="config.urls_tenant")
        return ""
    from apps.promotions.models import Promotion

    live = Promotion.objects.filter(Promotion.on_sale_q())
    from apps.tenants import siteconfig

    blocks = (cfg.get("page_blocks") or {}) if isinstance(cfg, dict) else {}
    if key == "promo_detail_style":
        # ревью B1b-1: образец без своего шаблона И без своих строк — его вид задаёт перенос
        for promo in live.filter(page_style="").order_by("pk")[:20]:
            if not blocks.get(f"promo:{promo.pk.hex}"):
                return reverse(
                    "storefront-promotion", args=[promo.pk], urlconf="config.urls_tenant"
                )
        return ""
    if key == "promo_group_style":
        own = siteconfig.normalize_promo_groups((cfg or {}).get("promo_groups"))
        group = None
        for name in live.exclude(group="").order_by("group").values_list("group", flat=True):
            spec = own.get(name)
            has_style = (spec.get("style") if isinstance(spec, dict) else spec) or ""
            if not has_style and not blocks.get(siteconfig.promo_group_host(name)):
                group = name
                break
        if not group:
            return ""
        from urllib.parse import urlencode

        base = reverse("storefront-aktionen", urlconf="config.urls_tenant")
        return f"{base}?{urlencode({'gruppe': group})}"
    return ""


def renderer(tenant):
    """`render(cfg, key) -> html | None` для `migrate`: страница шаблона `key`, отрисованная
    витриной с настройками `cfg` (без записи в базу) в схеме тенанта."""
    import copy as _copy

    from django.contrib.auth.models import AnonymousUser
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory
    from django.urls import resolve
    from django_tenants.utils import schema_context

    def render(cfg, key):
        with schema_context(tenant.schema_name):
            path = _page_path(cfg, key)
        return at(cfg, path) if path else None

    def at(cfg, path):
        with schema_context(tenant.schema_name):
            fake = _copy.copy(tenant)
            fake.site_config = cfg
            request = RequestFactory().get(path)
            SessionMiddleware(lambda r: None).process_request(request)
            MessageMiddleware(lambda r: None).process_request(request)
            request.user = AnonymousUser()
            request.tenant = fake
            match = resolve(path.split("?")[0], urlconf="config.urls_tenant")
            response = match.func(request, *match.args, **match.kwargs)
            if hasattr(response, "render"):
                response.render()
            if response.status_code != 200:
                # ревью B1b-1: «404 до и 404 после» — не совпадение, а нечего сверять
                return None
            html = response.content.decode()
            html = _CSRF.sub(r"\1X", html)
            html = _NONCE.sub(r"\1X", html)
            html = _PB_HOST.sub(r"\1X", html)
            return _TOKEN.sub("TOKEN", html)

    render.at = at  # B1b-2: сверка страниц объектов по адресу
    return render


# ───────── запись в базу (команда `materialize_page_axes`) ─────────

REASON = "fb31.7-page-axes"
#: ключи настроек, которые меняет перенос (их и хранит снимок)
_TOUCHED = ("page_blocks", "i18n")


def config_hash(cfg) -> str:
    import hashlib
    import json

    raw = json.dumps(cfg or {}, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


#: откаченный владельцем сайт — тихо, без «ПРОПУЩЕНО» на каждом деплое
ROLLED_BACK = "rolled_back"
#: строка сайта занята дольше `LOCK_TIMEOUT` или менялась во время переноса — повтор на
#: следующем деплое
BUSY = "busy"
LOCK_TIMEOUT = "2s"
_ATTEMPTS = 3


def _lock(model, pk):
    """Строка под блокировкой, но не дольше `LOCK_TIMEOUT` (деплой не висит на занятом сайте)."""
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
    return model.objects.select_for_update().get(pk=pk)


def _object_index(tenant):
    from django_tenants.utils import schema_context

    from apps.core import page_axes_objects

    with schema_context(tenant.schema_name):
        return page_axes_objects.build_index()


def apply_tenant(tenant, *, dry_run: bool = False) -> Report:
    """Перенести коды одного сайта. Перенос считается БЕЗ блокировки; под блокировкой —
    только сверка «настройки не менялись» (иначе — заново) и одна запись со снимком."""
    from django.db import OperationalError, transaction

    from apps.tenants.models import SiteConfigSnapshot, Tenant

    if SiteConfigSnapshot.objects.filter(
        tenant_id=tenant.pk, reason=REASON, undone_at__isnull=False
    ).exists():
        return Report(surfaces={"*": ROLLED_BACK})  # владелец откатил — не повторяем

    for _attempt in range(_ATTEMPTS):
        row = Tenant.objects.filter(pk=tenant.pk).values_list("site_config", flat=True).first()
        if row is None and not Tenant.objects.filter(pk=tenant.pk).exists():
            return Report()  # сайт удалили во время прогона
        before = row or {}
        try:
            render = renderer(tenant)
        except Exception:  # noqa: BLE001 — без рендера сверка только по осям не годится
            logger.exception("materialize_page_axes: renderer for %s", tenant.schema_name)
            return Report(surfaces={"*": "render-failed"})
        try:
            objects = _object_index(tenant)
        except Exception:  # noqa: BLE001 — без данных объектов перенос объектов не годится
            logger.exception("materialize_page_axes: objects for %s", tenant.schema_name)
            return Report(surfaces={"*": "render-failed"})
        new, report = migrate(before, render=render, objects=objects)
        if not report.changed or dry_run:
            return report
        try:
            with transaction.atomic():
                written = _write(tenant, before, new)
        except OperationalError:  # строка занята дольше lock_timeout
            return Report(surfaces={"*": BUSY})
        if written is None:
            continue  # кабинет успел сохранить — считаем заново
        transaction.on_commit(lambda s=written: _bump(s))
        return report
    return Report(surfaces={"*": BUSY})


def _bump(schema: str) -> None:
    """Сброс кэша витрины после переноса; сбой — в лог, не сбой переноса (данные записаны)."""
    from apps.core.pagecache import bump_storefront_cache

    try:
        bump_storefront_cache(schema)
    except Exception:  # noqa: BLE001
        logger.warning("materialize_page_axes: cache bump failed for %s", schema, exc_info=True)


def _write(tenant, before: dict, new: dict) -> str | None:
    """Под блокировкой (внутри транзакции): настройки не менялись — записать и снять снимок,
    вернуть схему; менялись — None (перенос считается заново)."""
    from apps.tenants.models import SiteConfigSnapshot, Tenant

    locked = _lock(Tenant, tenant.pk)
    if config_hash(locked.site_config or {}) != config_hash(before):
        return None
    locked.site_config = new
    locked.save(update_fields=["site_config"])
    # хэш — после записи и чтения из базы (JSONB): откат сравнивает то же самое
    locked.refresh_from_db(fields=["site_config"])
    SiteConfigSnapshot.objects.create(
        tenant=locked,
        reason=REASON,
        # меняются только `page_blocks` и `i18n` — их и храним (снимок не раздувается)
        before={k: before.get(k) for k in _TOUCHED},
        after_hash=config_hash(locked.site_config or {}),
    )
    return locked.schema_name


def undo_tenant(tenant) -> str:
    """Откат последнего переноса: "undone" | "none" (нечего) | "changed" (настройки с тех пор
    меняли — не трогаем, решает владелец)."""
    from django.db import transaction
    from django.utils import timezone

    from apps.tenants.models import SiteConfigSnapshot, Tenant

    with transaction.atomic():
        locked = _lock(Tenant, tenant.pk)
        snap = (
            SiteConfigSnapshot.objects.select_for_update()
            .filter(tenant=locked, reason=REASON, undone_at__isnull=True)
            .order_by("-created_at", "-id")
            .first()
        )
        if snap is None:
            return "none"
        if config_hash(locked.site_config or {}) != snap.after_hash:
            return "changed"
        restored = dict(locked.site_config or {})
        for key in _TOUCHED:
            old = (snap.before or {}).get(key)
            if old is None:
                restored.pop(key, None)
            else:
                restored[key] = old
        locked.site_config = restored
        locked.save(update_fields=["site_config"])
        snap.undone_at = timezone.now()
        snap.save(update_fields=["undone_at"])
        transaction.on_commit(lambda s=locked.schema_name: _bump(s))
    return "undone"
