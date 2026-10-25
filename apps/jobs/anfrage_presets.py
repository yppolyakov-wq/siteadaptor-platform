"""KA-12 A-3 (G6): стартовая форма заявки по типу бизнеса.

Кейтерингу форма «дата · гости · повод» нужна с первого дня — без неё заявка
приходит без главного (на сколько человек и когда), и владелец переписывается
с клиентом ради трёх полей. Раньше конфиг `site_config["anfrage"]` писали
только демо-кит и панель «Anfrage-Formular», поэтому новый кейтеринг стартовал
с формой Handwerker'а.

Пресет кладётся при создании бизнеса и при СМЕНЕ типа, и только если ключа ещё
нет: настройку владельца не перетирает, а «все поля сняты» (ключ удалён панелью)
повтор того же шага мастера не отменяет. Значения видов мероприятия — немецкие ключи записи
(`Job.event_type`), показ переводит витрина.
"""

from apps.tenants import siteconfig

ANFRAGE_PRESETS = {
    "catering": {
        "fields": ["date", "guests", "event_type"],
        "event_types": [
            "Hochzeit",
            "Firmenfeier",
            "Geburtstag",
            "Familienfeier",
            "Sonstiges",
        ],
    },
}


def preset_for(business_type) -> dict:
    """Нормализованный пресет формы для типа бизнеса ({} — пресета нет)."""
    raw = ANFRAGE_PRESETS.get(business_type or "")
    return siteconfig.normalize_anfrage(raw) if raw else {}


def with_default(site_config, business_type) -> tuple[dict, bool]:
    """(новый конфиг, изменён ли) — пресет добавлен, только если ключа нет."""
    cfg = dict(site_config) if isinstance(site_config, dict) else {}
    if "anfrage" in cfg:
        return cfg, False
    preset = preset_for(business_type)
    if not preset:
        return cfg, False
    cfg["anfrage"] = preset
    return cfg, True
