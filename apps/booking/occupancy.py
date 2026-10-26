"""KA-12 GA-5 (Gastro): область занятости ресурса — объединение столов.

Комбинация «Tisch 3+4» — отдельный ресурс-стол с `parts` = {3, 4}. Пока она
занята, заняты и столы 3 и 4; пока занят стол 3, занята комбинация (и любая
другая, где есть стол 3). Единственная точка: все проверки пересечений
(`services.overlapping`, слоты `availability`) и блокировки строк идут через
`scope_ids` / `lock_scope`, иначе комбинация и её стол продались бы на одно время.

Комбинации действуют только для столов «1 бронь = 1 стол» (`capacity == 1`, не пул):
у пула мест и ресурса на N броней область — он сам (прежнее поведение)."""

from .models import Resource


def _combinable(resource) -> bool:
    return (
        getattr(resource, "type", "") == Resource.TYPE_TABLE
        and not getattr(resource, "counts_party_size", False)
        and int(getattr(resource, "capacity", 1) or 1) == 1
    )


def scope_ids(resource) -> set:
    """pk ресурсов, чьи активные брони занимают `resource` на то же время."""
    pk = getattr(resource, "pk", resource)
    if not _combinable(resource):
        return {pk}
    base = {pk} | set(
        Resource.parts.through.objects.filter(from_resource_id=pk).values_list(
            "to_resource_id", flat=True
        )
    )
    combos = set(
        Resource.parts.through.objects.filter(to_resource_id__in=base).values_list(
            "from_resource_id", flat=True
        )
    )
    return base | combos


def lock_scope(*resources):
    """select_for_update строк области (в порядке pk — без встречного дедлока с
    `book`/`move`/самопереносом). Возвращает {pk: Resource}."""
    ids = set()
    for r in resources:
        if r is not None:
            ids |= scope_ids(r)
    return {r.pk: r for r in Resource.objects.select_for_update().filter(pk__in=ids).order_by("pk")}


class ComboInvalid(ValueError):
    """Комбинация собрана неверно (сообщение — для владельца)."""


def set_parts(combo, part_ids) -> list:
    """Единственный писатель `parts`: проверяет и сохраняет состав комбинации.

    Комбинация и части — столы «1 бронь = 1 стол»; часть не бывает комбинацией
    (один уровень), комбинация не бывает частью; себя не включает. Места
    комбинации по умолчанию — сумма мест частей. Пустой список — комбинация
    распускается (снова обычный стол)."""
    from django.utils.translation import gettext as _

    ids = {str(p) for p in part_ids if p} - {str(combo.pk)}
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
