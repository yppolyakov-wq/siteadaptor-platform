"""Onboarding-Wizard (Track D / D0c): состояние пошаговой настройки бизнеса.

Мастер живёт на /dashboard/setup/ (apps.core.views.setup_view): ≤5 шагов, одно
решение на шаг, каждый можно пропустить, прогресс резюмируется. Состояние —
в Tenant.site_config["onboarding"] (siteconfig.normalize и site_view его
сохраняют): {"step": 1..5, "skipped": [...], "completed": bool}.

Шаги (B.4 «анти-Битрикс», линейный ≤10): 1) Was machst du? (business_type →
предвыбор блоков) → 2) Stil & Farbe (выбор шаблона+акцент) → 3) Was willst du
anbieten? (тумблеры модулей) → 4) Basics (адрес/часы/контакты) → 5) Dein Banner
(hero-текст + загрузка фото) → 6) Inhalt & Vorschau (демо-контент + пресеты +
ссылка на превью) → 7) Geschafft. Достижение шага 7 = мастер завершён.
"""

from django.utils.translation import gettext_lazy as _l

TOTAL_STEPS = 7

# AB3 (анти-Битрикс): визуальные карточки типов бизнеса для шага 1 мастера и
# визуализации при регистрации — эмодзи + короткое «что это даёт» на ЯЗЫКЕ ЗАДАЧ
# (не сущностей). Ключи — Tenant.BUSINESS_TYPES; неизвестный → нейтральная иконка.
BUSINESS_TYPE_META = {
    "bakery": ("🥐", "Brot, Brötchen & Kuchen — Vorbestellung & Abholung"),
    "butcher": ("🥩", "Fleisch & Wurst — Vorbestellung, Partyservice"),
    "grocery": ("🛒", "Lebensmittel — Sortiment, Aktionen & Treue"),
    "clothing": ("👗", "Mode — Online-Shop mit Größen & Versand"),
    "restaurant": ("🍽️", "Speisekarte, Tischreservierung & Lieferung"),
    "cafe": ("☕", "Karte, Reservierung & Treuekarte"),
    "retail": ("🛍️", "Einzelhandel — Online-Shop, Versand & Abholung"),
    "tour_operator": ("🧭", "Touren & Events — Tickets und Termine"),
    "hotel": ("🛏️", "Zimmer & Ferienwohnungen — Buchung nach Datum"),
    # S6: реальные архетипы (язык задач, как остальные карточки).
    "friseur": ("💇", "Salon — Termine online, Bewertungen & Treuekarte"),
    "handwerker": ("🔧", "Handwerk — Anfragen, Angebote & Kostenvoranschläge"),
    "werkstatt": ("🚗", "KFZ-Werkstatt — Termine & Kostenvoranschläge"),
    "events": ("🎟️", "Veranstalter — Tickets, Termine & Teilnehmerlisten"),
    "other": ("✨", "Etwas anderes — frei konfigurierbar"),
}


def business_type_cards() -> list[dict]:
    """AB3: типы бизнеса как визуальные карточки ({value, label, icon, blurb}) в порядке
    модели. Для шага 1 мастера онбординга и визуализации архетипов при регистрации."""
    from apps.tenants.models import Tenant

    cards = []
    for value, label in Tenant.BUSINESS_TYPES:
        icon, blurb = BUSINESS_TYPE_META.get(value, ("✨", ""))
        cards.append({"value": value, "label": str(label), "icon": icon, "blurb": blurb})
    return cards


def get_state(tenant) -> dict:
    """Валидное состояние мастера из site_config (мусор → дефолты)."""
    config = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    raw = config.get("onboarding")
    raw = raw if isinstance(raw, dict) else {}
    step = raw.get("step")
    if not isinstance(step, int) or not 1 <= step <= TOTAL_STEPS:
        step = 1
    skipped = sorted(
        {s for s in raw.get("skipped", []) if isinstance(s, int) and 1 <= s < TOTAL_STEPS}
    )
    return {"step": step, "skipped": skipped, "completed": bool(raw.get("completed"))}


def save_state(tenant, state: dict) -> None:
    config = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    config["onboarding"] = state
    tenant.site_config = config
    tenant.save(update_fields=["site_config", "updated_at"])


def advance(tenant, *, skip: bool = False) -> dict:
    """Перейти к следующему шагу (опц. пометив текущий пропущенным).

    Шаг 5 — финальный экран: добравшись до него, мастер завершён.
    """
    state = get_state(tenant)
    if skip and state["step"] < TOTAL_STEPS and state["step"] not in state["skipped"]:
        state["skipped"] = sorted({*state["skipped"], state["step"]})
    if state["step"] < TOTAL_STEPS:
        state["step"] += 1
    if state["step"] >= TOTAL_STEPS:
        state["completed"] = True
    save_state(tenant, state)
    return state


def back(tenant) -> dict:
    """Вернуться на шаг назад (сравнить варианты, поменять тип бизнеса).

    Возврат не «раз-завершает» мастер: completed остаётся, плашка прогресса
    на дашборде не воскресает из-за просмотра прежних шагов.
    """
    state = get_state(tenant)
    if state["step"] > 1:
        state["step"] -= 1
        state["skipped"] = [s for s in state["skipped"] if s != state["step"]]
        save_state(tenant, state)
    return state


def progress(tenant) -> tuple[int, int]:
    """(пройдено, всего) для плашки «Setup-Fortschritt N/7» на дашборде."""
    state = get_state(tenant)
    done = TOTAL_STEPS if state["completed"] else state["step"] - 1
    return done, TOTAL_STEPS


# --- AB4: чек-лист готовности сайта (из реального наполнения, не из шагов мастера) ---
def _has_offering(tenant) -> bool:
    """Есть ли что продавать: товар / акция / услуга / событие / номер. Безопасно к
    выключенным модулям и отсутствию таблиц (любая ошибка → этот источник False)."""
    checks = (
        ("apps.catalog.models", "Product", {"is_active": True}),
        ("apps.promotions.models", "Promotion", {"status": "active"}),
        ("apps.booking.models", "Service", {"is_active": True}),
        ("apps.events.models", "Event", {}),
        ("apps.stays.models", "StayUnit", {"is_active": True}),
    )
    import importlib

    for mod_path, cls_name, flt in checks:
        try:
            model = getattr(importlib.import_module(mod_path), cls_name)
            if model.objects.filter(**flt).exists():
                return True
        except Exception:  # noqa: BLE001 — модуль выключен / нет таблицы
            continue
    return False


# AB4: пункт «первый товар» — на ЯЗЫКЕ архетипа + ссылка на нужный список кабинета
# (отель → номер, события → событие, услуги → услуга), а не всегда «товар/каталог».
# url_name'ы смонтированы в urls_tenant безусловно → reverse не падает даже при
# выключенном модуле. Неизвестный/без архетипа → нейтральный фолбэк (каталог).
_OFFER_CTA = {
    "catalog": (_l("Add your first product"), "catalog:product-list"),
    "stays": (_l("Add your first room"), "stays:units"),
    "events": (_l("Add your first event"), "events:list"),
    "booking": (_l("Add your first service"), "booking:services"),
    "promotions": (_l("Create your first offer"), "promotions:promotion-list"),
}


def completeness(tenant) -> dict:
    """AB4: «Dein Site ist zu X% fertig» — пункты готовности из реального наполнения.

    → {percent, done, total, items:[{key,label,done,url_name}]}. Считается по факту
    (фото/часы/контакты/первый товар/Impressum), а не по шагам мастера — мотивирует
    допилить сайт и даёт прямой путь к действию (анти-«пустой кабинет»)."""
    from django.utils.translation import gettext as _t

    from apps.core import archetypes

    from . import siteconfig

    cfg = siteconfig.normalize(tenant.site_config)
    has_photo = bool(cfg.get("hero_image")) or bool(cfg.get("gallery"))
    # Пункт «первый товар» — по главному архетипу тенанта (язык задач + верная ссылка).
    _offer_label, _offer_url = _OFFER_CTA.get(
        archetypes.primary_module(tenant),
        (_t("Add your first item to sell"), "catalog:product-list"),
    )
    items = [
        {
            "key": "banner",
            "label": _t("Add a banner or photo"),
            "done": has_photo,
            "url_name": "site",
        },
        {
            "key": "hours",
            "label": _t("Set your opening hours"),
            "done": bool(tenant.opening_hours or tenant.opening_hours_structured),
            "url_name": "settings",
        },
        {
            "key": "contact",
            "label": _t("Add contact details"),
            "done": bool(tenant.public_email or tenant.public_phone or tenant.address),
            "url_name": "settings",
        },
        {
            "key": "offer",
            "label": _offer_label,
            "done": _has_offering(tenant),
            "url_name": _offer_url,
        },
        {
            "key": "legal",
            "label": _t("Complete legal info (Impressum)"),
            "done": bool(tenant.address),
            "url_name": "settings",
        },
    ]
    done = sum(1 for i in items if i["done"])
    total = len(items)
    return {
        "percent": round(100 * done / total) if total else 100,
        "done": done,
        "total": total,
        "items": items,
    }
