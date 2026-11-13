"""FB-25 / FB-27: экран «Website › Seitenaufbau» — схема страницы рядами и её правка."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext as _

from apps.core import page_settings, site_schema


def _url(code: str, block: str = "") -> str:
    query = {"seite": code}
    if block:
        query["block"] = block
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
        # FB-27 R2: правки копятся в черновике, на сайт попадают по «Speichern».
        try:
            if op == "save":
                force = request.POST.get("force") == "1"
                if aufbau_draft.commit(request, tenant, code, force=force):
                    messages.success(request, _("Gespeichert."))
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
                )
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
        # Блок остаётся выбранным (новый — тоже), удалённый — нет.
        target = _url(code, "" if op == "delete" else ref)
        if op == "setting" and "#" in target:
            # Настройка, которую только что меняли, остаётся раскрытой.
            base, anchor = target.split("#", 1)
            opened = urlencode({"offen": request.POST.get("setting", "")})
            target = f"{base}&{opened}#{anchor}"
        return redirect(target)
    saved = siteconfig.normalize(tenant.site_config)
    groups = site_schema.type_groups(tenant, saved)
    rows = [r for _label, items in groups for r in items]
    # Тип, которого у бизнеса нет (или мусор в адресе), не открывается — главная.
    current = next((r for r in rows if r.code == code), rows[0] if rows else None)
    code = current.code if current else "home"
    draft = aufbau_draft.get(request, code)
    config = aufbau_draft.overlay(saved, draft) if draft else saved
    draft_info = aufbau_draft.info(request, saved, code)
    blocks = site_schema.blocks_for(config, code, host=current.host if current else None)
    selected = next((b for b in blocks if b["ref"] == request.GET.get("block")), None)
    if selected and selected.get("list_data") is not None:
        from apps.core import list_panel

        selected["groups"] = list_panel.groups(request, config, selected["list_data"])
        selected["result"] = list_panel.result(request, config, selected["list_data"])
        selected["pick"] = list_panel.pick_state(request, selected["list_data"])
    if selected and selected.get("fields"):
        site_schema.fill_options(selected, current.host if current else "")
    # FB-27 R4: настройки типа страницы — в панели «★ Hauptliste», а у страниц без
    # основного списка — на строке «Einstellungen der Seite».
    page_row, settings = None, []
    try:
        has_settings = bool(site_schema.setting_codes(tenant, code))
    except site_schema.SchemaError:
        has_settings = False
    if has_settings:
        main = next((b for b in blocks if b["main"]), None)
        if main is None:
            page_row = {
                "ref": site_schema.PAGE_REF,
                "active": request.GET.get("block") == site_schema.PAGE_REF,
            }
        if (selected and selected["main"]) or (page_row and page_row["active"]):
            settings = site_schema.settings_groups(tenant, code, config)
    preview_url = current.preview_url if current else ""
    studio = reverse("site-home")
    if preview_url:
        studio = f"{studio}?{urlencode({'page': preview_url})}"
    preview_query = (
        {"preview": "1", "aufbau": code} if draft else {"preview": "1", "stand": "saved"}
    )
    labels = {r.code: r.label for r in rows}
    aufbau_draft.prune(request, labels)
    other_drafts = [
        {"code": c, "label": labels[c]}
        for c in aufbau_draft.dirty_codes(request)
        if c != code and c in labels
    ]
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
            "blocks": blocks,
            "layout": site_schema.schema_layout(blocks),
            "selected": selected,
            "confirm_remove": bool(selected) and request.GET.get("entfernen") == "1",
            # FB-27 R7: строка категории — своя схема или блоки каталога
            "category_row": (
                {"own": any(not b["main"] and not b["fixed"] for b in blocks)}
                if code.startswith(f"{site_schema.CATEGORY}@")
                else None
            ),
            "add_groups": site_schema.add_groups(code, saved),
            "row_options": site_schema.row_options(),
            "studio_url": studio,
            "draft": draft_info if draft else None,
            "other_drafts": other_drafts,
            "page_row": page_row,
            "settings": settings,
            "settings_ref": selected["ref"] if selected else site_schema.PAGE_REF,
            "shared_settings": site_schema.SHARED_SETTINGS,
            "open_setting": request.GET.get("offen", ""),
            # Панель правит текст ОСНОВНОГО языка; при нескольких языках — подсказка.
            "multi_lang": len(tenant.active_locales) > 1,
        },
    )
