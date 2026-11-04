"""FLT-4b: строка фильтров списка кабинета — поиск, «Filter · N», сортировка, пилюли, шторка.

Описание фильтров — данные (`Field`), значения — уже очищенные вьюхой (белые списки живут
у владельца списка, напр. `finance.invoice_list`). Здесь только состояние адреса:
- пилюля «✕» снимает ровно свой ключ (и номер страницы);
- шторка переносит всё, что не правит сама (поиск, сортировку, вкладку, вид…) — W0;
- «Zurücksetzen» оставляет только `keep` (вкладку/вид), а не выкидывает со страницы.
Шаблон — `core/_list_filter_bar.html`, поведение шторки — общий `static/js/portal.js`.
План — docs/flt4-cabinet-filters-plan-2026-11-04.md.
"""

from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlencode

from django.utils.formats import date_format
from django.utils.translation import gettext as _

#: Параметры, которые никакая ссылка строки не переносит (как пейджер кабинета).
DROP = ("seite", "box", "cursor", "next", "drawer")


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str = "select"  # select | date
    options: tuple = ()  # ((значение, подпись), …) — без пустого «Alle»
    value: str = ""
    empty_label: str = ""  # подпись пустого варианта select

    @property
    def value_label(self) -> str:
        if not self.value:
            return ""
        if self.kind == "date":
            try:
                return date_format(date.fromisoformat(self.value), "SHORT_DATE_FORMAT")
            except ValueError:
                return self.value
        return next((label for v, label in self.options if str(v) == self.value), self.value)


@dataclass(frozen=True)
class Pill:
    label: str
    url: str


@dataclass
class ListFilters:
    fields: list
    search_key: str = "q"
    search_value: str = ""
    search_label: str = ""
    sort_key: str = "sort"
    sort_value: str = ""
    sort_options: tuple = ()
    total: int | None = None
    pills: list = field(default_factory=list)
    drawer_hidden: list = field(default_factory=list)
    search_hidden: list = field(default_factory=list)
    sort_hidden: list = field(default_factory=list)
    reset_url: str = "?"

    @property
    def active_count(self) -> int:
        return sum(1 for f in self.fields if f.value)

    @property
    def any_active(self) -> bool:
        return bool(self.active_count or self.search_value)


def _pairs(params, exclude) -> list[tuple[str, str]]:
    out = []
    for key, values in params.lists():
        if key in exclude or key in DROP:
            continue
        out.extend((key, v) for v in values if v != "")
    return out


def _url(pairs) -> str:
    return "?" + urlencode(pairs) if pairs else "?"


def build(
    request,
    fields,
    *,
    search_value: str = "",
    search_label: str = "",
    sort_value: str = "",
    sort_options=(),
    total: int | None = None,
    keep=("tab", "view"),
    search_key: str = "q",
    sort_key: str = "sort",
) -> ListFilters:
    params = request.GET
    fields = list(fields)
    field_keys = {f.key for f in fields}
    lf = ListFilters(
        fields=fields,
        search_key=search_key,
        search_value=search_value,
        search_label=search_label or _("Suchen"),
        sort_key=sort_key,
        sort_value=sort_value,
        sort_options=tuple(sort_options),
        total=total,
    )
    lf.drawer_hidden = _pairs(params, field_keys)
    lf.search_hidden = _pairs(params, {search_key})
    lf.sort_hidden = _pairs(params, {sort_key})
    for f in fields:
        if f.value:
            lf.pills.append(Pill(f"{f.label}: {f.value_label}", _url(_pairs(params, {f.key}))))
    if search_value:
        lf.pills.append(Pill(f"„{search_value}“", _url(_pairs(params, {search_key}))))
    lf.reset_url = _url([(k, v) for k, v in _pairs(params, ()) if k in keep])
    return lf
