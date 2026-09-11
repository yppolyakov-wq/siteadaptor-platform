"""PT-1: реестр ТИПОВ акции — одна ось рубрикации витрины акций.

Решение владельца (2026-09-11, Р-1): «тип акции» — это ОДНА ось, в которой
живут два сорта значений:

* **свои типы владельца** — то, что до этой волны называлось «группой»
  (`Promotion.group`, свободный текст: Wochenangebote / Anti-Food-Waste /
  Räumung). Поле не меняется, миграции нет;
* **встроенные типы** — механики, которые и так видны посетителю (Mystery,
  Überraschungstüte, Vorbestellung, Countdown, Dauerangebot). Они ВЫВОДЯТСЯ из
  полей акции, руками размечать ничего не нужно.

Ключевое архитектурное решение: у обоих сортов ОДИН параметр витрины —
`?gruppe=`. Встроенный тип отличается префиксом `sys:`. Благодаря этому вся
машинерия «страницы типа», построенная волнами DL-20/LAY-7, достаётся
встроенным типам даром: свой шаблон страницы, пункт меню, чип-фильтр,
хранение настроек в `site_config["promo_groups"]`, тип страницы Студии
`promo_group`. Второй параметр (`?typ=`) означал бы два контрола на один
смысл — ровно то, что волна LAY из системы вычищала.

Настройки типа (шаблон · раскладка · сетка/слайдер · форма карточки, решение
Р-3) лежат там же, где раньше лежал один только шаблон:

    site_config["promo_groups"][<ключ типа>] = "<шаблон>"            # легаси
    site_config["promo_groups"][<ключ типа>] = {                     # PT-2/PT-3
        "style":  "<композиция страницы типа>",
        "layout": {...},        # своя сетка/лента (normalize_layout)
        "card":   "<форма карточки>",
    }

Строка читается как `{"style": <строка>}` и СОХРАНЯЕТСЯ строкой, пока у типа
нет других настроек, — конфиги живых сайтов не переписываются, golden-эталоны
целы (инвариант волны LAY §10.0).
"""

from __future__ import annotations

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

#: Префикс ключа встроенного типа. Имя своей рубрики с таким префиксом
#: (крайне маловероятное) будет затенено встроенным — документированная цена
#: за единственный параметр витрины.
SYS_PREFIX = "sys:"

#: (ключ, подпись, подсказка, фильтр выдачи). Порядок = порядок показа.
#: Фильтр — Q по полям, из которых механика и складывается: список живых типов
#: считается по данным, поэтому пустой тип владельцу не предлагается (STU-9).
BUILTIN: list[tuple[str, object, object, Q]] = [
    (
        "sys:mystery",
        _("Mystery deal"),
        _("Price stays hidden until the guest clicks."),
        Q(discount_style="mystery"),
    ),
    (
        "sys:surprise",
        _("Surprise bag"),
        _("Rescue leftovers — content is a surprise."),
        Q(is_surprise=True),
    ),
    (
        "sys:reservation",
        _("Pre-order"),
        _("Reserve online, pick up in store."),
        Q(promo_type="reservation"),
    ),
    (
        "sys:countdown",
        _("Countdown offer"),
        _("Runs out soon — the timer is the point."),
        Q(show_countdown=True) | Q(discount_style="countdown"),
    ),
    (
        "sys:dauer",
        _("Recurring offer"),
        _("Repeats every day or every week."),
        ~Q(recurrence=""),
    ),
]

_BY_KEY = {key: (label, hint, flt) for key, label, hint, flt in BUILTIN}


def is_builtin(key: str) -> bool:
    return key in _BY_KEY


def builtin_keys() -> tuple[str, ...]:
    return tuple(_BY_KEY)


def builtin_filter(key: str) -> Q | None:
    """Q-фильтр встроенного типа; None — ключ не встроенный (значит, рубрика)."""
    row = _BY_KEY.get(key)
    return row[2] if row else None


def builtin_label(key: str) -> object:
    row = _BY_KEY.get(key)
    return row[0] if row else ""


def builtin_hint(key: str) -> object:
    row = _BY_KEY.get(key)
    return row[1] if row else ""


def label_for(key: str, own_labels=None) -> str:
    """Подпись типа: встроенная из реестра, своя — из карты локализованных рубрик."""
    if is_builtin(key):
        return str(builtin_label(key))
    return (own_labels or {}).get(key, key)


def live_builtin_keys(base_qs) -> list[str]:
    """Встроенные типы, у которых есть хотя бы одна акция в выдаче.

    Один запрос на все типы: пять `exists()` подряд стоили бы пять round-trip'ов
    на каждый рендер страницы акций. Поля лёгкие, выборка уже отфильтрована по
    `status="active"`.
    """
    rows = list(
        base_qs.values_list(
            "discount_style", "is_surprise", "promo_type", "show_countdown", "recurrence"
        )
    )
    if not rows:
        return []
    live: list[str] = []
    for style, surprise, ptype, countdown, recurrence in rows:
        if style == "mystery":
            live.append("sys:mystery")
        if surprise:
            live.append("sys:surprise")
        if ptype == "reservation":
            live.append("sys:reservation")
        if countdown or style == "countdown":
            live.append("sys:countdown")
        if recurrence:
            live.append("sys:dauer")
    seen = set(live)
    return [key for key in builtin_keys() if key in seen]


def apply_type(items, key: str):
    """Отфильтровать выдачу по типу: встроенный — Q из реестра, свой — рубрика."""
    if not key:
        return items
    flt = builtin_filter(key)
    if flt is not None:
        return items.filter(flt)
    return items.filter(group=key)


# ─────────────────────── настройки типа (PT-2 / PT-3) ───────────────────────


def settings_for(per_type, key: str) -> dict:
    """Настройки одного типа из `site_config["promo_groups"]`.

    Значение записи — строка (легаси «только шаблон») или словарь. Мусор в любом
    слое проваливается в пустое, а не роняет страницу: ключ типа — свободный
    текст, и переименование рубрики в форме акции осиротит запись словаря
    (то же правило fail-safe, что у `group_styles.group_style`).
    """
    raw = (per_type or {}).get(key or "")
    if isinstance(raw, str):
        return {"style": raw.strip()} if raw.strip() else {}
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    style = raw.get("style")
    if isinstance(style, str) and style.strip():
        out["style"] = style.strip()
    layout = raw.get("layout")
    if isinstance(layout, dict) and layout:
        out["layout"] = layout
    card = raw.get("card")
    if isinstance(card, str) and card.strip():
        out["card"] = card.strip()
    return out
