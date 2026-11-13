"""FB-21: формат фото по МЕСТАМ витрины (карточки товаров, акций, услуг, …).

Раньше форма кадра была одна на весь сайт (`site_defaults.media_shape`: round | wide,
DL-10), а пропорции зашиты в шаблонах (квадрат / 3:2 / 4:3). Теперь у каждого места
своя пропорция и способ вписывания:

    site_defaults.media_places = {"product": {"ratio": "4-3", "fit": "contain"}, …}

Ключ presence-minimal: нет записи у места → прежний вид (общая форма DL-10 или
разметка), поэтому golden-конфиги и сборки целы. Значения — только из реестра ниже,
CSS собирается сервером из них же (ввода владельца в CSS нет).

Место помечено в разметке `data-sf-place="<код>"` на том же боксе, что `data-sf-media-box`
(подпись поверх фото — overlay-карточки — не помечены: кроп срезал бы текст). Боковое фото
горизонтальных форм (`data-sf-media-box="side"`) высоту берёт от карточки — его не трогаем.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

#: код места → подпись (порядок = порядок строк на экране «Design des Shops»).
PLACES = {
    "product": _("Produkte"),
    "promo": _("Aktionen"),
    "sellable": _("Leistungen, Zimmer & Termine"),
    "category": _("Kategorien"),
    "combo": _("Menüs & Sets"),
    "tour": _("Touren"),
    # M21.5: главное фото страницы товара/услуги/номера (галерея). Раньше — жёстко 4:3
    # с обрезкой, круглую тарелку чая срезало снизу.
    "detail": _("Detailseiten"),
}

#: код пропорции → CSS aspect-ratio ("round" — круг по центру карточки).
RATIOS = {
    "1-1": "1 / 1",
    "4-3": "4 / 3",
    "3-2": "3 / 2",
    "3-4": "3 / 4",
    "16-9": "16 / 9",
    "round": "1 / 1",
}
RATIO_LABELS = {
    "1-1": _("Quadrat 1:1"),
    "4-3": _("Quer 4:3"),
    "3-2": _("Quer 3:2"),
    "3-4": _("Hoch 3:4"),
    "16-9": _("Breit 16:9"),
    "round": _("Rund"),
}
#: FB-29.7: рамка-образец на плитке выбора — (ширина, высота) в px; "" — «Standard».
TILE_SHAPES = {
    "": (48, 36),
    "1-1": (42, 42),
    "4-3": (52, 39),
    "3-2": (54, 36),
    "3-4": (33, 44),
    "16-9": (60, 34),
    "round": (42, 42),
}
SHORT_LABELS = {"1-1": "1:1", "4-3": "4:3", "3-2": "3:2", "3-4": "3:4", "16-9": "16:9"}


def ratio_tiles() -> list[dict]:
    """Плитки выбора пропорции: {key, label, short, w, h, round}; первая — «Standard»."""
    out = [{"key": "", "label": _("Standard"), "short": _("Standard"), "round": False}]
    for key, label in RATIO_LABELS.items():
        out.append(
            {
                "key": key,
                "label": label,
                "short": SHORT_LABELS.get(key, label),
                "round": key == "round",
            }
        )
    for tile in out:
        tile["w"], tile["h"] = TILE_SHAPES[tile["key"]]
    return out


#: «cover» (по умолчанию) — обрезать до формата; «contain» — вписать целиком с полями.
FITS = {"contain": _("Ganz zeigen (mit Rand)")}


def clean(raw) -> dict:
    """Сырое значение → {place: {ratio?, fit?}} только с допустимыми непустыми полями."""
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for place in PLACES:
        entry = raw.get(place)
        if not isinstance(entry, dict):
            continue
        item = {}
        if entry.get("ratio") in RATIOS:
            item["ratio"] = entry["ratio"]
        if entry.get("fit") in FITS:
            item["fit"] = entry["fit"]
        if item:
            out[place] = item
    return out


def from_post(post) -> dict:
    """Форма экрана «Design des Shops» (`mp_<place>_ratio` / `mp_<place>_fit`) → clean()."""
    return clean(
        {
            place: {
                "ratio": post.get(f"mp_{place}_ratio", ""),
                "fit": post.get(f"mp_{place}_fit", ""),
            }
            for place in PLACES
        }
    )


def css(places) -> str:
    """Правила CSS для витрины (пусто, если ничего не задано)."""
    rules = []
    for place, item in clean(places).items():
        box = f'body [data-sf-place="{place}"]:not([data-sf-media-box="side"])'
        ratio = item.get("ratio")
        if ratio and place == "detail":
            # ширину галереи задаёт её раскладка (лента на телефоне — 88 %), поэтому
            # меняем только пропорцию; «круг» здесь — квадрат (кадр на всю колонку)
            ratio = "1-1" if ratio == "round" else ratio
            rules.append(box + "{aspect-ratio:" + RATIOS[ratio] + "!important;}")
        elif ratio:
            decl = f"aspect-ratio:{RATIOS[ratio]}!important;height:auto!important;"
            if ratio == "round":
                decl += "width:62%;margin:.75rem auto 0;border-radius:9999px;overflow:hidden;"
            else:
                # общая форма DL-10 «Rund» сужала бокс и скругляла — своё место сильнее
                decl += "width:auto;margin:0;border-radius:0;"
            rules.append(box + "{" + decl + "}")
            # у тура пропорция стоит на самой картинке — она обязана заполнить бокс
            rules.append(
                box + " > img{width:100%;height:100%!important;aspect-ratio:auto!important;}"
            )
        if item.get("fit") == "contain":
            rules.append(box + " img{object-fit:contain!important;}")
    return "".join(rules)


def rows(places) -> list[dict]:
    """Строки для формы: код, подпись, текущие ratio/fit."""
    current = clean(places)
    return [
        {
            "code": code,
            "label": label,
            "ratio": current.get(code, {}).get("ratio", ""),
            "fit": current.get(code, {}).get("fit", ""),
            # подпись свёрнутой строки: «1:1, ganz» / «Standard»
            "ratio_short": SHORT_LABELS.get(
                current.get(code, {}).get("ratio", ""),
                RATIO_LABELS.get(current.get(code, {}).get("ratio", ""), _("Standard")),
            ),
        }
        for code, label in PLACES.items()
    ]
