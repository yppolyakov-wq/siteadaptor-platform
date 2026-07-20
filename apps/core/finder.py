"""FD-1: Finder «вопросы → 3 предложения» — rule-based guided selling.

Покупатель отвечает на 2–4 вопроса-чипа → движок скорит АКТИВНЫЕ сущности
primary-модуля тенанта и отдаёт 3 карточки (лучшая — «Unser Vorschlag», в
середине). Правила вместо ИИ: слова (+2 за попадание в имя/описание),
collection/category-slug (+3), price_min/max — жёсткий фильтр (EUR). Скоринг в
Python — каталоги микро-бизнеса маленькие (кап 200). Контракт «ответы →
фильтры → предложения» рассчитан на будущий LLM-режим без переделки (v2).

Дерево вопросов: кастом из site_config["finder"]["questions"] (кабинет — FD-3),
иначе пресет по business_type, иначе generic по primary-модулю. Лейблы пресетов
— немецкие литералы (конвенция msgid). План — docs/fd1-finder-plan-2026-07-18.md.
"""

import importlib

from apps.core import archetypes
from apps.core.sellable import display_fields

# primary-модуль → (модель, фильтр активных, sellable-kind).
_CANDIDATES = {
    "catalog": ("apps.catalog.models", "Product", {"is_active": True}, "product"),
    "booking": ("apps.booking.models", "Service", {"is_active": True}, "service"),
    "stays": ("apps.stays.models", "StayUnit", {"is_active": True}, "stay"),
    "events": ("apps.events.models", "Event", {}, "event"),
}
_MAX_CANDIDATES = 200
_RESULTS = 3

# --- пресеты деревьев -------------------------------------------------------------
# Каждый чип: {key, label, match}; match-семантика = siteconfig._clean_finder_match.
# Структура вопросов по рисёрчу FD (повод → уточнение → бюджет; 3 предложения).


def _budget_q(levels) -> dict:
    """Вопрос бюджета из [(key, label, price_min, price_max), …]; 0 = без границы."""
    chips = []
    for key, label, lo, hi in levels:
        match = {}
        if lo:
            match["price_min"] = lo
        if hi:
            match["price_max"] = hi
        chips.append({"key": key, "label": label, "match": match})
    return {"key": "budget", "label": "Und dein Budget?", "chips": chips}


def _q(key, label, chips) -> dict:
    return {
        "key": key,
        "label": label,
        "chips": [{"key": k, "label": lbl, "match": m} for k, lbl, m in chips],
    }


_TREES = {
    "bakery": [
        _q(
            "anlass",
            "Was suchst du? 🥨",
            [
                ("geburtstag", "🎂 Etwas zum Geburtstag", {"words": ["torte", "kuchen"]}),
                ("alltag", "🥖 Brot & Brötchen", {"words": ["brot", "brötchen", "brezel"]}),
                ("feier", "🎉 Für eine Feier", {"words": ["torte", "platte", "box", "gebäck"]}),
                ("suess", "🍰 Etwas Süßes", {"words": ["kuchen", "gebäck", "tasche", "schnecke"]}),
            ],
        ),
        _budget_q(
            [
                ("klein", "bis 10 €", 0, 10),
                ("mittel", "10–30 €", 0, 30),
                ("egal", "Egal", 0, 0),
            ]
        ),
    ],
    "butcher": [
        _q(
            "anlass",
            "Was ist geplant? 🥩",
            [
                ("grillen", "🔥 Grillen", {"words": ["grill", "steak", "bratwurst", "spieß"]}),
                ("party", "🎉 Party / Gäste", {"words": ["platte", "party", "aufschnitt"]}),
                ("alltag", "🍽 Für den Alltag", {"words": ["wurst", "schinken", "hack", "braten"]}),
            ],
        ),
        _budget_q(
            [
                ("klein", "bis 15 €", 0, 15),
                ("mittel", "15–50 €", 0, 50),
                ("egal", "Egal", 0, 0),
            ]
        ),
    ],
    "friseur": [
        _q(
            "ziel",
            "Was möchtest du? 💇",
            [
                ("schnitt", "✂️ Schnitt", {"words": ["schnitt", "haarschnitt", "trocken"]}),
                ("farbe", "🎨 Farbe", {"words": ["farbe", "färben", "strähnen", "balayage"]}),
                (
                    "styling",
                    "✨ Styling / Pflege",
                    {"words": ["styling", "pflege", "föhnen", "kur"]},
                ),
            ],
        ),
        _budget_q(
            [
                ("klein", "bis 30 €", 0, 30),
                ("mittel", "30–60 €", 0, 60),
                ("egal", "Egal", 0, 0),
            ]
        ),
    ],
    "hotel": [
        _q(
            "wer",
            "Wer reist? 🛏",
            [
                ("zwei", "💑 Zu zweit", {"words": ["doppel", "komfort", "suite"]}),
                (
                    "familie",
                    "👨‍👩‍👧 Familie",
                    {"words": ["familien", "apartment", "ferienwohnung"]},
                ),
                ("allein", "🧳 Allein", {"words": ["einzel", "single"]}),
            ],
        ),
        _budget_q(
            [
                ("klein", "bis 80 €/Nacht", 0, 80),
                ("mittel", "80–150 €/Nacht", 0, 150),
                ("egal", "Egal", 0, 0),
            ]
        ),
    ],
    "events": [
        _q(
            "art",
            "Wonach suchst du? 🎟",
            [
                ("konzert", "🎵 Konzert / Show", {"words": ["konzert", "musik", "show"]}),
                ("kurs", "🧑‍🎓 Kurs / Workshop", {"words": ["workshop", "kurs", "seminar"]}),
                ("erlebnis", "🌄 Erlebnis / Tour", {"words": ["tour", "führung", "wanderung"]}),
            ],
        ),
        _budget_q(
            [
                ("klein", "bis 20 €", 0, 20),
                ("mittel", "20–60 €", 0, 60),
                ("egal", "Egal", 0, 0),
            ]
        ),
    ],
}
# Синонимичные архетипы → то же дерево.
_TREES["cafe"] = _TREES["bakery"]
_TREES["tour_operator"] = _TREES["events"]

# Generic-фолбэк по primary-модулю (архетип без своего дерева).
_MODULE_TREES = {
    "catalog": [
        _q(
            "anlass",
            "Was suchst du? 🛍",
            [
                ("geschenk", "🎁 Ein Geschenk", {"words": ["geschenk", "gutschein", "set", "box"]}),
                ("alltag", "🧺 Für den Alltag", {}),
                ("besonderes", "✨ Etwas Besonderes", {"words": ["premium", "spezial", "edition"]}),
            ],
        ),
        _budget_q(
            [
                ("klein", "bis 20 €", 0, 20),
                ("mittel", "20–50 €", 0, 50),
                ("egal", "Egal", 0, 0),
            ]
        ),
    ],
    "booking": [
        _q(
            "ziel",
            "Was brauchst du? 📅",
            [
                ("beratung", "💬 Beratung", {"words": ["beratung", "check", "termin"]}),
                ("service", "🔧 Service / Behandlung", {}),
                ("pflege", "✨ Pflege / Extras", {"words": ["pflege", "extra", "paket"]}),
            ],
        ),
        _budget_q(
            [
                ("klein", "bis 50 €", 0, 50),
                ("mittel", "50–150 €", 0, 150),
                ("egal", "Egal", 0, 0),
            ]
        ),
    ],
    "stays": _TREES["hotel"],
    "events": _TREES["events"],
}


def primary_kind(tenant) -> str:
    """sellable-kind primary-модуля тенанта ('' — у архетипа нет Finder-сущностей)."""
    module = archetypes.primary_module(tenant)
    return _CANDIDATES[module][3] if module in _CANDIDATES else ""


def enabled(tenant) -> bool:
    """Finder — ОПЦИЯ (решение владельца 2026-07-18): включается явно."""
    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    fnd = cfg.get("finder") if isinstance(cfg.get("finder"), dict) else {}
    return bool(fnd.get("enabled")) and bool(primary_kind(tenant))


def preset_tree(tenant) -> list[dict]:
    """FD-3: пресетное дерево архетипа (ИГНОРИРУЯ кастом) — «Branchen-Vorlage»
    как стартовая точка редактора."""
    if tenant.business_type in _TREES:
        return _TREES[tenant.business_type]
    module = archetypes.primary_module(tenant)
    return _MODULE_TREES.get(module, _MODULE_TREES["catalog"])


def tree_for(tenant) -> list[dict]:
    """Дерево вопросов: кастом (site_config, FD-3) → пресет архетипа → generic."""
    from apps.tenants import siteconfig

    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    custom = siteconfig.normalize_finder(cfg.get("finder")).get("questions")
    if custom:
        return custom
    return preset_tree(tenant)


def _candidates(tenant):
    """(kind, [объекты]) — активные сущности primary-модуля, новейшие первыми."""
    module = archetypes.primary_module(tenant)
    if module not in _CANDIDATES:
        return "", []
    mod_path, cls_name, flt, kind = _CANDIDATES[module]
    try:
        model = getattr(importlib.import_module(mod_path), cls_name)
        return kind, list(model.objects.filter(**flt)[:_MAX_CANDIDATES])
    except Exception:  # noqa: BLE001 — модуль выключен / нет таблицы
        return kind, []


def _slug_set(obj, attr) -> set:
    """Слаги M2M/FK-связи (collections у service/stay, category у product)."""
    try:
        rel = getattr(obj, attr, None)
        if rel is None:
            return set()
        if hasattr(rel, "all"):
            return {x.slug for x in rel.all() if getattr(x, "slug", "")}
        return {rel.slug} if getattr(rel, "slug", "") else set()
    except Exception:  # noqa: BLE001 — связь недоступна
        return set()


def _score(fields, obj, matches) -> float | None:
    """Балл сущности по выбранным чипам; None = отфильтрована ценой."""
    text = f"{fields.get('name', '')} {fields.get('description', '')}".lower()
    try:
        raw = fields.get("price_value")
        price = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        price = None
    score = 0.0
    for match in matches:
        lo, hi = match.get("price_min"), match.get("price_max")
        if price is not None:
            if lo and price < float(lo):
                return None
            if hi and price > float(hi):
                return None
        for word in match.get("words", []):
            if word.lower() in text:
                score += 2
        if match.get("collection") and match["collection"] in _slug_set(obj, "collections"):
            score += 3
        if match.get("category") and match["category"] in _slug_set(obj, "category"):
            score += 3
    return score


def resolve(tenant, answers: dict, locale=None) -> dict:
    """Состояние Finder по ответам {q_key: chip_key}.

    Есть неотвеченный вопрос → {"question", "step", "total", "answers"}.
    Все отвечены → {"results": [{kind, obj, fields, pick}] ×3, "fallback": bool}
    — лучшая карточка ПОСЕРЕДИНЕ («Unser Vorschlag», правило трёх + дефолт).
    Мало кандидатов → добор новейшими (fallback=True при пустом скоринге)."""
    tree = tree_for(tenant)
    chosen = []
    for i, q in enumerate(tree):
        chip_key = answers.get(q["key"])
        chip = next((c for c in q["chips"] if c["key"] == chip_key), None)
        if chip is None:
            return {"question": q, "step": i + 1, "total": len(tree), "answers": answers}
        chosen.append(chip.get("match") or {})

    kind, objs = _candidates(tenant)
    scored = []
    for obj in objs:
        fields = display_fields(kind, obj, locale)
        s = _score(fields, obj, chosen)
        if s is not None:  # None = отфильтрована ценой
            scored.append((s, kind, obj, fields))
    scored.sort(key=lambda t: t[0], reverse=True)
    top = [(k, o, c) for _s2, k, o, c in scored[:_RESULTS]]
    # fallback: ни одного «содержательного» совпадения — показываем новейшие
    # активные как «популярное» (страница даёт CTA в чат/каталог).
    fallback = not any(s > 0 for s, *_rest in scored[:_RESULTS])
    results = []
    if top:
        # Лучшая карточка — В СЕРЕДИНЕ («Unser Vorschlag»): [2-я, 1-я, 3-я].
        seq = [top[i] for i in (1, 0, 2) if i < len(top)]
        for k, o, f in seq:
            results.append({"kind": k, "obj": o, "fields": f, "pick": o.pk == top[0][1].pk})
    return {"results": results, "fallback": fallback, "total": len(tree)}
