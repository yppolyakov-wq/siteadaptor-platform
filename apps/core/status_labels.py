"""FB-4a/FB-4b: свои имена статусов (кабинет-отображение) — generic по kind.

Хранение: site_config["status_labels"][kind][status] = "своё имя". Читается тегом
`{% status_label obj kind %}` (apps/core/templatetags/cabinet.py) и на доске (transactions).
FSM/письма/публичную витрину НЕ трогает. Пусто = дефолт get_status_display().
"""

_LABEL_MAX = 40


def custom_labels(tenant, kind: str) -> dict:
    """{status: своё_имя} для kind из site_config тенанта (или {} — тогда дефолты)."""
    cfg = getattr(tenant, "site_config", None)
    if isinstance(cfg, dict):
        node = cfg.get("status_labels")
        if isinstance(node, dict) and isinstance(node.get(kind), dict):
            return dict(node[kind])
    return {}


def label_rows(tenant, kind: str, choices) -> list[tuple]:
    """[(status, дефолт-подпись, своё-имя)] для панели переименования статусов."""
    node = custom_labels(tenant, kind)
    return [(st, default, node.get(st, "")) for st, default in choices]


def save_labels(tenant, kind: str, statuses, request) -> None:
    """Targeted-write site_config["status_labels"][kind] из POST (label_<status>).

    Прочие ключи/kinds целы; пусто = дефолты (kind снимается — presence-minimal,
    golden-паритет). FSM/переходы не трогаются.
    """
    node = {}
    for st in statuses:
        val = (request.POST.get(f"label_{st}") or "").strip()[:_LABEL_MAX]
        if val:
            node[st] = val
    cfg = dict(tenant.site_config) if isinstance(tenant.site_config, dict) else {}
    labels = dict(cfg.get("status_labels") or {})
    if node:
        labels[kind] = node
    else:
        labels.pop(kind, None)
    if labels:
        cfg["status_labels"] = labels
    else:
        cfg.pop("status_labels", None)
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config", "updated_at"])
