"""FB-33 M3-6 (макет M0-7): окно блока «Banner» — подписи плиток и «Wo zeigen».

План — план среза M3-6 (решения владельца 2026-11-20):

- подпись под плиткой баннера: срок и где он уже стоит («bis 30.11. · 2 Seiten», «ab 29.11.
  · geplant», «immer · Startseite», «ausgeblendet») — одной картой мест на всё окно (один
  запрос к библиотеке, без «N баннеров × M страниц»);
- «Wo zeigen» — места показа баннера (`Banner.show_on`, FB-29.2c) прямо в окне, только когда в
  блоке ОДИН баннер (у слайдера — ссылка к баннеру в библиотеке). Правка идёт в черновик
  страницы (`draft["show_on"] = {pk: [места]}`, `show_on_base` — сохранённое на первой правке;
  обе части ВНЕ `_saved_state`: правка библиотеки — не конфликт чужих страниц), «Abbrechen»
  возвращает, «Speichern» пишет под блокировкой баннера, сверяя базу (не совпала — своё
  сообщение; «Trotzdem speichern» — трёхстороннее слияние);
- места — только существующие и открытые сайтом (`banners.place_labels`: черновые акции,
  выключенные товары, чужое и мусор не проходят) — при правке И при записи;
- баннер — только из выбора ЭТОГО блока в черновике; право — на библиотеку баннеров.

«Startseite» в «Wo zeigen» — только чтение (её задаёт блок «Banner» главной). «+ Neuer Banner»
не возвращается (решение 2026-11-18): все баннеры — в библиотеке.
"""

from __future__ import annotations

import logging
import uuid

from django.db import DatabaseError, connection
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.core import site_schema

logger = logging.getLogger(__name__)

SHOW_ON_KEY = "show_on"
BASE_KEY = "show_on_base"
SHOW_ON_KEYS = (SHOW_ON_KEY, BASE_KEY)
PLACES_OP = "places"
#: поиск мест (`?wo=`): потолок длины запроса и минимум (короче — без фильтра в базе
#: `place_search` читал бы до 2000 записей каждого вида)
QUERY_MAX = 80
QUERY_MIN = 3
#: сессия: что сделала последняя кнопка «Wo zeigen» (живая область окна, один раз)
SAID_KEY = "aufbau_places_said"


def _schema() -> str:
    return getattr(connection, "schema_name", "") or ""


def is_places_edit(op_name: str) -> bool:
    return op_name == PLACES_OP


def count(draft: dict) -> int:
    pending = draft.get(SHOW_ON_KEY)
    return len(pending) if isinstance(pending, dict) else 0


def _clean(values) -> list[str]:
    from apps.core import banners

    out: list[str] = []
    for value in values if isinstance(values, list) else []:
        if banners._place_ok(value) and value not in out:
            out.append(value)
    return out


def state(draft: dict | None, pk: str, saved) -> list[str]:
    """Места баннера, как их видит окно: черновик поверх сохранённого."""
    pending = (draft or {}).get(SHOW_ON_KEY) or {}
    if isinstance(pending, dict) and pk in pending:
        return _clean(pending[pk])
    return _clean(saved)


# ───────────── подписи плиток: одна карта мест на окно ─────────────


def _host_key(host: str) -> str:
    """Хост блоков страницы → ключ места «Wo zeigen» (та же страница — один счёт)."""
    from apps.core import banners, detail_parts
    from apps.tenants import siteconfig

    if host.startswith(siteconfig.CATEGORY_HOST_PREFIX):
        return f"category:{host.removeprefix(siteconfig.CATEGORY_HOST_PREFIX)}"
    kind = detail_parts.object_kind(host)
    if kind in banners.SHOW_ON_TYPES:
        try:
            return f"{kind}:{uuid.UUID(host.split(':', 1)[1])}"
        except ValueError:
            return host
    return host


def _place_map(config: dict) -> tuple[set[str], dict[str, set[str]]]:
    """(баннеры главной, баннер → места страниц, где он выбран в блоке) — один проход."""
    from apps.core import banners

    home: set[str] = set()
    hosts: dict[str, set[str]] = {}
    for place, holder in banners._picks(config or {}):
        for pk in banners.clean_pick(holder.get("pick")):
            if place == "home":
                home.add(pk)
            else:
                hosts.setdefault(pk, set()).add(_host_key(place))
    return home, hosts


def _day(value) -> str:
    return f"{value.day:02d}.{value.month:02d}."


def caption(row: dict, home: bool, pages: int, today) -> str:
    """«bis 30.11. · 2 Seiten» · «ab 29.11. · geplant» · «immer · Startseite» · «ausgeblendet»."""
    if not row.get("is_active"):
        return _("ausgeblendet")
    starts, ends = row.get("starts"), row.get("ends")
    parts: list[str] = []
    if starts and starts > today:
        parts += [_("ab %(date)s") % {"date": _day(starts)}, _("geplant")]
    elif ends:
        parts.append(_("bis %(date)s") % {"date": _day(ends)})
        if ends < today:
            parts.append(_("abgelaufen"))
    else:
        parts.append(_("immer"))
    if home:
        parts.append(_("Startseite"))
    if pages:
        parts.append(ngettext("%(n)s Seite", "%(n)s Seiten", pages) % {"n": pages})
    return " · ".join(parts)


def _library(pks) -> dict[str, dict] | None:
    """Строки библиотеки по pk; None — библиотека недоступна (ошибка базы), а не «нет баннера»."""
    from apps.core.models import Banner

    if not pks:
        return {}
    try:
        rows = Banner.objects.filter(pk__in=list(pks)).values(
            "pk", "is_active", "starts", "ends", "show_on"
        )
        return {str(r["pk"]): r for r in rows}
    except DatabaseError:
        logger.exception("banner window: library unavailable (schema %s)", _schema())
        return None


def _labels(values) -> dict | None:
    """Подписи существующих мест; None — проверить нельзя (ошибка базы)."""
    from apps.core import banners

    try:
        return banners.place_labels(values, strict=True)
    except DatabaseError:
        logger.exception("banner window: place labels unavailable (schema %s)", _schema())
        return None


def _edit_url(request, pk: str) -> str:
    from apps.core import view_perms

    url = reverse("site-banner-edit", args=[pk])
    return url if view_perms.url_allowed(getattr(request, "user", None), url, "POST") else ""


def decorate(selected, config: dict, draft: dict | None, request) -> None:
    """Подписи плиток выбора баннера и часть «Wo zeigen» (`places`) окна блока."""
    if not selected or not selected.get("banner_pick"):
        return
    pick = selected["banner_pick"]
    rows = [*(pick.get("entries") or ()), *(pick.get("offers") or ())]
    library = _library({r["pk"] for r in rows})
    entries = pick.get("entries") or []
    if library is None:
        # библиотека недоступна: не молчать — окно говорит, что места сейчас не показать
        if len(entries) == 1 and not pick.get("from_page"):
            selected["places"] = {"unavailable": True}
        return
    home, hosts = _place_map(config)
    # места «Wo zeigen» — только существующие (один запрос на вид на всё окно)
    wanted = {v for r in library.values() for v in _clean(r.get("show_on"))}
    known = _labels(sorted(wanted)) if wanted else {}
    today = timezone.localdate()
    for row in rows:
        found = library.get(row["pk"])
        if found is not None:
            places = set(hosts.get(row["pk"], ()))
            places |= {v for v in _clean(found.get("show_on")) if known is None or v in known}
            row["caption"] = caption(found, row["pk"] in home, len(places), today)
    if pick.get("from_page") or pick.get("unavailable"):
        return
    if len(entries) > 1:
        # слайдер: места у каждого баннера свои — правятся в библиотеке
        for entry in entries:
            entry["places_url"] = _edit_url(request, entry["pk"])
        return
    if len(entries) == 1 and entries[0]["pk"] in library:
        selected["places"] = places_panel(
            request, draft, entries[0]["pk"], library[entries[0]["pk"]], entries[0]["pk"] in home
        )
        session = getattr(request, "session", None)
        if session is not None:
            selected["places"]["said"] = session.pop(SAID_KEY, "")


def places_panel(request, draft, pk: str, row: dict, on_home: bool) -> dict:
    from apps.core import banners

    current = state(draft, pk, row.get("show_on"))
    labels = _labels(current) if current else {}
    if labels is None:
        return {"unavailable": True}
    query = (request.GET.get("wo") or "").strip()[:QUERY_MAX]
    allowed = bool(_edit_url(request, pk))
    searchable = len(query) >= QUERY_MIN
    return {
        "pk": pk,
        "chips": [
            {"value": v, "label": labels.get(v, ""), "missing": v not in labels} for v in current
        ],
        "home": on_home,
        "query": query,
        "results": banners.place_search(query, exclude=current) if searchable and allowed else [],
        "short": bool(query) and not searchable,
        "full": len(current) >= banners.SHOW_ON_MAX,
        "allowed": allowed,
    }


# ───────────── правка «Wo zeigen» в черновике ─────────────


def _chosen(config: dict, draft: dict, code: str, host: str, ref: str = "") -> set[str] | str:
    """Баннеры, выбранные в блоках страницы черновика; с `ref` — единственный баннер этого
    блока ("" — в блоке не один баннер)."""
    from apps.core import aufbau_draft
    from apps.tenants import siteconfig

    shown = aufbau_draft.overlay(config, draft)
    rows = site_schema.blocks_for(shown, code, host=host or None, summaries=False)
    if ref:
        row = next((b for b in rows if b["ref"] == ref), None)
        choice = (row or {}).get("banner_choice")
        if not isinstance(choice, dict) or choice.get("from_page"):
            return ""
        pick = siteconfig.clean_banner_choice(choice).get("pick") or []
        return pick[0] if len(pick) == 1 else ""
    out: set[str] = set()
    for b in rows:
        choice = b.get("banner_choice")
        if isinstance(choice, dict) and not choice.get("from_page"):
            out.update(siteconfig.clean_banner_choice(choice).get("pick") or [])
    return out


def _rights(request, pk: str) -> None:
    if not _edit_url(request, pk):
        raise site_schema.SchemaError("banner_rights")


def places_op(request, config: dict, draft: dict, code: str, host: str, ref: str, notes) -> str:
    """Кнопки «Wo zeigen»: `value=del:<место>` — убрать, `value=add` + галочки `wo_add` —
    добавить. Отказ (`SchemaError`) — ничего не меняется."""
    from apps.core import banners
    from apps.core.models import Banner

    if not ref:
        raise site_schema.SchemaError("op")  # ревью: без блока выбор баннера не определить
    pk = _chosen(config, draft, code, host, ref)
    if not isinstance(pk, str) or not pk:
        raise site_schema.SchemaError("op")
    _rights(request, pk)
    banner = Banner.objects.filter(pk=pk).first()
    if banner is None:
        raise site_schema.SchemaError("op")
    saved = _clean(banner.show_on)
    current = state(draft, pk, saved)
    post = getattr(request, "POST", None) or {}
    value = str(post.get("value", ""))
    if value.startswith("del:"):
        gone = value[4:]
        if gone not in current:
            return ref  # уже убрано (вторая вкладка) — не ошибка
        current = [v for v in current if v != gone]
        said = _("„%(name)s“ entfernt.") % {"name": _labels_quiet([gone]).get(gone, gone)}
    elif value == "add":
        wanted = [v for v in post.getlist("wo_add") if v not in current][: banners.SHOW_ON_MAX]
        if not wanted:
            return ref
        known = _labels(wanted)
        if known is None:
            raise site_schema.SchemaError("banner_unavailable")
        if any(v not in known for v in wanted):
            # IDOR-замок: черновая/выключенная/чужая/выдуманная страница — отказ целиком
            raise site_schema.SchemaError("banner_place")
        if len(current) + len(wanted) > banners.SHOW_ON_MAX:
            raise site_schema.SchemaError("banner_full")
        current = [*current, *wanted]
        said = ngettext("%(n)s Seite hinzugefügt.", "%(n)s Seiten hinzugefügt.", len(wanted)) % {
            "n": len(wanted)
        }
    else:
        raise site_schema.SchemaError("op")
    pending = dict(draft.get(SHOW_ON_KEY) or {})
    base = dict(draft.get(BASE_KEY) or {})
    if current == base.get(pk, saved):
        pending.pop(pk, None)  # вернули как было — правки нет
        base.pop(pk, None)
    else:
        pending[pk] = current
        base.setdefault(pk, saved)
    for key, part in ((SHOW_ON_KEY, pending), (BASE_KEY, base)):
        if part:
            draft[key] = part
        else:
            draft.pop(key, None)
    session = getattr(request, "session", None)
    if session is not None:
        session[SAID_KEY] = said  # a11y (ревью): итог кнопки — живой областью окна
    return ref


def _labels_quiet(values) -> dict:
    return _labels(values) or {}


def conflict(draft: dict) -> bool:
    """Места баннера, которые держит черновик, успели изменить в библиотеке."""
    base = draft.get(BASE_KEY)
    if not isinstance(base, dict) or not base or SHOW_ON_KEY not in draft:
        return False
    library = _library(base)
    if library is None:
        return False  # библиотека недоступна — не «изменено в библиотеке»; запись проверит
    return any(_clean((library.get(pk) or {}).get("show_on")) != was for pk, was in base.items())


def merge(base: list[str], mine: list[str], theirs: list[str]) -> list[str]:
    """Трёхстороннее слияние «Trotzdem speichern»: мои добавления и удаления поверх
    сохранённого сейчас (чужие правки библиотеки не теряются)."""
    removed = set(base) - set(mine)
    out = [v for v in theirs if v not in removed]
    out += [v for v in mine if v not in base and v not in out]
    return out


def dropped_note() -> str:
    return _("„Wo zeigen“ wurde nicht übernommen: Der Banner steht nicht mehr in diesem Block.")


def conflict_note() -> str:
    return _(
        "Die Seiten dieses Banners wurden inzwischen in der Bibliothek geändert. Ihr Entwurf "
        "wurde nicht gespeichert – Sie können ihn verwerfen oder trotzdem speichern."
    )


def cut_note() -> str:
    return _(
        "Nicht alle Seiten passen zu diesem Banner – „Wo zeigen“ wurde auf die ersten "
        "%(n)s Seiten gekürzt."
    )


def rights_note() -> str:
    return _("„Wo zeigen“ wurde nicht übernommen: Dafür fehlt das Recht, Banner zu bearbeiten.")


def unavailable_note() -> str:
    return _(
        "Die Banner-Bibliothek ist gerade nicht erreichbar. Bitte später noch einmal versuchen."
    )


def gone_note() -> str:
    return _("Einige Seiten gibt es nicht mehr – sie wurden bei „Wo zeigen“ nicht übernommen.")


def commit(config: dict, draft: dict, code: str, host: str, *, force, notes, request) -> None:
    """«Speichern»: места баннеров черновика — под блокировкой баннера (в транзакции
    `aufbau_draft.commit`, после блокировки строки бизнеса — тот же порядок везде)."""
    from apps.core import banners
    from apps.core.models import Banner

    pending = draft.get(SHOW_ON_KEY)
    if not isinstance(pending, dict) or not pending:
        return
    base = draft.get(BASE_KEY) or {}
    chosen = _chosen(config, draft, code, host)
    for pk, wanted in pending.items():
        if pk not in chosen:
            if notes is not None:
                notes.append(dropped_note())
            continue
        if not _edit_url(request, pk):
            # право на библиотеку отозвали: страница сохраняется, места — нет (с пометкой)
            if notes is not None:
                notes.append(rights_note())
            continue
        locked = Banner.objects.select_for_update().filter(pk=pk).first()
        if locked is None:
            if notes is not None:
                notes.append(dropped_note())
            continue
        current = _clean(locked.show_on)
        was = _clean(base.get(pk, current))
        result = _clean(wanted)
        if current != was:
            if not force:
                raise site_schema.SchemaError("show_on_conflict")
            result = merge(was, result, current)
        added = [v for v in result if v not in current]
        known = _labels(added) if added else {}
        if known is None:
            raise site_schema.SchemaError("banner_unavailable")  # черновик остаётся
        if any(v not in known for v in added):
            result = [v for v in result if v in current or v in known]
            if notes is not None:
                notes.append(gone_note())
        if len(result) > banners.SHOW_ON_MAX:
            result = result[: banners.SHOW_ON_MAX]
            if notes is not None:
                notes.append(cut_note() % {"n": banners.SHOW_ON_MAX})
        if result != (locked.show_on or []):
            locked.show_on = result
            locked.save(update_fields=["show_on", "updated_at"])
