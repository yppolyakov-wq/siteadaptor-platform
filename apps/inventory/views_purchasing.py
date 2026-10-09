"""Склад-2 E3.2: кабинет закупок (Einkauf) — Bestellungen + Lieferanten + Wareneingang.

Один экран: список заказов (+ ?po=<pk> — детали/строки/приёмка), поставщики в
свёртке, кнопка «из Bestellvorschlägen». Счётчик двигает ТОЛЬКО приёмка через
`purchasing.receive_po_line` (складской путь, D1)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import maengel, purchasing, services
from .models import BestellPosition, Bestellung, Lieferant, Maengelanzeige, Mangel, StockLocation
from .views import _int, _parse_date, _resolve_entity, _resolve_location, _threshold


def _uuid(raw):
    """UUID из POST или None: мусорная строка в фильтре по UUID-pk роняла бы 500."""
    import uuid

    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError, AttributeError):
        return None


def _redirect(po=None):
    url = "/dashboard/purchasing/"
    return redirect(f"{url}?po={po.pk}" if po is not None else url)


@login_required
def purchasing_view(request):
    if request.method == "POST":
        return _handle_post(request)

    pos = list(Bestellung.objects.select_related("supplier").prefetch_related("positions")[:100])
    # ERP-8: бейдж открытых рекламаций в списке заказов (один запрос на страницу)
    open_maengel = maengel.open_counts([po.pk for po in pos])
    for po in pos:
        po.open_maengel = open_maengel.get(po.pk, 0)
    current = None
    anzeigen = []
    po_id = request.GET.get("po")
    if po_id:
        current = (
            Bestellung.objects.select_related("supplier")
            .prefetch_related("positions__product", "positions__variant")
            .filter(pk=po_id)
            .first()
        )
    if current is not None:
        anzeigen = list(
            current.maengel.prefetch_related(
                "maengel__position__product", "maengel__position__variant"
            )
        )
    return render(
        request,
        "inventory/purchasing.html",
        {
            "nav": "purchasing",
            "pos": pos,
            "current": current,
            "suppliers": purchasing.suppliers(active_only=False),
            "entities": services.stock_entities(),
            "reorder": services.reorder_suggestions(_threshold(request.tenant)),
            "lots_on": services.lots_enabled(request.tenant),
            "statuses": Bestellung.STATUSES,
            # E2: селектор Standort на приёмке (виден при локациях > 1)
            "stock_locations": list(StockLocation.objects.filter(is_active=True)),
            # ERP-8: рекламации поставщику по этой поставке
            "anzeigen": anzeigen,
            "defect_types": maengel.DEFECT_TYPES,
            "decisions": Mangel.DECISIONS,
        },
    )


@login_required
def maengel_pdf(request, pk):
    """ERP-8: PDF-бланк «Mängelanzeige» — язык документа ссылкой `?lang=` (как Rechnung)."""
    from django.utils import translation

    from apps.core.documents import document_language

    from .pdf import build_maengel_pdf

    anzeige = get_object_or_404(
        Maengelanzeige.objects.select_related("bestellung__supplier"), pk=pk
    )
    with translation.override(document_language(request)):
        pdf = build_maengel_pdf(anzeige, request.tenant)
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="Maengelanzeige-{anzeige.reference}.pdf"'
    return resp


@require_POST
def _handle_post(request):
    action = request.POST.get("action", "")
    actor = getattr(request.user, "username", "") or ""

    if action == "create_supplier":
        name = (request.POST.get("name") or "").strip()[:200]
        if not name:
            messages.error(request, _("Bitte einen Namen eingeben."))
            return _redirect()
        Lieferant.objects.create(
            name=name,
            contact_person=(request.POST.get("contact_person") or "").strip()[:150],
            email=(request.POST.get("email") or "").strip()[:254],
            phone=(request.POST.get("phone") or "").strip()[:50],
            customer_number=(request.POST.get("customer_number") or "").strip()[:64],
        )
        messages.success(request, _("Lieferant angelegt."))
        return _redirect()

    if action == "create_po":
        supplier = Lieferant.objects.filter(pk=request.POST.get("supplier") or 0).first()
        po = purchasing.create_po(
            supplier=supplier, actor=actor, note=request.POST.get("note") or ""
        )
        messages.success(request, _("Bestellung angelegt: %(ref)s") % {"ref": po.reference})
        return _redirect(po)

    if action == "po_from_suggestions":
        suggestions = services.reorder_suggestions(_threshold(request.tenant))
        po = purchasing.draft_from_suggestions(suggestions, actor=actor)
        if not po.positions.exists():
            po.delete()  # пустой черновик не оставляем
            messages.info(
                request, _("Keine Vorschläge mit Sollbestand — Bestellung nicht angelegt.")
            )
            return _redirect()
        messages.success(
            request, _("Entwurf aus Bestellvorschlägen: %(ref)s") % {"ref": po.reference}
        )
        return _redirect(po)

    # --- действия над конкретным заказом ---
    po = Bestellung.objects.filter(pk=request.POST.get("po") or 0).first()
    if po is None:
        messages.error(request, _("Bestellung nicht gefunden."))
        return _redirect()

    if action == "create_maengel":
        # ERP-8: рекламация по поставке — строки из полей m_qty_/m_types_/m_desc_<строка>
        lines = []
        for line in po.positions.all():
            lines.append(
                {
                    "position": line,
                    "qty": _int(request.POST.get(f"m_qty_{line.pk}"), 0),
                    "defect_types": request.POST.getlist(f"m_types_{line.pk}"),
                    "description": request.POST.get(f"m_desc_{line.pk}") or "",
                }
            )
        anzeige = maengel.create_anzeige(
            po,
            lines=lines,
            actor=actor,
            delivery_date=_parse_date(request.POST.get("delivery_date")),
            inspected_at=_parse_date(request.POST.get("inspected_at")),
            carrier=request.POST.get("carrier") or "",
            delivery_note_ref=request.POST.get("delivery_note_ref") or "",
            result=request.POST.get("result") or "",
        )
        if anzeige is None:
            messages.error(request, _("Bitte bei mindestens einer Position eine Menge angeben."))
        else:
            messages.success(
                request, _("Mängelanzeige angelegt: %(ref)s") % {"ref": anzeige.reference}
            )
        return _redirect(po)

    if action == "resolve_mangel":
        mangel = Mangel.objects.filter(
            pk=_uuid(request.POST.get("mangel")), anzeige__bestellung=po
        ).first()
        if mangel is None:
            messages.error(request, _("Position nicht gefunden."))
            return _redirect(po)
        raw = (request.POST.get("discount") or "").strip().replace(",", ".")
        done = maengel.resolve(
            mangel,
            request.POST.get("decision", ""),
            discount=raw or None,
            actor=actor,
            tenant=request.tenant,
        )
        if done:
            messages.success(request, _("Entscheidung gebucht."))
        else:
            messages.error(request, _("Keine Buchung — bereits entschieden oder Nachlass fehlt."))
        return _redirect(po)

    if action in ("maengel_send", "maengel_notified"):
        anzeige = Maengelanzeige.objects.filter(
            pk=_uuid(request.POST.get("anzeige")), bestellung=po
        ).first()
        if anzeige is None:
            messages.error(request, _("Mängelanzeige nicht gefunden."))
            return _redirect(po)
        if action == "maengel_notified":
            maengel.mark_notified(anzeige)
            messages.success(request, _("Als angezeigt markiert."))
        elif maengel.send_to_supplier(anzeige, request.tenant):
            messages.success(request, _("Mängelanzeige an den Lieferanten gesendet."))
        else:
            messages.error(request, _("Der Lieferant hat keine E-Mail-Adresse."))
        return _redirect(po)

    if action == "add_line":
        product, variant = _resolve_entity(request.POST.get("entity"))
        if product is None:
            messages.error(request, _("Bitte einen Artikel wählen."))
            return _redirect(po)
        raw_cost = (request.POST.get("unit_cost") or "").strip().replace(",", ".")
        unit_cost = None
        if raw_cost:
            try:
                from decimal import Decimal

                unit_cost = Decimal(raw_cost)
            except Exception:
                unit_cost = None
        purchasing.add_po_line(
            po,
            product=product,
            variant=variant,
            qty=_int(request.POST.get("qty"), 1),
            unit_cost=unit_cost,
        )
        messages.success(request, _("Position hinzugefügt."))
        return _redirect(po)

    if action == "remove_line":
        BestellPosition.objects.filter(pk=request.POST.get("line") or 0, bestellung=po).delete()
        messages.success(request, _("Position entfernt."))
        return _redirect(po)

    if action == "set_status":
        status = request.POST.get("status", "")
        if status in dict(Bestellung.STATUSES):
            purchasing.set_po_status(po, status, actor=actor)
            messages.success(request, _("Status aktualisiert."))
        return _redirect(po)

    if action == "receive_line":
        line = BestellPosition.objects.filter(
            pk=request.POST.get("line") or 0, bestellung=po
        ).first()
        if line is None:
            messages.error(request, _("Position nicht gefunden."))
            return _redirect(po)
        raw_qty = (request.POST.get("qty") or "").strip()
        took = purchasing.receive_po_line(
            line,
            qty=_int(raw_qty, 0) if raw_qty else None,  # пусто = принять всё оставшееся
            tenant=request.tenant,
            mhd=_parse_date(request.POST.get("lot_mhd")),
            lot_code=(request.POST.get("lot_code") or "")[:64],
            actor=actor,
            update_cost=request.POST.get("update_cost") == "on",
            location=_resolve_location(request.POST.get("location")),  # E2
        )
        if took:
            messages.success(request, _("Wareneingang gebucht: %(n)s Stück.") % {"n": took})
        else:
            messages.info(request, _("Nichts zu buchen (Position bereits vollständig)."))
        return _redirect(po)

    if action == "return_line":
        # ERP-5: возврат поставщику из принятого по строке.
        line = BestellPosition.objects.filter(
            pk=request.POST.get("line") or 0, bestellung=po
        ).first()
        if line is None:
            messages.error(request, _("Position nicht gefunden."))
            return _redirect(po)
        took = purchasing.return_po_line(
            line,
            qty=_int(request.POST.get("qty"), 0),
            tenant=request.tenant,
            actor=actor,
            location=_resolve_location(request.POST.get("location")),
        )
        if took:
            messages.success(request, _("Rücksendung gebucht: %(n)s Stück.") % {"n": took})
        else:
            messages.info(request, _("Nichts zurückzusenden."))
        return _redirect(po)

    return _redirect(po)
