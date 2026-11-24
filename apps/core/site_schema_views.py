"""FB-25 / FB-27: экран «Website › Seitenaufbau» — схема страницы рядами и её правка."""

from __future__ import annotations

import logging
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext as _

from apps.core import block_window, page_settings, site_schema

logger = logging.getLogger(__name__)

#: FB-33 M5c-1: вставка блока — читает поле позиции `after`
INSERT_OPS = ("add", "add_row")
#: E1 (стопка 14): предел длины пути страницы `von` — длиннее не принимается
VON_MAX = 300


def _page_path(tenant, raw, code: str) -> str:
    """E1: путь страницы витрины `von` (с неё открыли окно: ⚙ Студии) — только если чистка
    канвы ничего не отрезала (ревью M1), длина не больше `VON_MAX` и код страницы пути —
    код открытой схемы; со страницы объекта со своими блоками (`<вид>@…`) — и общая схема
    его типа (план §9 №1). Иначе "" — экран как без `von`. Зовёт вызывающий, раз на запрос
    (ревью M2, M3): `code_for_path` — только при непустом `von`."""
    from apps.core.views import _safe_preview_page

    if not isinstance(raw, str) or not raw or len(raw) > VON_MAX:
        return ""
    if any(ord(c) <= 0x20 or ord(c) == 0x7F for c in raw):
        return ""  # ревью E1 (security): управляющие символы и пробел — не путь канвы
    if _safe_preview_page(raw) != raw:
        return ""
    found = site_schema.code_for_path(tenant, raw)
    if found == code:
        return "" if code == site_schema.TEXT and _own_text_host(tenant, raw) else raw
    if site_schema.is_object_code(found):
        kind = found.split("@", 1)[0]
        if site_schema.OBJECT_PAGE_TYPES.get(kind, kind) == code:
            return raw
    return ""


def _own_text_host(tenant, path: str) -> bool:
    """Ревью E1 (M): своя страница `path` со СВОИМИ блоками (хост `seite:<slug>`) — не
    страница общего хоста `info`, хотя `code_for_path` даёт ей «text» (правильный разбор —
    roadmap). Хост — `content_pages.schema_ref`, как у «Seiten»."""
    from apps.core import content_pages

    slug = site_schema._path_ref(path)
    if not slug:
        return False
    host, row_code = content_pages.schema_ref(slug)
    if row_code == site_schema.TEXT:
        return False
    blocks = (getattr(tenant, "site_config", None) or {}).get("page_blocks") or {}
    return bool(blocks.get(host))


def _keep(source, von: str = "") -> dict:
    """Вид схемы («Telefon») и открытый способ «Welche» — переживают действие с блоком.
    Только значения из белого списка: в адрес возврата не попадает ничего из запроса.
    `von` (E1) — уже проверенный вызывающим путь страницы (`_page_path`)."""
    from apps.core import list_panel

    keep = {}
    if source.get("welche") in list_panel.WHICH_MODES:
        keep["welche"] = source.get("welche")
    if source.get("ansicht") == "telefon":
        keep["ansicht"] = "telefon"
    # FB-33 M3-1: открытая вкладка окна блока (только из белого списка)
    if source.get("tab") in block_window.TAB_KEYS:
        keep["tab"] = source.get("tab")
    # FB-33 M3-1b: токен открытия окна блока — действие окна не начинает «новое открытие»
    from apps.core import aufbau_draft

    if aufbau_draft.clean_token(source.get("wopen")):
        keep["wopen"] = source.get("wopen")
    # FB-33 M2i-5b: выбранный язык переводов вкладки «Felder» (кнопка `f_sprache` или
    # помнящееся скрытое поле `sprache`) — только язык платформы
    from apps.core import form_answers

    lang = source.get("f_sprache") or source.get("sprache")
    if lang in form_answers.overlay_locales():
        keep["sprache"] = lang
    if von:
        keep["von"] = von
    return keep


#: E9 (стопка 14): значения `abbruch` в адресе после «Abbrechen» (белый список GET)
CANCEL_KINDS = ("done", "conflict", "same")


def _cancel_kind(done: str) -> str:
    """E9: итог `aufbau_draft.cancel` → значение `abbruch`."""
    from apps.core import aufbau_draft

    if done == aufbau_draft.CANCEL_DONE:
        return "done"
    if done == aufbau_draft.CANCEL_CONFLICT:
        return "conflict"
    return "same"


def _cancel_text(kind: str) -> tuple[int, str]:
    """E9: уровень и текст итога «Abbrechen» (тексты M3-1b; вне белого списка — «нечего»)."""
    if kind == "done":
        return messages.SUCCESS, _("Änderungen an diesem Block zurückgenommen.")
    if kind == "conflict":
        return messages.ERROR, _(
            "Die Seite wurde inzwischen an anderer Stelle gespeichert – "
            "Abbrechen ist nicht mehr möglich. Bitte den Block prüfen."
        )
    return messages.WARNING, _("Nichts zurückzunehmen – der Block ist so wie beim Öffnen.")


def _linked_refs(request, tenant, code: str) -> set[str]:
    """E9 (ревью): ref строк схемы со своей ссылкой (не общие) — как их видит GET: черновик
    поверх сохранённого, строки `blocks_for` хоста страницы."""
    from apps.core import aufbau_draft
    from apps.tenants import siteconfig

    saved = siteconfig.normalize(tenant.site_config)
    draft = aufbau_draft.get(request, code)
    config = aufbau_draft.overlay(saved, draft, scope=False) if draft else saved
    _pt, host, _home = site_schema.resolve(tenant, code)
    blocks = site_schema.blocks_for(config, code, host=host or None, tenant=tenant)
    return {b["ref"] for b in blocks if not b.get("shared")}


def _url(code: str, block: str = "", keep: dict | None = None) -> str:
    query = {"seite": code}
    if block:
        query["block"] = block
    for key, value in (keep or {}).items():
        if key not in ("welche", "tab", "wopen", "sprache") or block:
            query[key] = value
    # Якорь панели: после действия фокус возвращается к блоку, а не в начало страницы.
    return f"{reverse('site-schema')}?{urlencode(query)}" + ("#schema-panel" if block else "")


def _panel_fields(post) -> dict | None:
    if post.get("panel_present") != "1":
        return None
    # Браузер шлёт переводы строк textarea как \r\n: без нормализации «Übernehmen» без
    # правок выглядело бы изменением, а в конфиг попадал бы CRLF.
    return {
        k[2:]: v.replace("\r\n", "\n").replace("\r", "\n")
        for k, v in post.items()
        if k.startswith("f_")
    }


_PICK_SAID = {
    "pick_add": _("Hinzugefügt."),
    "pick_remove": _("Entfernt."),
    "pick_up": _("Nach oben verschoben."),
    "pick_down": _("Nach unten verschoben."),
}


def _m36_error(key) -> str:
    """FB-33 M3-6: сообщение отказа окна блока («Wo zeigen» баннера); "" — не наш отказ."""
    from apps.core import window_banner

    if key == "banner_place":
        return _(
            "Diese Seite gibt es nicht (mehr) oder sie ist nicht öffentlich – sie kann hier "
            "nicht gewählt werden."
        )
    if key == "banner_full":
        return _("Mehr Seiten sind für einen Banner nicht möglich.")
    if key == "banner_rights":
        return _("„Wo zeigen“ darf nur ändern, wer auch die Banner bearbeiten darf.")
    if key == "show_on_conflict":
        return window_banner.conflict_note()
    if key == "banner_unavailable":
        return window_banner.unavailable_note()
    return ""


def _row_ops(layout: dict, selected) -> dict:
    """FB-30.8: кнопки без мыши у выбранного блока — «в ряд выше» (если там есть место и
    блок не из этого ряда) и «свой ряд» (если блок стоит в ряду с соседями)."""
    if not selected or not selected.get("enabled", True):
        return {"beside_target": None, "selected_in_row": False}
    lines = layout.get("lines") or []
    at = next(
        (i for i, li in enumerate(lines) if any(b["ref"] == selected["ref"] for b in li["blocks"])),
        None,
    )
    if at is None:
        return {"beside_target": None, "selected_in_row": False}
    above = lines[at - 1]["slot"] if at > 0 else None
    allowed = {v for v, *_rest in selected.get("widths") or []}
    if above and not (allowed & set(site_schema.ROW_SHARE)):
        above = None  # блоку нельзя быть узким — в ряд он не встанет
    return {"beside_target": above, "selected_in_row": len(lines[at]["blocks"]) > 1}


def _is_anfrage_ref(row: dict) -> bool:
    from apps.tenants import siteconfig

    return (
        bool(row.get("cblock"))
        and (siteconfig.cblock_type(row["key"]) or row["key"]) == "anfrage_ref"
    )


def _block_preview(request, code: str, current, selected: dict, page: str) -> dict:
    """FB-33 M3-7: «Vorschau» в окне блока — адрес кадра (черновик страницы
    `?preview=1&aufbau=<код>`: только у члена с правом сайта, `page_settings.preview_raw`) и
    якорь блока на витрине. Путь — тем же фильтром, что старт канвы Студии (только
    внутренний путь витрины, не кабинет). `page` — путь страницы (E1: `von` или образец
    типа). Ничего не пишет."""
    from apps.core import window_links
    from apps.core.views import _safe_preview_page

    path = _safe_preview_page(page)
    sep = "&" if "?" in path else "?"
    return {
        "src": f"{path}{sep}{urlencode({'preview': '1', 'aufbau': code})}",
        "anchor": window_links.canvas_key(request, code, selected["ref"], host=current.host),
        "page": window_links.whole_page(selected["ref"]),
    }


def _old_title_link(request, tenant, code: str) -> str:
    """FB-33 M5b-2 (architect A-M5): старая ссылка на строку «Seitentitel» (`?block=__title`:
    закладка, письмо, Студия до деплоя) — адрес окна ★-строки на вкладке «Seite»; вид
    «Telefon», токен окна и язык переводов остаются, подтверждение удаления и раскрытая
    настройка — нет. У страницы без ★-строки — страница без блока. "" — ссылка не старая."""
    if request.method != "GET" or not site_schema.is_title_alias(request.GET.get("block")):
        return ""
    von = _page_path(tenant, request.GET.get("von"), code)  # ревью E1: та же сверка
    keep = {
        k: v
        for k, v in _keep(request.GET, von).items()
        if k in ("ansicht", "wopen", "sprache", "von")
    }
    if site_schema.page_row_ref(tenant, code) != site_schema.PAGE_REF:
        return _url(code, "", keep)
    return _url(code, site_schema.PAGE_REF, {**keep, "tab": "seite"})


def _title_hint(layout: dict, blocks: list[dict], at, host: str) -> dict | None:
    """Метка «Überschrift der Seite · in ★ bearbeiten»: номер ряда `layout.lines`, после
    которого она стоит, и имя окна ★-строки для ссылки. Ряд последнего видимого блока над
    заголовком целиком выше точки заголовка — метка после него; в ряду есть и блок под точкой
    (узкие соседи) — перед этим рядом (ревью M5b-2 №3; -1 — перед первым рядом). None —
    метки нет (`site_schema.title_hint_at`)."""
    from apps.core import page_window

    if at is None:
        return None
    above = [b["ref"] for b in blocks[:at] if b["enabled"]]
    if not above:
        return None
    index = {b["ref"]: i for i, b in enumerate(blocks)}
    for line, li in enumerate(layout.get("lines") or []):
        refs = [b["ref"] for b in li["blocks"]]
        if above[-1] not in refs:
            continue
        whole = all(index.get(r, at) < at for r in refs)
        return {
            "after": line if whole else line - 1,
            "where": page_window.star_name(page_window.label(host), visible=False),
        }
    return None


@login_required
def site_schema_view(request):
    from apps.core import aufbau_draft
    from apps.tenants import siteconfig

    tenant = request.tenant
    code = request.GET.get("seite") or request.POST.get("seite") or "home"
    if request.method == "POST":
        op = request.POST.get("op", "")
        ref = request.POST.get("ref", "")
        pick_value = ""
        if not op and ":" in request.POST.get("pick_op", ""):
            # FB-27 R5: кнопка ручного состава несёт действие и запись одним значением
            action, pick_value = request.POST["pick_op"].split(":", 1)
            op = f"pick_{action}"
        # FB-33 M3-5a: кнопка вкладки окна (без скриптов) применяет форму открытой вкладки —
        # операция формы (`op_default`, белый список), затем открывается выбранная вкладка
        goto = block_window.goto_tab(request.POST)
        if not op and request.POST.get("zu_tab") in block_window.TAB_KEYS:
            # кнопка вкладки — правка формы и тогда, когда вкладки у блока уже нет
            op = block_window.default_op(request.POST)
        applied, notes = False, []
        # FB-27 R2: правки копятся в черновике, на сайт попадают по «Speichern».
        token = request.POST.get("wopen", "")  # FB-33 M3-1b: токен открытия окна
        # FB-33 M5c-2 (ревью H2): форма «⋯» строки схемы — не действие открытого окна: его
        # токен не продолжает окно (снимок «Abbrechen» чужого окна не вытесняется)
        row_form = request.POST.get("zeile") == "1"
        if row_form:
            token = ""
        cancel_kind = ""  # E9: итог «Abbrechen» (`CANCEL_KINDS`), пусто — отмены не было
        try:
            if op == "revert":
                # FB-33 M3-1b: «Abbrechen» — блок как на момент открытия окна; итог честный.
                # E9 (стопка 14): у строки блока итог — в адресе (`abbruch`), сообщение — у
                # строки; нет строки с ссылкой (★-строка, блок удалён) — вверху, ниже
                done = aufbau_draft.cancel(request, tenant, code, ref, token)
                cancel_kind = _cancel_kind(done)
            elif op == "save":
                force = request.POST.get("force") == "1"
                said: list[str] = []  # FB-33 M2i-5: что запись поправила (способ связи)
                if aufbau_draft.commit(request, tenant, code, force=force, notes=said):
                    messages.success(request, _("Gespeichert."))
                    for note in said:
                        messages.warning(request, note)
                else:
                    messages.error(
                        request,
                        _("Es gibt keinen Entwurf mehr – bitte die Änderungen erneut vornehmen."),
                    )
                ref = ""
            elif op == "discard":
                aufbau_draft.discard(request, code)
                messages.success(request, _("Änderungen verworfen."))
                ref = ""
            elif op == "setting":
                # FB-27 R4: настройка типа страницы — в черновик. `out_mode` — сентинел
                # оси вывода: без него сохранённые ряды/лента остаются как были.
                if "value" not in request.POST:
                    # Сохранённое значение больше нельзя выбрать (плитка отключена) —
                    # браузер не прислал ничего. Пустое значение означало бы «Standard»
                    # и молча стёрло бы настройку.
                    raise site_schema.SchemaError("value")
                output = (
                    page_settings.output_payload(request.POST, "out")
                    if "out_mode" in request.POST
                    else None
                )
                skipped = aufbau_draft.setting_op(
                    request,
                    tenant,
                    code,
                    request.POST.get("setting", ""),
                    request.POST.get("value", ""),
                    output=output,
                    apply_all=request.POST.get("apply_all") == "1",
                    ref=ref,  # FB-33 M3-1b: снимок окна ★/строки-носителя
                    token=token,
                )
                if skipped:
                    from apps.core import studio_pages

                    names = [
                        str(studio_pages.page_type(page_settings.APPLY_ALL_TYPES[c]).label)
                        for c in skipped
                    ]
                    messages.warning(
                        request,
                        _("Nicht übernommen (diese Ansicht gibt es dort nicht): %(lists)s")
                        % {"lists": ", ".join(names)},
                    )
            else:
                if op in ("catview", "mainview", "maingroup"):
                    # ревью R5b: недоступный вид (нет подкатегорий/наборов) не берём и в
                    # обход плиток — только тот, что можно выбрать на экране
                    site_schema.check_view_available(
                        aufbau_draft.overlay(
                            siteconfig.normalize(tenant.site_config),
                            aufbau_draft.get(request, code),
                        )
                        if aufbau_draft.get(request, code)
                        else siteconfig.normalize(tenant.site_config),
                        site_schema.host_for(code),
                        ref,
                        request.POST.get("value", ""),
                        op,
                    )
                notes: list[str] = []  # FB-33 M2i-5: сообщения вкладки «Felder»
                ref = aufbau_draft.op(
                    request,
                    tenant,
                    code,
                    op,
                    ref=ref,
                    block_type=request.POST.get("type", ""),
                    value=pick_value or request.POST.get("value", ""),
                    # Сентинел панели: без него поля не читаются (кнопки «выше/ниже»
                    # той же страницы не должны стирать текст блока).
                    fields=_panel_fields(request.POST),
                    token=token,
                    notes=notes,
                    # FB-33 M5c-1: позиция вставки — своим полем, только у вставки
                    after=request.POST.get("after", "") if op in INSERT_OPS else "",
                    # ревью L3: правка строкой — окно этого блока «Abbrechen» её не откатит
                    row_edit=row_form,
                )
                for note in notes:
                    messages.warning(request, note)
                # S8: у действий выбора баннера — сообщение (после «убрать» кнопка, на
                # которой стоял фокус, исчезает; читатель экрана слышит, что произошло).
                said = _PICK_SAID.get(op)
                if said and request.POST.get("pick_op"):
                    messages.success(request, said)
        except page_settings.PageSettingError:
            if op == "save":
                # Черновик остаётся: владелец видит, что именно не записалось, и может
                # поправить настройку или отбросить черновик.
                messages.error(
                    request,
                    _(
                        "Nicht gespeichert: Eine Einstellung im Entwurf ist nicht mehr "
                        "möglich. Bitte die Einstellungen prüfen oder den Entwurf verwerfen."
                    ),
                )
            else:
                messages.error(request, _("Diese Änderung ist hier nicht möglich."))
        except site_schema.SchemaError as exc:
            if exc.args and exc.args[0] == "full" and op in ("add", "add_row", "adopt"):
                messages.error(request, _("Auf dieser Seite ist kein Platz für weitere Blöcke."))
            elif exc.args and exc.args[0] == "hosts":
                messages.error(
                    request,
                    _(
                        "So viele Kategorien mit eigenem Aufbau sind nicht möglich. "
                        "Bitte zuerst bei einer anderen Kategorie die eigenen Blöcke entfernen."
                    ),
                )
            elif exc.args and exc.args[0] == "ids":
                messages.error(
                    request,
                    _(
                        "Keine weitere Frage möglich: Die Nummern für eigene Fragen sind "
                        "aufgebraucht."
                    ),
                )
            elif exc.args and exc.args[0] == "rights":
                messages.error(
                    request,
                    _(
                        "Abschnitte dieser Seite darf nur ändern, wer auch das Angebot "
                        "selbst bearbeiten darf."
                    ),
                )
            elif exc.args and exc.args[0] in ("ofaq_rights", "ofaq_conflict"):
                from apps.core import object_faq  # FB-33 M2b-2b: свои вопросы объекта

                messages.error(request, object_faq.error_note(exc.args[0]))
            elif exc.args and exc.args[0] == "objects":
                messages.error(
                    request,
                    _(
                        "So viele Seiten mit eigenen Blöcken sind nicht möglich. Bitte zuerst "
                        "bei einem anderen Produkt oder einer Leistung die eigenen Blöcke "
                        "entfernen."
                    ),
                )
            elif exc.args and exc.args[0] == "btr_conflict":
                # FB-33 M3-5c: переводы текстов блока изменили в Студии/на канве — черновик цел
                from apps.core import block_i18n

                messages.error(request, block_i18n.conflict_note())
            elif exc.args and exc.args[0] == "faq_conflict":
                # FB-33 M3-5b: общие вопросы FAQ изменили в Студии/на канве — черновик цел
                from apps.core import faq_content

                messages.error(request, faq_content.faq_changed_note())
            elif exc.args and _m36_error(exc.args[0]):
                # FB-33 M3-6: «Wo zeigen» баннера в окне блока
                messages.error(request, _m36_error(exc.args[0]))
            else:
                messages.error(request, _("Diese Änderung ist hier nicht möglich."))
        except aufbau_draft.DraftConflict:
            messages.error(
                request,
                _(
                    "Diese Seite wurde inzwischen an anderer Stelle geändert. "
                    "Ihr Entwurf wurde nicht gespeichert."
                ),
            )
        else:
            # FB-33 M3-5a: ни одна ветка отказа не сработала. Отказ без исключения бывает только
            # у «Abbrechen» (CANCEL_CONFLICT) — переход по вкладке его не касается: он идёт
            # лишь с правкой формы (op из OP_DEFAULTS, см. `moved`)
            applied = True
        # Блок остаётся выбранным (новый — тоже), удалённый — нет.
        # FB-33 M3-1b: «Fertig» и «Abbrechen» закрывают окно блока
        closed = op in ("delete", "revert") or op in aufbau_draft.WINDOW_OPS
        # E1 (ревью M2): `von` из формы — сверка заново, подделанный не попадает в адрес
        keep = _keep(request.POST, _page_path(tenant, request.POST.get("von"), code))
        if op in INSERT_OPS:
            # FB-33 M5c-1: новый блок — новое открытие окна (токен и вкладку выдаёт GET), а не
            # продолжение окна, из которого пришла форма; отказ окно закрывает
            for key in ("wopen", "tab", "sprache"):
                keep.pop(key, None)
            if not applied:
                ref = ""
            elif ref:
                keep["neu"] = ref  # FB-33 M5c-3: окно нового блока — фокус и сообщение о вставке
        # FB-33 M3-5a: на выбранную вкладку — только если правка прошла без отказа и без
        # сообщений (иначе владелец остаётся там, где видит, что не так)
        moved = bool(
            goto and applied and op in block_window.OP_DEFAULTS and not notes and not closed and ref
        )
        if moved:
            keep["tab"] = goto
        if (op in aufbau_draft.WINDOW_OPS or op == "revert") and ref:
            # FB-33 M5c-3 (a11y B4): после «Fertig» «＋ Block» остаётся под этой строкой.
            # M5d-2b: и после «Abbrechen» — по `zuletzt` список «Ausgeblendet» остаётся раскрытым
            # у скрытой строки (фокус на её ссылку ставит `aufbau.js`)
            keep["zuletzt"] = ref
        cancel_row = bool(
            cancel_kind
            and ref
            and site_schema.page_ref(ref) != site_schema.PAGE_REF
            and ref in _linked_refs(request, tenant, code)
        )
        if cancel_row:
            # E9 (решение владельца 2026-11-24): итог «Abbrechen» — белым списком, GET пишет
            # сообщение у строки и сверяет `zuletzt` со строками схемы
            keep["abbruch"] = cancel_kind
        elif cancel_kind:
            # ★-строка страницы, блок удалён в другой вкладке, общая строка, пустой ref —
            # строки с ссылкой нет: итог не теряется, а стоит вверху (ревью E9)
            messages.add_message(request, *_cancel_text(cancel_kind))
        target = _url(code, "" if closed else ref, keep)
        if (op in aufbau_draft.WINDOW_OPS or cancel_row) and ref:
            # FB-33 M5c-3 (a11y B3): «Fertig» без скриптов — к строке блока (её ⚙); E9: и
            # «Abbrechen» строки блока
            target = f"{target}#schema-row-{quote(ref, safe='')}"
        if row_form:
            # FB-33 M5c-2: из «⋯» строки — окно не открывается; фокус и сообщение «ist jetzt
            # Nummer n» — у строки (`bewegt`: GET сверяет его со строками схемы). Тот же id
            # (`schema-more-<ref>`) у «⋯» видимой строки и у «Einblenden» скрытой
            target = _url(code, "", keep)
            if applied and ref:
                target = f"{target}&{urlencode({'bewegt': ref})}#schema-more-{quote(ref, safe='')}"
        lang = request.POST.get("f_sprache", "")
        if "#" in target and lang and _keep({"f_sprache": lang}).get("sprache") == lang:
            # FB-33 M2i-5b (ревью a11y): после кнопки языка фокус — на ней (`#schema-tab-…`
            # ставит фокус по id и окно, и страница без окна; без JS — прокрутка к ней)
            target = f"{target.split('#', 1)[0]}#schema-tab-lang-{lang}"
        felder = applied and not notes and "#" in target and request.POST.get("f_do")
        if felder:
            # FB-33 M3-5a (a11y M2i-5): после ↑/↓/Entfernen/«+ Frage» — фокус на вопрос
            form_state = (aufbau_draft.get(request, code) or {}).get("form")
            anchor = block_window.felder_anchor(request.POST, form_state)
            if anchor:
                target = f"{target.split('#', 1)[0]}#{anchor}"
                # a11y (ревью): что произошло — живой областью вкладки и окна
                said = block_window.felder_said(request.POST)
                if said:
                    messages.success(request, said)
        if applied and not notes and "#" in target and request.POST.get("faq_present") == "1":
            # стопка 2 (a11y M3-5b): после ↑/↓/Entfernen/нового вопроса FAQ — фокус на вопрос
            from apps.core import faq_content, window_parts

            faq_draft = aufbau_draft.get(request, code) or {}
            count = len(faq_content.state(siteconfig.normalize(tenant.site_config), faq_draft)[0])
            opened = request.session.get(aufbau_draft.FAQ_OPENED)
            anchor = window_parts.faq_anchor(request.POST, count, opened)
            if anchor:
                target = f"{target.split('#', 1)[0]}#{anchor}"
        if moved:
            target = f"{target.split('#', 1)[0]}#schema-tab-{goto}"
        if op == "places" and applied and "#" in target:
            # FB-33 M3-6 (a11y ревью): после кнопки «Wo zeigen» фокус — на её заголовок
            target = f"{target.split('#', 1)[0]}#schema-tab-places"
        if op == "setting" and "#" in target:
            # Настройка, которую только что меняли, остаётся раскрытой.
            base, anchor = target.split("#", 1)
            opened = urlencode({"offen": request.POST.get("setting", "")})
            target = f"{base}&{opened}#{anchor}"
        if request.POST.get("zurueck") == "seiten":
            # FB-27 «Seiten»: действие пришло со вкладки «Blöcke» страницы — возвращаемся
            # туда. Адрес — по имени маршрута из кода страницы, не из запроса.
            from apps.core import content_pages

            back = content_pages.edit_url_for_code(code)
            if back:
                return redirect(f"{back}?tab=bloecke")
        return redirect(target)
    saved = siteconfig.normalize(tenant.site_config)
    groups = site_schema.type_groups(tenant, saved)
    # FB-29.4b: свои блоки объекта — строки нет в списке типов, добавляем её одну.
    own_row = site_schema.object_row(saved, code)
    if own_row is not None:
        groups = [*groups, (str(_("Nur diese Seite")), [own_row])]
    rows = [r for _label, items in groups for r in items]
    # Тип, которого у бизнеса нет (или мусор в адресе), не открывается — главная.
    current = next((r for r in rows if r.code == code), rows[0] if rows else None)
    code = current.code if current else "home"
    old = _old_title_link(request, tenant, code)
    if old:
        return redirect(old)
    # FB-31 P5 R7 (ревью): старая ссылка на настройку со строки «Seite» (закладка, письмо)
    # ведёт на строку раздела, где она теперь живёт
    moved = site_schema.SETTING_ROWS.get(code, {}).get(request.GET.get("offen", ""))
    if moved and request.GET.get("block") == site_schema.PAGE_REF:
        return redirect(site_schema.settings_url(code, request.GET["offen"]))
    draft = aufbau_draft.get(request, code)
    # FB-33 M4c: окно показывает СВОИ оси блока и при охвате «Den ganzen Typ» (вид типа —
    # в предпросмотре): иначе «Übernehmen» без правок стёрло бы вид типа
    config = aufbau_draft.overlay(saved, draft, scope=False) if draft else saved
    from apps.core import form_spec

    if config.get(form_spec.FORM_ERROR_KEY):
        # FB-33 M2i-5 (ревью): черновик вкладки «Felder» не показать — видно, а не молча
        logger.warning("aufbau draft: form tab draft not shown (%s, %s)", tenant.schema_name, code)
        messages.warning(
            request,
            _("Keine weitere Frage möglich: Die Nummern für eigene Fragen sind aufgebraucht."),
        )
    draft_info = aufbau_draft.info(request, saved, code)
    # FB-33 M5b-2 / стопка 14 E8: имя главного списка («Menü-Pakete» у гастро) — в самой
    # `blocks_for` по тенанту
    blocks = site_schema.blocks_for(
        config, code, host=current.host if current else None, tenant=tenant
    )
    host = (current.host if current else "") or ""
    # FB-27 V3 / FB-33 M5b-1 / M5b-2 (V4): настройки типа живут в ★-строке страницы
    # («Seitentitel und Seite» / «Einstellungen der Seite»), на главной — в строке «Banner»:
    # одно правило, флаг носителя — до выбора строки
    page_ref = site_schema.page_row_ref(tenant, code, blocks)
    carrier = next((b for b in blocks if b["ref"] == page_ref), None)
    if carrier is not None:
        carrier["carrier"] = True
    selected = next((b for b in blocks if b["ref"] == request.GET.get("block")), None)
    from apps.core import page_window

    # FB-33 M3-6 / M5b-2: ★-строка страницы — тем же окном блока (вкладка «Seite»)
    selected = selected or page_window.pseudo_row(
        request.GET.get("block", ""), page_ref, host, config
    )
    page_window.list_links(selected, blocks, page_ref, host)
    if selected and selected.get("list_data") is not None:
        from apps.core import list_panel

        selected["groups"] = list_panel.groups(
            request,
            config,
            selected["list_data"],
            request.GET.get("welche", ""),
            # FB-33 M4c: «Ansicht gilt für» — выбор из черновика; без права на типы поля нет
            scope=aufbau_draft.scope_of(draft, selected["ref"])
            if list_panel.scope_allowed(request)
            else None,
        )
        # a11y (ревью A3): при охвате «Den ganzen Typ» строка наследования не говорит «nur diesen»
        selected["scope_type"] = bool(aufbau_draft.scope_of(draft, selected["ref"]))
        selected["result"] = list_panel.result(request, config, selected["list_data"])
        selected["pick"] = list_panel.pick_state(request, selected["list_data"])
        selected["which"] = next(
            (g.get("mode", "") for g in selected["groups"] if g["key"] == "welche"), ""
        )
        selected.update(list_panel.source_link(selected["list_data"]))
    if selected and selected.get("builtin_data") is not None:
        # FB-27 (макет Main): встроенный список главной — та же панель «Welche · Wie»
        from apps.core import list_panel

        selected["groups"] = list_panel.builtin_groups(
            request,
            config,
            selected["key"],
            selected["builtin_data"],
            request.GET.get("welche", ""),
        )
        selected["result"] = list_panel.result(request, config, selected["builtin_data"])
        selected["which"] = next(
            (g.get("mode", "") for g in selected["groups"] if g["key"] == "welche"), ""
        )
        selected.update(list_panel.source_link(selected["builtin_data"]))
    if selected and selected.get("banner_choice") is not None:
        # FB-29.2: баннеры места показа — выбор из библиотеки и настройки слайдера
        from apps.core import banners

        selected["banner_pick"] = banners.pick_state(
            request,
            selected["banner_choice"],
            place_capable=bool(selected.get("cblock"))
            and site_schema.place_capable(current.host if current else ""),
        )

    # FB-33 M3-6: подписи плиток и «Wo zeigen»; SEO и наследование у «Seite»; закреплённые 🔒
    from apps.core import legal_buttons, window_banner

    window_banner.decorate(selected, config, draft, request)
    page_window.decorate(selected, config, current.host if current else "", code)
    legal_buttons.decorate(selected, current.host if current else "", config)
    for view_key in ("catview", "mainview", "groupview"):
        if selected and selected.get(view_key):
            site_schema.mark_view_availability(config, current.host, selected[view_key])
    if selected and selected.get("fields"):
        site_schema.fill_options(selected, current.host if current else "")
    # FB-33 M3-3a: виды картинками — из уже заполненных пунктов (вкладка «Wie anordnen»)
    from apps.core import block_card, block_views

    block_views.decorate(selected, blocks, config, current.host if current else "")
    block_card.decorate(selected, config)  # FB-33 M3-4: «Kartenform» — во вкладку «Karte»
    if selected and selected.get("form_spec"):
        # FB-33 M2i-5: «Branchen-Vorlage» — только у типа бизнеса с пресетом формы
        from apps.jobs.anfrage_presets import preset_for

        selected["form_spec"]["preset"] = bool(
            preset_for(tenant.business_type, form=selected["form_spec"]["form"])
        )
        # FB-33 C5: у корзины — подсказки по онлайн-оплате и заказу к столику
        from apps.core import checkout_window

        checkout_window.decorate(selected, tenant)
        # FB-33 M2i-5b: переводы подписей и вариантов — на языки бизнеса (один язык — нет)
        from apps.core import i18n_input

        form_spec.with_locales(
            selected["form_spec"],
            i18n_input.extra_locales(tenant),
            request.GET.get("sprache", ""),
        )
    # FB-33 M3-5b: вопросы FAQ («Texte») и плашки Schnellzugriff («Was») окна блока
    from apps.core import window_parts

    window_parts.decorate(
        selected,
        saved,
        draft,
        code == "home",
        config,
        current.host if current else "",
        request.session.pop(aufbau_draft.FAQ_OPENED, None) if selected else None,
        user=getattr(request, "user", None),  # FB-33 M2b-2b (ревью): своё право на вопросы
    )
    # FB-33 M3-5c: переводы текстов блока, вопросов FAQ и подписей плашек — в окне (языки
    # бизнеса кнопками; один язык — окно прежнее)
    from apps.core import block_i18n, i18n_input

    block_i18n.decorate(
        selected,
        saved,
        draft,
        config,
        code == "home",
        current.host if current else "",
        i18n_input.extra_locales(tenant),
        request.GET.get("sprache", ""),
        getattr(tenant, "default_locale", ""),
    )
    if (
        selected
        and (selected["key"] == "anfrage" and not selected["cblock"] or _is_anfrage_ref(selected))
        and tenant.is_module_active("jobs")
    ):
        # FB-33 M2i-5: полоса заявки главной и блок «Anfrage» — поля правятся в окне формы
        # страницы «Anfrage» (одна настройка на все места формы, без дубля)
        selected["form_link"] = site_schema.form_window_url()
    # FB-27 R4 / FB-33 M5b-2: настройки типа страницы — на ★-строке страницы (`page_ref`
    # выше), у главной — на строке «Banner».
    page_row, settings, design_rows = None, [], []
    if page_ref == site_schema.PAGE_REF:
        star = page_window.pseudo_row(page_ref, page_ref, host, config)
        page_row = {
            "ref": site_schema.PAGE_REF,
            "label": star["label"],
            "summary": star["summary"],
            "active": request.GET.get("block") == site_schema.PAGE_REF,
        }
    if (selected and selected.get("carrier")) or (page_row and page_row["active"]):
        settings = site_schema.settings_groups(tenant, code, config)
        design_rows = site_schema.design_rows(tenant, code)
    # FB-31 P5 R7: строка раздела со своими настройками («Ähnliche › Wie»)
    if selected and site_schema.row_settings(code, selected["ref"]):
        selected["setting_row"] = True
        settings = site_schema.settings_groups(tenant, code, config, row=selected["ref"])
        wanted = site_schema.SETTING_ROW_DESIGN.get(selected["ref"], ())
        design_rows = [d for d in site_schema.design_rows(tenant, code) if d["code"] in wanted]
        row_view = (
            site_schema.related_view(config)
            if selected["ref"] == "related"
            else site_schema.related_view(config, "cart_upsell_layout")
            if selected["ref"] == "upsell"
            else {}
        )
    else:
        row_view = {}
    # FB-29.5: с кем выбранный блок стоит в одном ряду (подсказка под кнопками ширины)
    width_mates = []
    if selected and selected.get("enabled"):
        for row in site_schema.schema_layout(blocks)["rows"]:
            if any(b["ref"] == selected["ref"] for b in row):
                width_mates = [b["label"] for b in row if b["ref"] != selected["ref"]]
    # E1: страница, с которой открыли окно (`von`, сверка раз на запрос) — и для «Auf der
    # Seite bearbeiten», и для «Vorschau»; без неё — образец типа
    von = _page_path(tenant, request.GET.get("von"), code)
    preview_url = von or (current.preview_url if current else "")
    studio = reverse("site-home")
    if preview_url:
        studio = f"{studio}?{urlencode({'page': preview_url})}"
    preview_query = (
        {"preview": "1", "aufbau": code} if draft else {"preview": "1", "stand": "saved"}
    )
    labels = {r.code: r.label for r in rows}
    # FB-29.4b (ревью): черновики своих блоков других объектов остаются и видны в списке
    # «weitere Entwürfe» — строки объектов в общий выбор не входят.
    for other in aufbau_draft.dirty_codes(request):
        if other not in labels and site_schema.is_object_code(other):
            row = site_schema.object_row(saved, other)
            if row is not None:
                labels[other] = row.label
    aufbau_draft.prune(request, labels)
    other_drafts = [
        {"code": c, "label": labels[c]}
        for c in aufbau_draft.dirty_codes(request)
        if c != code and c in labels
    ]
    layout = site_schema.schema_layout(blocks)
    # FB-33 M5c-2: номера строк — только показ (окно и действия — по ref)
    numbers = site_schema.row_numbers(layout)
    for b in blocks:
        b["num"] = numbers.get(b["ref"])
    # после перестановки из «⋯» строки: что с ней стало — по этой же схеме (белый список)
    wanted_moved = request.GET.get("bewegt", "")
    moved = next((b for b in blocks if b["ref"] == wanted_moved), None) if wanted_moved else None
    moved_msg = ""
    # FB-33 M5c-3: «＋ Block» под выбранной видимой строкой — после ПОСЛЕДНЕГО блока её ряда,
    # который есть в строках страницы (общие строки объекта — нет; «Buchung» — цель позиции)
    add_at = None
    anchor = selected
    if anchor is None and request.GET.get("zuletzt"):
        # после «Fertig» — строка, чьё окно только что закрыли (белый список — строки схемы)
        anchor = next((b for b in blocks if b["ref"] == request.GET["zuletzt"]), None)
    if anchor is not None and anchor.get("num"):
        for line_no, li in enumerate(layout["lines"]):
            if not any(b["ref"] == anchor["ref"] for b in li["blocks"]):
                continue
            last = next((b for b in reversed(li["blocks"]) if not b.get("shared")), None)
            if last is not None:
                add_at = {"line": line_no, "ref": last["ref"], "name": last["label"]}
            break
    # FB-33 M5c-3 (a11y B3): после вставки — что вставили и под каким номером (белый список:
    # `neu` = выбранный блок)
    inserted_msg = ""
    if selected is not None and selected.get("num") and request.GET.get("neu") == selected["ref"]:
        inserted_msg = _(
            "Block „%(name)s“ eingefügt, Nummer %(n)s. Der Block bleibt — entfernen über „⋯“."
        ) % {"name": selected["label"], "n": selected["num"]}
    if moved is not None and moved.get("num"):
        moved_msg = _("Block „%(name)s“ ist jetzt Nummer %(n)s von %(total)s.") % {
            "name": moved["label"],
            "n": moved["num"],
            "total": len(numbers),
        }
    # E9 (стопка 14, a11y H1): итог «Abbrechen» — статичным абзацем перед строкой блока (белый
    # список `abbruch`; `zuletzt` — точно ref строки схемы, у которой есть ссылка). Вверху его
    # нет; живая область пуста — текст туда кладёт `aufbau.js` (ветка `back`)
    cancel_ref, cancel_kind, cancel_msg = "", "", ""
    if selected is None and request.GET.get("abbruch") in CANCEL_KINDS:
        if anchor is not None and not anchor.get("shared"):
            cancel_ref, cancel_kind = anchor["ref"], request.GET["abbruch"]
            cancel_msg = _cancel_text(cancel_kind)[1]
        else:
            # страховка (ревью E9): строки уже нет — итог вверху, а не молча
            messages.add_message(request, *_cancel_text(request.GET["abbruch"]))
    # FB-33 M5b-2 (V4, a11y Y-H2): серая метка «Überschrift der Seite» — только в разметке,
    # после ряда с последним видимым блоком над заголовком (не строка: не в `blocks`/рядах)
    title_hint = None
    if page_ref == site_schema.PAGE_REF:
        title_hint = _title_hint(layout, blocks, site_schema.title_hint_at(host, blocks), host)
    confirm_remove = bool(selected) and request.GET.get("entfernen") == "1"
    # FB-33 M5d-2: объект строки «Nur diese Seite» ищем один раз — он же в ссылке «назад»
    from apps.core import detail_parts

    row_object = detail_parts.object_for_host(host) if site_schema.is_object_code(code) else None
    object_back = site_schema.object_back(code, row_object)
    # FB-33 M5d-1 / M5d-2: «Inhalt» — что показывает строка и где правится её содержимое
    window_parts.content_part(
        selected,
        host,
        request,
        code=code,
        obj=row_object,
        back=object_back,
        page_label=str(current.label) if current else "",
    )
    # FB-33 M3-1: окно блока — части панели по вкладкам (`block_window`)
    window = block_window.tabs(
        selected, {"settings": settings, "design_rows": design_rows}, request.GET.get("tab", "")
    )
    bw_preview = (
        _block_preview(request, code, current, selected, preview_url)
        if selected and block_window.has_preview(window) and not confirm_remove and preview_url
        else None
    )
    return render(
        request,
        "tenant/site_schema.html",
        {
            "nav": "site-schema",
            "groups": groups,
            "current": current,
            "code": code,
            "preview_url": preview_url,
            "preview_query": urlencode(preview_query),
            # FB-33 M3-7: «Vorschau» в окне блока — кадр черновика, прокрученный к блоку
            "bw_preview": bw_preview,
            "blocks": blocks,
            "layout": layout,
            "title_hint": title_hint,
            # FB-33 M5c-2: сообщение после перестановки и раскрытый «Ausgeblendet» после скрытия
            "moved_msg": moved_msg,
            "moved_hidden": moved is not None and not moved["enabled"],
            # E9: сообщение «Abbrechen» у строки (`cancel_ref`); вид — `cancel_kind`
            "cancel_ref": cancel_ref,
            "cancel_kind": cancel_kind,
            "cancel_msg": cancel_msg,
            "add_at": add_at,  # FB-33 M5c-3
            # ревью L2: «Fertig» у скрытого блока — якорь #schema-row в раскрытом «Ausgeblendet»
            "last_hidden": selected is None and anchor is not None and not anchor["enabled"],
            "inserted_msg": inserted_msg,
            **_row_ops(layout, selected),
            "selected": selected,
            "confirm_remove": confirm_remove,
            "window": window,
            # FB-33 M3-1b: токен открытия окна — тот же, пока владелец в этом окне
            "wopen": (
                aufbau_draft.clean_token(request.GET.get("wopen")) or aufbau_draft.new_token()
            )
            if selected
            else "",
            # токен НОВОГО открытия — в ссылках на блоки (F5 остаётся тем же открытием)
            "wopen_link": aufbau_draft.new_token(),
            # вкладка, которую формы окна помнят после действия: только явно открытая
            "window_tab": block_window.explicit_tab(window, request.GET.get("tab", "")),
            # FB-33 M2i-5b: язык переводов вкладки «Felder» — переживает действие окна
            # FB-33 M3-5c: и язык переводов текстов блока (у строки — одна из двух вкладок)
            "form_lang": ((selected or {}).get("form_spec") or {}).get("lang", "")
            or ((selected or {}).get("field_langs") or {}).get("lang", ""),
            # FB-27 R7: строка категории — своя схема или блоки каталога
            "category_row": (
                {"own": any(not b["main"] and not b["fixed"] for b in blocks)}
                if code.startswith(f"{site_schema.CATEGORY}@")
                else None
            ),
            # FB-29.4b S8: со строки своих блоков объекта — ссылка назад к нему
            "object_back": object_back,
            # R8: общие блоки в схеме объекта — правятся на общей схеме его типа страницы
            "shared_url": site_schema.shared_schema_url(code),
            "add_groups": site_schema.add_groups(code, saved),
            "row_options": site_schema.row_options(),
            "studio_url": studio,
            "draft": draft_info if draft else None,
            "other_drafts": other_drafts,
            "page_row": page_row,
            "settings": settings,
            "settings_ref": selected["ref"] if selected else site_schema.PAGE_REF,
            **row_view,  # FB-31 P5 R7: «Ähnliche › Wie»
            "design_rows": design_rows,
            "open_setting": request.GET.get("offen", ""),
            # единственная настройка раскрыта сразу — иначе панель выглядит пустой
            "settings_single": sum(len(g["settings"]) for g in settings) == 1,
            # FB-27 V4: вид схемы «как на телефоне» — блоки друг под другом
            "phone_view": request.GET.get("ansicht") == "telefon",
            "width_mates": width_mates,
            "which": (selected or {}).get("which", ""),
            # Вид «Telefon» — во всех ссылках экрана (способ «Welche» — только в формах)
            "keep_q": ("&ansicht=telefon" if request.GET.get("ansicht") == "telefon" else "")
            + (f"&{urlencode({'von': von})}" if von else ""),
            # E1: проверенный путь страницы — скрытым полем всех форм (`_schema_keep.html`)
            "von": von,
            # Панель правит текст ОСНОВНОГО языка; при нескольких языках — подсказка.
            "multi_lang": len(tenant.active_locales) > 1,
        },
    )
