"""T-10 D-2: отпечаток демо-кита — пересевать только изменённые демо (2026-10-20).

План — docs/deploy-speed-plan-2026-10-20.md §5. Решение владельца: демо засеваются один
раз и обновляются только при необходимости.

Отпечаток = sha256 от спеки кита (`DemoKit` целиком) + переводов ЕГО строк из словарей
`demo_i18n_<loc>.json` + `SEEDER_VERSION`. Хранится у демо-тенанта в
`site_config["demo_kit"]` (без миграции). `seed_demo_tenants --changed` пересоздаёт только
киты, чей отпечаток разошёлся с сохранённым.

Чего отпечаток НЕ видит: поведение, зашитое в коде сидера (`apply_kit` и помощники), а не в
спеке. Меняя такой код, поднимите `SEEDER_VERSION` — пересеются все демо (или пересейте
нужные явно: `--kit X --recreate`).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json

from django.conf import settings
from django.utils import translation

# Поднимать вручную при изменении логики сидера, не отражённой в спеке китов.
SEEDER_VERSION = 9  # 9: KA-12 GA-7 — зал ресторана из столов (места/зоны/комбинация) + брони по столам; 8: KA-12 Z-5/Z-7 — стойка отеля: заезд/выезд сегодня с отметками; 7: KA-12 E6.4 — история клиента салона (неявки, рецептура); 6: KA-12 E4.4b — варианты услуги (friseur: Haarschnitt Damen); 5: KA-12 E4.2a — навыки мастеров (friseur: Färben только Lea); 4: KA-12 E4.10a — блок ремонта на комнату 104 отеля; 3: KA-12 E1.7 — проданные демо-билеты оплачены; 2: KA-12 E8.7/E8.11 — киты включают blog/booking по контенту
STORE_KEY = "demo_kit"


def _strings(value, out: set[str]) -> None:
    if isinstance(value, str):
        out.add(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            _strings(k, out)
            _strings(v, out)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _strings(item, out)


def _payload(kit) -> object:
    # Ленивые строки (gettext_lazy) — текст базового языка: иначе отпечаток зависел бы
    # от языка процесса.
    with translation.override(settings.LANGUAGE_CODE):
        raw = dataclasses.asdict(kit) if dataclasses.is_dataclass(kit) else vars(kit)
        return json.loads(json.dumps(raw, sort_keys=True, default=str))


def kit_fingerprint(kit) -> str:
    from . import demo_i18n

    payload = _payload(kit)
    strings: set[str] = set()
    _strings(payload, strings)
    i18n = {
        loc: {s: demo_i18n._map(loc)[s] for s in sorted(strings) if s in demo_i18n._map(loc)}
        for loc in demo_i18n.DEMO_LOCALES
    }
    blob = json.dumps(
        {"v": SEEDER_VERSION, "kit": payload, "i18n": i18n},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def stored(tenant) -> str:
    data = (tenant.site_config or {}).get(STORE_KEY)
    return str(data.get("fp") or "") if isinstance(data, dict) else ""


def stamp(tenant, key: str, fingerprint: str) -> None:
    """Записать отпечаток (только ключ `demo_kit` — остальной конфиг не трогаем)."""
    from django.db import transaction
    from django.utils import timezone

    from .models import Tenant

    with transaction.atomic():
        locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
        config = dict(locked.site_config or {})
        config[STORE_KEY] = {
            "key": key,
            "fp": fingerprint,
            "seeded_at": timezone.now().isoformat(),
        }
        locked.site_config = config
        locked.save(update_fields=["site_config"])
    tenant.site_config = config
