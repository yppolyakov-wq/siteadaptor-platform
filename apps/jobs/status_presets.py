"""KA-12 A-6b (Werkstatt): готовый набор своих статусов заявки.

Мастерской между «Beauftragt» и «Erledigt» нужны рабочие шаги — «In Arbeit»,
«Teile bestellt», «Abholbereit». Через редактор своих статусов (FB-3 B) владелец мог
собрать их сам, но не знал, что так можно. Пресет кладёт их одной кнопкой.

Слияние, а не замена: недостающие коды и рёбра добавляются, правки владельца (имя,
роль, удалённые им рёбра у уже существующих статусов) не трогаются, повтор ничего не
меняет. Новым бизнесам werkstatt пресет ставится, только если своих статусов заявки ещё
нет. Код `abholbereit` — сигнал письма клиенту (`JobSM.on_transition`): имя владелец
может переименовать, код остаётся.
"""

from apps.core.status_registry import def_from_role
from apps.tenants import siteconfig

READY_CODE = "abholbereit"

STATUS_PRESETS = {
    "werkstatt": {
        "defs": [
            ("in_arbeit", "In Arbeit", "active"),
            ("teile_bestellt", "Teile bestellt", "active"),
            (READY_CODE, "Abholbereit", "active"),
        ],
        "edges": [
            ("accepted", "in_arbeit"),
            ("in_arbeit", "teile_bestellt"),
            ("teile_bestellt", "in_arbeit"),
            ("in_arbeit", READY_CODE),
            (READY_CODE, "done"),
            ("in_arbeit", "cancelled"),
            ("teile_bestellt", "cancelled"),
        ],
    },
}


def has_preset(business_type) -> bool:
    return (business_type or "") in STATUS_PRESETS


def merge(site_config, business_type) -> tuple[dict, bool]:
    """(новый конфиг, изменён ли) — недостающие статусы/рёбра пресета добавлены."""
    cfg = dict(site_config) if isinstance(site_config, dict) else {}
    preset = STATUS_PRESETS.get(business_type or "")
    if not preset:
        return cfg, False
    defs_all = siteconfig.normalize_status_defs(cfg.get("status_defs"))
    edges_all = siteconfig.normalize_status_edges(cfg.get("status_edges"))
    defs = list(defs_all.get("job", []))
    edges = list(edges_all.get("job", []))
    codes = {d["code"] for d in defs}
    pairs = {(e["src"], e["dst"]) for e in edges}
    changed = False
    for code, label, role in preset["defs"]:
        if code not in codes:
            defs.append(def_from_role(code, label, role, kind="job"))
            codes.add(code)
            changed = True
    for src, dst in preset["edges"]:
        if (src, dst) not in pairs:
            edges.append({"src": src, "dst": dst})
            pairs.add((src, dst))
            changed = True
    if not changed:
        return cfg, False
    defs_all["job"] = siteconfig.normalize_status_defs({"job": defs}).get("job", [])
    edges_all["job"] = siteconfig.normalize_status_edges({"job": edges}).get("job", [])
    cfg["status_defs"] = defs_all
    cfg["status_edges"] = edges_all
    return cfg, True


def with_default(site_config, business_type) -> tuple[dict, bool]:
    """Дефолт при создании/смене типа: только если своих статусов заявки нет."""
    cfg = dict(site_config) if isinstance(site_config, dict) else {}
    if siteconfig.normalize_status_defs(cfg.get("status_defs")).get("job"):
        return cfg, False
    return merge(cfg, business_type)
