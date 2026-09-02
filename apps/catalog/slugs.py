"""KAT-6/KAT-3: общая генерация уникального слага «среди живых записей».

Единая утилита для формы категории, демо-сидера (после снятия префикса demo-
сидер обязан суффиксовать — recreate на схеме с ручными категориями иначе падал
бы на uniq_*_slug_alive) и авто-слага товара. Слаг стабилен после создания
(переименование URL не меняет — прецедент Collection).
"""

from django.utils.text import slugify

# KAT-3: слова, занятые подпутями /sortiment/ — категория/товар с таким слагом
# перекрыли бы роут (uuid-роуты строже и не в счёт).
RESERVED_SLUGS = frozenset({"p", "zuletzt"})  # DL-16.6: /sortiment/zuletzt/ — фрагмент


def unique_slug(model, base: str, *, exclude_pk=None, fallback: str = "eintrag") -> str:
    """base → base, base-2, base-3… уникально среди живых записей model.

    Пустой/нелатинский base (slugify съел всё) → fallback. Зарезервированные
    слова получают суффикс сразу."""
    base = slugify(base or "")[:100] or fallback
    if base in RESERVED_SLUGS:
        base = f"{base}-1"
    qs = model.objects.all()
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    slug = base
    i = 2
    while qs.filter(slug=slug).exists():
        slug = f"{base}-{i}"
        i += 1
    return slug
