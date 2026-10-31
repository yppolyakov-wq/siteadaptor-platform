"""M21.1: переадресации со старых адресов (переезд с другой платформы).

Правило (``core.LegacyRedirect``) срабатывает только на ответе 404 витрины —
см. ``LegacyRedirectMiddleware``. Здесь — нормализация адресов, подбор правила,
проверка цели и CSV. План — ``docs/m21-cscart-migration-plan-2026-10-31.md``.

Подбор: среди правил того же пути выигрывает самое специфичное, чьи параметры
целиком содержатся в запросе. Так правило ``/index.php`` +
``dispatch=products.view&product_id=800`` ловит и
``/index.php?dispatch=products.view&product_id=800&sl=de``, а правило без
параметров — любой query этого пути.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.models import LegacyRedirect

MAX_LEN = 500
CSV_MAX_BYTES = 1024 * 1024
CSV_MAX_ROWS = 5000


class RedirectError(ValueError):
    """Неверный источник/цель правила (текст — для владельца)."""


def _no_control(value: str) -> bool:
    return not any(ord(ch) < 32 or ord(ch) == 127 for ch in value)


def normalize_path(raw: str) -> str:
    """«/Fruchtetee/Apfeltees/» → «/fruchtetee/apfeltees»; корень остаётся «/»."""
    path = unquote(raw or "").strip()
    if not path.startswith("/"):
        path = "/" + path
    path = path.lower()
    while len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return path


def canonical_query(raw: str) -> str:
    """Параметры по алфавиту (ключ, значение); пустые ключи отброшены."""
    pairs = sorted((k, v) for k, v in parse_qsl(raw or "", keep_blank_values=True) if k)
    return urlencode(pairs)


def parse_source(text: str) -> tuple[str, str]:
    """Полный адрес старого сайта или путь (с query) → (путь, канон. query)."""
    text = (text or "").strip()
    if not text or not _no_control(text) or "\\" in text:
        raise RedirectError(_("Ungültige alte Adresse."))
    try:
        parts = urlsplit(text)
    except ValueError as exc:  # «http://[» — незакрытый IPv6 → не 500, а отказ строки
        raise RedirectError(_("Ungültige alte Adresse.")) from exc
    if parts.scheme and parts.scheme not in ("http", "https"):
        raise RedirectError(_("Ungültige alte Adresse."))
    path = normalize_path(parts.path)
    query = canonical_query(parts.query)
    if len(path) > MAX_LEN or len(query) > MAX_LEN:
        raise RedirectError(_("Die Adresse ist zu lang."))
    return path, query


def clean_target(text: str) -> str:
    """Цель — только локальный путь этого сайта (без чужих хостов, `//`, `\\`)."""
    target = (text or "").strip()
    if (
        not target.startswith("/")
        or target.startswith("//")
        or "\\" in target
        or not _no_control(target)
        or len(target) > MAX_LEN
        or urlsplit(target).scheme
        or urlsplit(target).netloc
    ):
        raise RedirectError(_("Das Ziel muss eine Adresse dieser Website sein, z. B. /sortiment/."))
    return target


def upsert(
    source: str, target: str = "", *, status: int = LegacyRedirect.STATUS_MOVED, origin="manual"
) -> tuple[LegacyRedirect, bool]:
    """Создать или обновить правило. 410 — без цели; 301 — с локальной целью."""
    path, query = parse_source(source)
    if status not in (LegacyRedirect.STATUS_MOVED, LegacyRedirect.STATUS_GONE):
        raise RedirectError(_("Ungültiger Status."))
    if status == LegacyRedirect.STATUS_GONE:
        target = ""
    else:
        target = clean_target(target)
        tparts = urlsplit(target)
        if normalize_path(tparts.path) == path and canonical_query(tparts.query) == query:
            raise RedirectError(_("Alte und neue Adresse sind gleich."))
    obj, created = LegacyRedirect.objects.update_or_create(
        source_path=path,
        source_query=query,
        defaults={"target": target, "status": status, "origin": origin},
    )
    return obj, created


def match(path: str, query: str) -> LegacyRedirect | None:
    """Самое специфичное правило пути, чьи параметры ⊆ параметров запроса."""
    norm = normalize_path(path)
    rules = list(
        LegacyRedirect.objects.filter(source_path=norm).only(
            "id", "source_query", "target", "status"
        )
    )
    if not rules:
        return None
    have = set(parse_qsl(query or "", keep_blank_values=True))
    best, best_size = None, -1
    for rule in rules:
        need = set(parse_qsl(rule.source_query, keep_blank_values=True))
        if need <= have and len(need) > best_size:
            best, best_size = rule, len(need)
    return best


def record_hit(rule: LegacyRedirect) -> None:
    LegacyRedirect.objects.filter(pk=rule.pk).update(hits=F("hits") + 1, last_hit_at=timezone.now())


@dataclass
class CsvResult:
    created: int = 0
    updated: int = 0
    errors: list = field(default_factory=list)


def _status_of(raw: str) -> int:
    raw = (raw or "").strip()
    if raw in ("", "301"):
        return LegacyRedirect.STATUS_MOVED
    if raw == "410":
        return LegacyRedirect.STATUS_GONE
    raise RedirectError(_("Ungültiger Status."))


def import_csv(raw: bytes, *, origin="manual") -> CsvResult:
    """CSV «alte Adresse;neue Adresse[;Status]» (Trenner «;» или «,», шапка необязательна)."""
    result = CsvResult()
    if len(raw) > CSV_MAX_BYTES:
        result.errors.append(_("Die Datei ist zu groß (max. 1 MB)."))
        return result
    text = raw.decode("utf-8-sig", errors="replace")
    delimiter = ";" if text.count(";") >= text.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    if len(rows) > CSV_MAX_ROWS + 1:
        result.errors.append(_("Zu viele Zeilen (max. 5000)."))
        return result
    with transaction.atomic():
        for n, row in enumerate(rows, start=1):
            cells = [c.strip() for c in row]
            if not cells or not any(cells):
                continue
            if n == 1 and not cells[0].startswith(("/", "http")):
                continue  # шапка
            try:
                status = _status_of(cells[2] if len(cells) > 2 else "")
                target = cells[1] if len(cells) > 1 else ""
                _obj, created = upsert(cells[0], target, status=status, origin=origin)
            except RedirectError as exc:
                result.errors.append(
                    _("Zeile %(n)s: %(msg)s") % {"n": n, "msg": exc}  # noqa: UP031
                )
                continue
            if created:
                result.created += 1
            else:
                result.updated += 1
    return result


def export_csv(qs) -> str:
    """CSV тем же форматом, что импорт (+ хиты). Формулы Excel нейтрализуем."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["alte_adresse", "neue_adresse", "status", "aufrufe"])
    for r in qs:
        source = r.source_path + (f"?{r.source_query}" if r.source_query else "")
        writer.writerow([_safe_cell(source), _safe_cell(r.target), r.status, r.hits])
    return buf.getvalue()


def _safe_cell(value: str) -> str:
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value
