"""SHP-1: справочник транспортных компаний (DE) — в коде, не в БД.

План `docs/ful-fulfilment-modes-plan-2026-11-09.md` §4. Владелец выбирает компанию у способа
доставки «Paketdienst»; имя, ссылка отслеживания и наличие пунктов выдачи живут здесь.
`pickup_point` — какие пункты выдачи у компании есть (пусто = только до двери). Packstation —
только у DHL (рыночная разведка 2026-11-09): у Hermes/DPD/GLS/UPS — PaketShop/Access Point.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Carrier:
    code: str
    name: object  # str или ленивый перевод
    #: шаблон ссылки отслеживания; {code} — трек-номер (экранируется)
    tracking: str
    #: виды пунктов выдачи; пусто — компания возит только до двери
    pickup_point: tuple[str, ...] = ()
    #: страница поиска пунктов выдачи у компании (ссылка покупателю)
    finder: str = ""


PACKSTATION, FILIALE, PAKETSHOP = "packstation", "postfiliale", "paketshop"

REGISTRY: tuple[Carrier, ...] = (
    Carrier(
        "dhl",
        "DHL",
        "https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?piececode={code}",
        (PACKSTATION, FILIALE),
        "https://www.dhl.de/de/privatkunden/dhl-standorte-finden.html",
    ),
    Carrier(
        "deutsche_post",
        "Deutsche Post",
        "https://www.deutschepost.de/de/s/sendungsverfolgung.html?piececode={code}",
    ),
    Carrier(
        "hermes",
        "Hermes",
        "https://www.myhermes.de/empfangen/sendungsverfolgung/sendungsinformation/#{code}",
        (PAKETSHOP,),
        "https://www.myhermes.de/paketshopfinder/",
    ),
    Carrier(
        "dpd",
        "DPD",
        "https://tracking.dpd.de/status/de_DE/parcel/{code}",
        (PAKETSHOP,),
        "https://www.dpd.com/de/de/paket-empfangen/dpd-pickup-paketshops/",
    ),
    Carrier(
        "gls",
        "GLS",
        "https://gls-group.com/DE/de/paketverfolgung?match={code}",
        (PAKETSHOP,),
        "https://gls-group.com/DE/de/paketshop-finden",
    ),
    Carrier(
        "ups",
        "UPS",
        "https://www.ups.com/track?loc=de_DE&tracknum={code}",
        (PAKETSHOP,),
        "https://www.ups.com/dropoff?loc=de_DE",
    ),
    Carrier("other", _("Andere Versanddienste"), ""),
)

_BY_CODE = {c.code: c for c in REGISTRY}


def get(code: str) -> Carrier | None:
    return _BY_CODE.get(code or "")


def choices() -> list[tuple[str, str]]:
    return [(c.code, c.name) for c in REGISTRY]


def tracking_url(code: str, tracking_code: str) -> str:
    """Ссылка отслеживания или "" (нет компании/шаблона/номера)."""
    carrier = get(code)
    number = (tracking_code or "").strip()
    if not carrier or not carrier.tracking or not number:
        return ""
    return carrier.tracking.replace("{code}", quote(number, safe=""))
