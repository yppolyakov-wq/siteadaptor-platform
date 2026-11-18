"""FB-31: шаблон страницы → блоки страницы, общее ядро (стратегия §5).

Прежний код шаблона страницы (`promo_page_style` и т. п.) — готовый набор значений осей
блоков: вид шапки, вид навигации, вид ★ и т. д. Поверхность (`Surface`) описывает, в какой
строке схемы и в каком её поле живёт каждая ось и какой код какому набору соответствует.
Модуль чистый (без БД): вывод при чтении, старые конфиги читаются на лету, миграции нет.

* `from_code(surface, code)` — набор осей прежнего шаблона;
* `legacy_code(surface, parts)` — обратно в код (CSS/разметка, ключуемые кодом, — байт-в-байт);
* `rows_for` / `from_rows` — те же оси строками схемы страницы;
* `has_parts` — записаны ли оси строками явно;
* `effective(surface, cfg, host, code=…)` — код, поверх — оси, заданные строками хоста.

Первый образец — каталог (`apps/catalog/catalog_parts.py`, свой модуль до уборки P6); акции —
`apps/promotions/promo_parts.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType

MAIN_KEY = "main"


@dataclass(frozen=True)
class Axis:
    """Ось вида: строка схемы `key`, поле `field`; `values` — значения, отличные от обычного;
    `off` — как обычное значение записано в строке явно ("" — поля нет)."""

    name: str
    key: str
    values: tuple[str, ...]
    off: str = ""
    field: str = "style"

    def accepts(self, raw) -> bool:
        return isinstance(raw, str) and (raw in self.values or (bool(self.off) and raw == self.off))

    def value_of(self, raw) -> str:
        return "" if raw == self.off else raw


class Parts(tuple):
    """Неизменяемый набор осей: пары (ось, значение) по порядку осей поверхности."""

    def get(self, name: str) -> str:
        for axis, value in self:
            if axis == name:
                return value
        return ""

    def as_dict(self) -> dict[str, str]:
        return {axis: value for axis, value in self}

    def __getattr__(self, name: str) -> str:
        # только оси: `keys` и прочие служебные имена — как у кортежа (иначе dict() зациклится)
        if name.startswith("_") or name == "keys":
            raise AttributeError(name)
        return self.get(name)


@dataclass(frozen=True, eq=False)
class Surface:
    name: str
    axes: tuple[Axis, ...]
    codes: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    #: порядок осей, по которым ищется ближайший код для нового сочетания (главная — первой)
    priority: tuple[str, ...] = ()

    def parts(self, **values) -> Parts:
        known = {a.name for a in self.axes}
        bad = set(values) - known
        if bad:
            raise ValueError(f"{self.name}: unknown axes {sorted(bad)}")
        return Parts((a.name, values.get(a.name, "")) for a in self.axes)

    @property
    def standard(self) -> Parts:
        return self.parts()

    def axis(self, name: str) -> Axis:
        return next(a for a in self.axes if a.name == name)

    def keys(self) -> tuple[str, ...]:
        """Ключи строк поверхности без ★ (встроенные строки без id)."""
        out: list[str] = []
        for a in self.axes:
            if a.key != MAIN_KEY and a.key not in out:
                out.append(a.key)
        return tuple(out)


def surface(name: str, axes, codes: dict[str, dict], priority=()) -> Surface:
    s = Surface(name=name, axes=tuple(axes), priority=tuple(priority))
    table = {code: s.parts(**values) for code, values in codes.items()}
    if len(set(table.values())) != len(table):
        raise ValueError(f"{name}: two codes share one set of parts")
    object.__setattr__(s, "codes", MappingProxyType(table))
    return s


def from_code(s: Surface, code) -> Parts:
    """Оси прежнего шаблона; неизвестный код — обычный вид."""
    return s.codes.get(code if isinstance(code, str) else "", s.standard)


def legacy_code(s: Surface, parts: Parts) -> str:
    """Код для набора осей. Сочетание, которого прежде не было, — первый код, у которого
    совпадает значение главной оси (по `priority`), чтобы CSS-каскад нашёл правило."""
    for code, p in s.codes.items():
        if p == parts:
            return code
    for name in s.priority:
        value = parts.get(name)
        if not value:
            continue
        for code, p in s.codes.items():
            if p.get(name) == value:
                return code
    return ""


def rows_for(s: Surface, parts: Parts) -> list[dict]:
    """Оси строками схемы: строки по порядку ключей, ★ — последней (с полями вида)."""
    rows: list[dict] = []
    for key in s.keys():
        row: dict = {"key": key}
        for a in s.axes:
            if a.key == key:
                value = parts.get(a.name) or a.off
                if value:
                    row[a.field] = value
        rows.append(row)
    marker: dict = {"key": MAIN_KEY}
    for a in s.axes:
        if a.key == MAIN_KEY and parts.get(a.name):
            marker[a.field] = parts.get(a.name)
    if any(a.key == MAIN_KEY for a in s.axes):
        rows.append(marker)
    return rows


def _rows(rows) -> list[dict]:
    return [r for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict)]


def _row(rows: list[dict], key: str) -> dict | None:
    """Строка `key` (встроенная — без id); скрытая строка вида не задаёт (★ скрыть нельзя)."""
    row = next((r for r in rows if r.get("key") == key and not r.get("id")), None)
    if row is None or (key != MAIN_KEY and row.get("enabled") is False):
        return None
    return row


def _stored(s: Surface, rows: list[dict]) -> dict[str, str]:
    """Оси, заданные строками явно: {ось: значение} (мусор отбрасывается)."""
    out: dict[str, str] = {}
    for a in s.axes:
        row = _row(rows, a.key)
        if row is not None and a.field in row and a.accepts(row[a.field]):
            out[a.name] = a.value_of(row[a.field])
    return out


def from_rows(s: Surface, rows) -> Parts:
    return s.parts(**_stored(s, _rows(rows)))


def has_parts(s: Surface, rows) -> bool:
    return bool(_stored(s, _rows(rows)))


def effective(s: Surface, cfg, host: str, *, code: str = "") -> Parts:
    """Оси страницы: прежний код, поверх — оси, заданные сохранёнными строками хоста."""
    blocks = (cfg.get("page_blocks") or {}) if isinstance(cfg, dict) else {}
    rows = blocks.get(host) if isinstance(blocks, dict) else None
    return effective_rows(s, rows, code=code)


def effective_rows(s: Surface, rows, *, code: str = "") -> Parts:
    base = from_code(s, code).as_dict()
    base.update(_stored(s, _rows(rows)))
    return s.parts(**base)


# ───────── FB-31.7: перенос прежнего кода в строки ─────────


def materialize_rows(s: Surface, rows, code) -> list[dict] | None:
    """Строки, которые без кода дают тот же вид, что `rows` с кодом `code`:
    `effective_rows(s, new) == effective_rows(s, rows, code=code)`. Свои блоки, порядок и id
    не трогаются; недостающая строка оси встаёт перед ★ (★ без маркера — в начало: все блоки
    остаются под списком, как было). None — перенос невозможен без смены вида (скрытая
    строка, которую сейчас заменяет код) — решение владельца FB-31.7: такой сайт пропустить."""
    target = effective_rows(s, rows, code=code if isinstance(code, str) else "")
    return rows_with(s, rows, target)


def rows_with(s: Surface, rows, target: Parts, *, explicit: bool = False) -> list[dict] | None:
    """Строки `rows`, дающие оси `target` без кода. `explicit` (FB-31.7 B1b-2) — КАЖДАЯ ось
    записана строкой, даже совпадающая со «стандартом»: свой хост объекта лежит слоем поверх
    общих строк, и незаписанная ось после B3 пришла бы из них. None — как у materialize_rows."""
    import copy

    new = copy.deepcopy(_rows(rows))
    if not explicit and effective_rows(s, new) == target:
        return new
    lead = 0  # куда вставлять строки осей, если ★-маркера нет: в начало, по порядку осей
    for a in s.axes:
        want = target.get(a.name)
        stored = _stored(s, new)
        # ось уже такая: без `explicit` — по виду, с `explicit` — только если записана строкой
        if (a.name in stored if explicit else True) and from_rows(s, new).get(a.name) == want:
            continue
        row = next((r for r in new if r.get("key") == a.key and not r.get("id")), None)
        if row is not None and a.key != MAIN_KEY and row.get("enabled") is False:
            return None
        if row is None:
            row = {"key": a.key}
            marker = next(
                (i for i, r in enumerate(new) if r.get("key") == MAIN_KEY and not r.get("id")),
                None,
            )
            # ★ без маркера: блоки и так «под списком» — маркер перед ними это сохраняет
            at = marker if marker is not None and a.key != MAIN_KEY else lead
            new.insert(at, row)
            if marker is None:
                lead += 1
        value = want or a.off
        if value:
            row[a.field] = value
        else:
            row.pop(a.field, None)
    if effective_rows(s, new) != target:
        return None
    # каждая ось записана строкой; ось, которую строкой не записать (нет `off` при обычном
    # значении), после B3 пришла бы из общих строк — такой перенос не годится (ревью 2a)
    if explicit and any(a.name not in _stored(s, new) for a in s.axes):
        return None
    return new
