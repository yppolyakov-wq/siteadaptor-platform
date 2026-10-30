"""KA-12 GA-5 (Gastro): область занятости ресурса — объединение столов.

Комбинация «Tisch 3+4» — отдельный ресурс-стол с `parts` = {3, 4}. Пока она
занята, заняты и столы 3 и 4; пока занят стол 3, занята комбинация (и любая
другая, где есть стол 3). Единственная точка: все проверки пересечений
(`services.overlapping`, слоты `availability`) и блокировки строк идут через
`scope_ids` / `lock_scope`, иначе комбинация и её стол продались бы на одно время.

Комбинации действуют только для столов «1 бронь = 1 стол» (`capacity == 1`, не пул):
у пула мест и ресурса на N броней область — он сам (прежнее поведение)."""

from django.db import transaction

from .models import Resource


def _combinable(resource) -> bool:
    return (
        getattr(resource, "type", "") == Resource.TYPE_TABLE
        and not getattr(resource, "counts_party_size", False)
        and int(getattr(resource, "capacity", 1) or 1) == 1
    )


def _pk_of(resource):
    pk = getattr(resource, "pk", resource)
    return pk if pk is None else Resource._meta.pk.to_python(pk)


def scope_ids(resource) -> set:
    """pk ресурсов, чьи активные брони занимают `resource` на то же время.

    Связи читаются всегда, а не только у «комбинируемого» ресурса: если часть позже
    перестала им быть (вместимость/пул поменяли), область всё равно симметрична —
    иначе бронь продалась бы в одну сторону (ревью GA-5). Ресурс без связей — 1 запрос."""
    from django.db.models import Q

    pk = _pk_of(resource)
    if pk is None:
        return set()
    through = Resource.parts.through
    links = list(
        through.objects.filter(Q(from_resource_id=pk) | Q(to_resource_id=pk)).values_list(
            "from_resource_id", "to_resource_id"
        )
    )
    if not links:
        return {pk}
    parts = {to for frm, to in links if frm == pk}
    base = {pk} | parts
    combos = {frm for frm, to in links if to == pk}
    if parts:  # комбинации, делящие со мной стол-часть
        combos |= set(
            through.objects.filter(to_resource_id__in=parts).values_list(
                "from_resource_id", flat=True
            )
        )
    return base | combos


def lock_scope(*resources):
    """select_for_update всей области одним запросом в порядке pk (без встречного
    дедлока с `book`/`book_many`/`move`/самопереносом/`set_parts`).

    Состав читается без блокировки, поэтому после захвата область пересчитывается:
    если владелец успел поменять комбинацию, добираем недостающие строки — снова
    ОДНИМ запросом по всему объединению (повтор не переворачивает порядок).
    Возвращает {pk: Resource}."""
    ids = set()
    for r in resources:
        if r is not None:
            ids |= scope_ids(r)
    locked = {}
    for _attempt in range(3):
        locked = {
            r.pk: r for r in Resource.objects.select_for_update().filter(pk__in=ids).order_by("pk")
        }
        grown = set(ids)
        for pk in list(ids):
            grown |= scope_ids(pk)
        if grown == ids:
            return locked
        ids = grown
    return locked


class ComboInvalid(ValueError):
    """Комбинация собрана неверно (сообщение — для владельца)."""


@transaction.atomic  # блокировки lock_scope живут только в транзакции (демо-сидер звал без неё)
def set_parts(combo, part_ids) -> list:
    """Единственный писатель `parts`: проверяет и сохраняет состав комбинации.

    Комбинация и части — столы «1 бронь = 1 стол»; часть не бывает комбинацией
    (один уровень), комбинация не бывает частью; себя не включает. Места
    комбинации по умолчанию — сумма мест частей. Пустой список — комбинация
    распускается (снова обычный стол)."""
    from django.utils.translation import gettext as _

    ids = {str(p) for p in part_ids if p} - {str(combo.pk)}
    # Ревью GA-5: писатель состава берёт ТЕ ЖЕ блокировки, что бронь, — старая и
    # новая область целиком, иначе бронь между чтением и захватом увидела бы чужой состав.
    lock_scope(combo, *ids)
    combo.refresh_from_db()
    parts = list(Resource.objects.filter(pk__in=ids, is_active=True)) if ids else []
    if ids and len(parts) != len(ids):
        raise ComboInvalid(_("Tisch nicht gefunden."))
    if parts:
        if not _combinable(combo) or not all(_combinable(p) for p in parts):
            raise ComboInvalid(
                _(
                    "Kombinieren lassen sich nur Tische mit einer Buchung je Tisch (kein Platz-Pool)."
                )
            )
        if len(parts) < 2:
            raise ComboInvalid(_("Eine Kombination besteht aus mindestens zwei Tischen."))
        if combo.combinations.exists() or any(p.parts.exists() for p in parts):
            raise ComboInvalid(
                _("Eine Kombination kann nicht Teil einer anderen Kombination sein.")
            )
    combo.parts.set(parts)
    if parts and not combo.seats and all(p.seats for p in parts):
        combo.seats = sum(p.seats for p in parts)
        combo.save(update_fields=["seats", "updated_at"])
    return parts
