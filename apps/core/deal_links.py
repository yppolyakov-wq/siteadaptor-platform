"""VS-3: сервис связей «якорь + прикреплённые сделки» (план
`docs/vs3-deal-links-plan-2026-08-20.md`).

Инварианты волны (§4 плана), которые держит именно этот модуль:

- у спутника ОДИН якорь (перепривязка = перенос, не второй ряд);
- вложенности глубже одного уровня нет (спутник не может стать якорем);
- self-link и цикл A→B→A запрещены;
- каскадов статусов НЕТ: связь ничего не двигает, движение по колонкам
  независимое (прямое требование владельца);
- чтение для доски — БАТЧЕМ: два запроса к связям + по одному queryset'у на
  встретившийся kind, ни одного запроса на карточку.

Подписи связанных сделок берём через `transactions.transaction_for` — второй
источник правды не заводим.
"""

from collections import defaultdict

from .models import DealLink

__all__ = ["DealLink", "attach", "detach", "anchor_of", "children_of", "for_cards"]


def _check_kind(kind: str) -> None:
    from apps.core import transactions

    if kind not in transactions.TRANSACTION_KINDS:
        raise ValueError(f"unknown deal kind: {kind!r}")


def _exists(kind: str, pk) -> bool:
    from apps.core import transactions

    try:
        return transactions.model_for(kind).objects.filter(pk=pk).exists()
    except Exception:  # noqa: BLE001 — неизвестная модель = связи не бывать
        return False


def attach(anchor_kind: str, anchor_id, child_kind: str, child_id, note: str = "") -> DealLink:
    """Привязать сделку-спутника к якорю. Идемпотентно; другой якорь = перенос.

    ValueError: неизвестный kind, несуществующая сделка, self-link, цикл или
    попытка сделать якорем сделку, которая сама уже прикреплена (второй уровень).
    """
    _check_kind(anchor_kind)
    _check_kind(child_kind)
    if (anchor_kind, str(anchor_id)) == (child_kind, str(child_id)):
        raise ValueError("a deal cannot be linked to itself")
    if not _exists(anchor_kind, anchor_id) or not _exists(child_kind, child_id):
        raise ValueError("both deals must exist")
    # Цикл: якорь сам прикреплён к этому спутнику.
    reverse = DealLink.objects.filter(
        child_kind=anchor_kind, child_id=anchor_id, anchor_kind=child_kind, anchor_id=child_id
    ).exists()
    if reverse:
        raise ValueError("cyclic link")
    # Второй уровень: якорь сам является чьим-то спутником, ЛИБО спутник уже
    # является якорем для кого-то. И то и другое превратило бы доску в дерево.
    if DealLink.objects.filter(child_kind=anchor_kind, child_id=anchor_id).exists():
        raise ValueError("anchor is itself attached to another deal")
    if DealLink.objects.filter(anchor_kind=child_kind, anchor_id=child_id).exists():
        raise ValueError("child already has attached deals")

    link, _created = DealLink.objects.update_or_create(
        child_kind=child_kind,
        child_id=child_id,
        defaults={
            "anchor_kind": anchor_kind,
            "anchor_id": anchor_id,
            "note": (note or "").strip()[:120],
        },
    )
    return link


def detach(child_kind: str, child_id) -> bool:
    """Снять привязку спутника. True — связь была, False — нечего снимать."""
    deleted, _ = DealLink.objects.filter(child_kind=child_kind, child_id=child_id).delete()
    return bool(deleted)


def anchor_of(child_kind: str, child_id) -> DealLink | None:
    return DealLink.objects.filter(child_kind=child_kind, child_id=child_id).first()


def children_of(anchor_kind: str, anchor_id) -> list[DealLink]:
    return list(
        DealLink.objects.filter(anchor_kind=anchor_kind, anchor_id=anchor_id).order_by("created_at")
    )


def _resolve(pairs) -> dict:
    """{(kind, uuid): Transaction} для набора пар — ОДИН queryset на kind.

    Сироты (объект удалён) в результат не попадают: читатель просто не находит
    пару и молча пропускает связь — доска важнее строки-подсказки.
    """
    from apps.core import transactions

    by_kind = defaultdict(set)
    for kind, pk in pairs:
        by_kind[kind].add(pk)

    out = {}
    for kind, ids in by_kind.items():
        try:
            qs = transactions.model_for(kind).objects.filter(pk__in=ids)
            qs = qs.select_related(*transactions._SELECT_RELATED.get(kind, ()))
            for obj in qs:
                out[(kind, obj.pk)] = transactions.transaction_for(kind, obj)
        except Exception:  # noqa: BLE001 — сломанный kind не валит доску
            continue
    return out


def for_cards(kind: str, ids) -> dict:
    """{uuid: {"children": [Transaction], "anchor": Transaction|None, "notes": {...}}}.

    Два запроса к связям (карточки как якоря и как спутники) + по одному
    queryset'у на каждый встретившийся kind. Число связей на бюджет запросов НЕ
    влияет — замок `test_for_cards_is_batched_not_per_card`.
    """
    ids = [i for i in ids if i]
    empty = {"children": [], "anchor": None, "notes": {}}
    if not ids:
        return {}
    as_anchor = list(DealLink.objects.filter(anchor_kind=kind, anchor_id__in=ids))
    as_child = list(DealLink.objects.filter(child_kind=kind, child_id__in=ids))

    pairs = {(link.child_kind, link.child_id) for link in as_anchor}
    pairs |= {(link.anchor_kind, link.anchor_id) for link in as_child}
    resolved = _resolve(pairs)

    out = {pk: {"children": [], "anchor": None, "notes": {}} for pk in ids}
    for link in as_anchor:
        tx = resolved.get((link.child_kind, link.child_id))
        if tx is None:
            continue  # сирота
        out[link.anchor_id]["children"].append(tx)
        if link.note:
            out[link.anchor_id]["notes"][tx.pk] = link.note
    for link in as_child:
        out[link.child_id]["anchor"] = resolved.get((link.anchor_kind, link.anchor_id))
    return out or {pk: dict(empty) for pk in ids}


def block_context(kind: str, pk) -> dict:
    """Контекст блока связей на ДЕТАЛИ сделки: спутники, якорь и СПРАВОЧНЫЙ итог.

    Итог — только показ («сколько гость доплатит сверх»): деньги сделок не
    сливаются, в отчётах и finance ничего не меняется (инвариант §4.2 плана).
    """
    from decimal import Decimal

    from apps.core import transactions

    data = for_cards(kind, [pk]).get(pk) or {"children": [], "anchor": None, "notes": {}}
    total, currency, seen = Decimal(0), "EUR", False
    for tx in data["children"]:
        if tx.amount_value in (None, ""):
            continue
        total += Decimal(str(tx.amount_value))
        currency = tx.currency or currency
        seen = True
    data["children_total"] = transactions._money_str(total, currency) if seen else ""
    return data
