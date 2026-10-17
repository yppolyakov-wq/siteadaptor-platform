"""T-8.20: поисковый индекс листинга каталога города.

План — docs/t8-20-unified-search-plan-2026-10-15.md (Р-1…Р-4). Хранимый ``search_vector``
(GIN) с весами A–D и ``search_text`` (свёрнутый текст для поиска опечаток через pg_trgm).
Вектор собирается в Python одним UPDATE с параметрами: подписи категорий и районов живут
в Python-реестрах, в SQL их не достать. Обновляется в ``AggregatorListing.save()`` и в
``tasks.refresh_tenant_fields``; полная пересборка — ``manage.py rebuild_search_index``.
"""

from __future__ import annotations

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, connections
from django.utils import translation

# Конфигурации стемминга Postgres по локали; uk/pl и прочие — без стемминга ("simple").
TS_CONFIG = {
    "de": "german",
    "en": "english",
    "ru": "russian",
    "tr": "turkish",
    "fr": "french",
    "it": "italian",
    "es": "spanish",
    "nl": "dutch",
    "pt": "portuguese",
}
_FOLD = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})

# Поля, правка которых меняет индекс (save(update_fields=…) без них индекс не трогает).
INDEXED_FIELDS = frozenset(
    {
        "title",
        "teaser",
        "business_name",
        "dish_names",
        "variant_terms",
        "city",
        "district",
        "city_category",
        "city_tags",
        "category",
        "item_condition",
    }
)


def ts_config(locale: str) -> str:
    return TS_CONFIG.get((locale or "").split("-")[0], "simple")


def fold(text: str) -> str:
    """lower + ä/ö/ü→a/o/u, ß→ss — «muller» находит «Müller» и в поиске опечаток."""
    return (text or "").lower().translate(_FOLD)


def _labels(listing) -> str:
    """Подписи раздела/категории справочника, темы события и района — de + en."""
    from apps.core import city_categories as cc
    from apps.core import districts

    parts = []
    condition = getattr(listing, "item_condition", "") or ""
    for lang in ("de", "en"):
        with translation.override(lang):
            if condition:  # В4: «gebraucht», «Retoure» находят товары в таком состоянии
                parts.append(listing.item_condition_label)
            cat = cc.category(listing.city_category) if listing.city_category else None
            if cat:
                parts.append(str(cat.label))
                section = cc.section(cat.section)
                if section:
                    parts.append(str(section.label))
    if listing.category:
        parts.append(listing.category)
    if listing.district:
        parts.append(districts.label(listing.city, listing.district) or "")
    return " ".join(p for p in parts if p)


def _parts(listing) -> list[tuple[str, str, str]]:
    """[(config, text, weight)] — что и с какой важностью попадает в вектор."""
    title, teaser = listing.title or {}, listing.teaser or {}
    dishes = " ".join(str(d) for d in (listing.dish_names or []))
    tags = " ".join(str(t) for t in (listing.city_tags or []))
    variants = " ".join(str(v) for v in (listing.variant_terms or []))
    parts: list[tuple[str, str, str]] = []
    for code, _name in settings.LANGUAGES:
        if title.get(code):
            parts.append((ts_config(code), str(title[code]), "A"))
            if ts_config(code) != "simple":  # у uk/pl simple уже есть — без дубля
                parts.append(("simple", str(title[code]), "A"))
        if teaser.get(code):
            parts.append((ts_config(code), str(teaser[code]), "C"))
    parts += [
        # Блок Б5: имя бизнеса — вес D (как город): совпадение по заголовку ранжируется
        # выше, чем «нашлось потому, что так зовут фирму». Поиск по имени по-прежнему находит.
        ("german", listing.business_name or "", "D"),
        ("simple", listing.business_name or "", "D"),
        ("german", dishes, "B"),
        ("german", _labels(listing), "C"),
        ("simple", tags, "C"),
        ("simple", variants, "C"),
        ("simple", listing.city or "", "D"),
    ]
    return [p for p in parts if p[1].strip()]


def search_text(listing) -> str:
    title = listing.title or {}
    dishes = " ".join(str(d) for d in (listing.dish_names or []))
    variants = " ".join(str(v) for v in (listing.variant_terms or []))
    return fold(
        " ".join([*(str(v) for v in title.values() if v), listing.business_name, dishes, variants])
    )


def refresh_listing(listing, *, using: str = DEFAULT_DB_ALIAS) -> None:
    """Один UPDATE: вектор + свёрнутый текст для одного листинга."""
    connection = connections[using]
    parts = _parts(listing)
    table = connection.ops.quote_name(type(listing)._meta.db_table)
    if parts:
        vector = " || ".join(
            'setweight(to_tsvector(%s::regconfig, %s), %s::"char")' for _p in parts
        )
        params: list = [x for p in parts for x in p]
    else:
        vector, params = "NULL", []
    with connection.cursor() as cur:
        cur.execute(
            f"UPDATE {table} SET search_vector = {vector}, search_text = %s WHERE id = %s",  # noqa: S608
            [*params, search_text(listing), listing.pk],
        )


def refresh(qs) -> int:
    """Пересобрать индекс для набора листингов (backfill, правка полей бизнеса)."""
    n = 0
    for listing in qs.only(
        "pk",
        "title",
        "teaser",
        "business_name",
        "dish_names",
        "variant_terms",
        "city",
        "district",
        "city_category",
        "city_tags",
        "category",
        "item_condition",
    ).iterator():
        refresh_listing(listing)
        n += 1
    return n
