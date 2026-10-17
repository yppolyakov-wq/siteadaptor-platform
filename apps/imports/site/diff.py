"""Диф повторного импорта (T-8.27f): сравнение кандидатов с тем, что уже применено.

Чистая функция над dict'ами — без БД, легко проверяется. Ключ — `identity_key`
позиции (gtin > sku > адрес+имя), сравнение — `fingerprint` (имя, описание, цена,
картинка, тип, подсказка категории). Пропавшая с сайта позиция предлагается к
отключению, не к удалению — история заказов у товара остаётся."""

from __future__ import annotations

NEW, CHANGED, UNCHANGED, REMOVED = "new", "changed", "unchanged", "removed"
COMPARED = ("name", "price", "description", "image_url")


def compare(candidates: list, applied: dict) -> tuple[list, list]:
    """candidates: [{"identity_key", "fingerprint", "data"}]; applied: {identity_key: {
    "fingerprint", "data", "target_kind", "target_id"}} — последнее применённое и НЕ
    отключённое. Возвращает (кандидаты с diff/previous, список пропавших)."""
    seen = set()
    out = []
    for cand in candidates:
        key = cand["identity_key"]
        seen.add(key)
        prev = applied.get(key)
        if prev is None:
            out.append({**cand, "diff": NEW, "previous": {}})
        elif prev["fingerprint"] == cand["fingerprint"]:
            out.append({**cand, "diff": UNCHANGED, "previous": {}})
        else:
            before = {
                f: prev["data"].get(f)
                for f in COMPARED
                if prev["data"].get(f) != cand["data"].get(f)
            }
            out.append({**cand, "diff": CHANGED, "previous": before})
    removed = [{**prev, "identity_key": key, "diff": REMOVED}
               for key, prev in applied.items() if key not in seen]  # fmt: skip
    return out, removed
