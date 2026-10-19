"""T-8.8: llms.txt портала и основного домена — карта каталога для AI-ассистентов.

План — docs/t8-8-machine-readable-plan-2026-10-15.md §2 (Р-3). Только НЕПУСТЫЕ
разделы и районы (пустой раздел — мёртвая ссылка), блок «Daten für Assistenten» с
фидом/sitemap и правилами (без онлайн-оплаты, реклама помечена, цены без гарантии),
ссылки на Impressum/Datenschutz платформы. Персональных данных нет. Тексты — gettext
(язык по запросу), `/llms-full.txt` не делаем — полный список отдаёт фид.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core import city_categories as cc
from apps.core import districts

from .models import AggregatorPortal
from .platform_links import legal_links


def _sections_present(pool) -> list:
    """Разделы справочника, в которых есть хотя бы одно предложение (1 запрос)."""
    present = set(
        pool.exclude(city_category="").order_by().values_list("city_category", flat=True).distinct()
    )
    out = []
    for section in cc.SECTIONS:
        if any(c.key in present for c in cc.CATEGORIES if c.section == section.key):
            out.append(section)
    return out


def _districts_present(pool, city: str) -> list[tuple[str, str]]:
    known = districts.choices_for(city)
    if not known:
        return []
    used = set(pool.exclude(district="").order_by().values_list("district", flat=True).distinct())
    return [(slug, name) for slug, name in known if slug in used]


def _rules() -> list[str]:
    return [
        "- "
        + _(
            "Keine Online-Zahlung über das Portal: Reservieren, Coupon oder Anfrage direkt beim Anbieter (Link in jedem Eintrag)."
        ),
        "- "
        + _(
            "Werbliche Einträge sind im Feed als `sponsored` markiert und werden in der Reihenfolge nicht bevorzugt."
        ),
        "- " + _("Preise und Verfügbarkeit ohne Gewähr — maßgeblich ist die Seite des Anbieters."),
    ]


def _data_block(
    request, *, feed_json: str, feed_atom: str, sitemap: str, extra: str = ""
) -> list[str]:
    abs_ = request.build_absolute_uri
    lines = [
        "## " + _("Daten für Assistenten"),
        f"- JSON Feed 1.1: {abs_(feed_json)}",
        f"- Atom: {abs_(feed_atom)}",
        "  "
        + _(
            "Filter: `?kind=` (promotion|product|service|event|stay|menu|business), `?kat=` (Rubrik), `?merkmal=` (Merkmal), `?stadtteil=`, `?limit=` (max. 100), `cursor` aus `next_url`."
        )
        + (f" {extra}" if extra else ""),
        f"- Sitemap: {abs_(sitemap)}",
        "- "
        + _(
            "Angebotsseite: `/angebot/<id>/` mit JSON-LD (Product/Service/Event/HotelRoom/LocalBusiness)."
        ),
        *_rules(),
        "",
    ]
    return lines


def _legal_block() -> list[str]:
    legal = legal_links()
    return [
        "## " + _("Rechtliches"),
        f"- Impressum: {legal['impressum']}",
        f"- Datenschutz: {legal['datenschutz']}",
        "",
    ]


def build_portal(request, portal) -> str:
    from .views import listings_for

    pool = listings_for(
        city=portal.city or None,
        business_type=portal.business_type or None,
        include_demo=False,  # T-8.26 (Р-3): выдуманные предложения ассистентам не отдаём
    )
    abs_ = request.build_absolute_uri
    lines = [f"# {portal.title_text}", ""]
    intro = portal.tagline_text or portal.intro_text
    if intro:
        lines += ["> " + " ".join(intro.split()), ""]
    if portal.show_demo and not pool.exists():
        # превью без единого настоящего предложения — честно сказать ассистенту почему пусто
        lines += [_("Vorschau — noch keine echten Angebote."), ""]
    if portal.city:
        lines += [_("Stadt: %(city)s") % {"city": portal.city}, ""]
    sections = _sections_present(pool)
    if sections:
        lines += ["## " + _("Rubriken")]
        lines += [f"- [{s.label}]({abs_(reverse('portal-home'))}?kat={s.key})" for s in sections]
        lines.append("")
    if portal.city:
        present = _districts_present(pool, portal.city)
        if present:
            lines += ["## " + _("Stadtteile")]
            lines += [
                f"- [{name}]({abs_(reverse('portal-district', args=[slug]))})"
                for slug, name in present
            ]
            lines.append("")
    lines += _data_block(
        request,
        feed_json=reverse("portal-feed-json"),
        feed_atom=reverse("portal-feed-atom"),
        sitemap=reverse("portal-sitemap"),
    )
    from .mcp.views import mcp_available

    if mcp_available(portal):  # T-8.10f F-5: подключаемый MCP-сервер каталога
        lines += [
            "## MCP",
            f"- {abs_(reverse('portal-mcp'))}",
            "  "
            + _(
                "MCP-Server (Streamable HTTP, ohne Anmeldung): search_offers, get_offer, get_business, list_categories, list_districts."
            ),
            "",
        ]
    lines += _legal_block()
    return "\n".join(lines) + "\n"


def build_platform(request) -> str:
    """Основной домен: описание платформы, /entdecken/, фид, активные порталы (≤12)."""
    abs_ = request.build_absolute_uri
    entdecken = _("Entdecken")
    lines = [
        "# siteadaptor",
        "",
        "> "
        + _(
            "Lokale Angebote, Produkte und Dienstleistungen kleiner Betriebe — pro Stadt ein Portal, ein gemeinsamer Datenbestand."
        ),
        "",
        "## " + _("Einstieg"),
        f"- [{entdecken}]({abs_(reverse('aggregator-index'))})",
        "",
    ]
    portals = list(AggregatorPortal.objects.filter(is_active=True).order_by("host")[:12])
    if portals:
        lines += ["## " + _("Portale")]
        lines += [f"- [{p.title_text}]({request.scheme}://{p.host}/)" for p in portals]
        lines.append("")
    lines += _data_block(
        request,
        feed_json=reverse("aggregator-feed-json"),
        feed_atom=reverse("aggregator-feed-atom"),
        sitemap=reverse("aggregator-sitemap"),
        extra=_("Auf der Hauptdomain zusätzlich `?city=` (Stadt)."),
    )
    lines += _legal_block()
    return "\n".join(lines) + "\n"
