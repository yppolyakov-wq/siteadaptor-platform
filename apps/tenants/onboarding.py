"""Onboarding-Wizard (Track D / AB6): состояние пошаговой настройки бизнеса.

Мастер живёт на /dashboard/setup/ (apps.core.views.setup_view — тонкий диспетчер,
слайды — apps.core.setup_steps): одно решение на шаг, каждый можно пропустить,
прогресс резюмируется. Состояние — в Tenant.site_config["onboarding"]
(normalize пропускает ключ verbatim): state v2
{"v": 2, "step": "<key>", "done": [keys], "skipped": [keys], "completed": bool}.
Легаси-формат v1 (int-шаги 1..7 из прода) консервативно мапится в get_state;
completed никогда не понижается.

Порядок и метаданные шагов — ЕДИНЫЙ реестр SETUP_STEPS (AB6.1): он питает рельсу
прогресса мастера (✓/⏭/○ + прыжок ?step=<key> к пропущенному), а далее (AB6.2/AB7)
— чек-лист готовности и бейджи плиток дашборда.
"""

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _l


@dataclass(frozen=True)
class SetupStep:
    """Шаг мастера: метаданные для рельсы/диспетчера. check/gate/tile_url —
    расширение AB6.2 (done по реальному контенту, гейт по модулям, плитки AB7)."""

    key: str
    icon: str
    label: str  # короткая подпись рельсы (DE, язык задач)


# AB6.1: состав 1:1 прежним 7 шагам (слаги вместо номеров); целевая карта
# 8 слайдов (company/menu/offer/...) — AB6.2 (план master-slides-v3 §3).
SETUP_STEPS = (
    SetupStep("business", "🏪", "Geschäftstyp"),
    SetupStep("template", "🎨", "Stil & Farbe"),
    SetupStep("modules", "🧩", "Bausteine"),
    SetupStep("basics", "📍", "Kontakt & Zeiten"),
    SetupStep("hero", "🖼️", "Banner"),
    SetupStep("content", "🛍️", "Erster Inhalt"),
    SetupStep("done", "🎉", "Fertig"),
)
STEP_KEYS = tuple(s.key for s in SETUP_STEPS)
_FINAL = STEP_KEYS[-1]
TOTAL_STEPS = len(SETUP_STEPS)

# Легаси v1: номер шага (1..7, прод до AB6.1) → слаг того же шага.
_LEGACY_STEP_KEYS = dict(enumerate(STEP_KEYS, start=1))

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
    "online_shop": ("📦", "Online-Shop — verkaufen & versenden, ohne Ladengeschäft"),
    "tour_operator": ("🧭", "Touren & Events — Tickets und Termine"),
    "hotel": ("🛏️", "Zimmer & Ferienwohnungen — Buchung nach Datum"),
    # S6: реальные архетипы (язык задач, как остальные карточки).
    "friseur": ("💇", "Salon — Termine online, Bewertungen & Treuekarte"),
    "handwerker": ("🔧", "Handwerk — Anfragen, Angebote & Kostenvoranschläge"),
    "werkstatt": ("🚗", "KFZ-Werkstatt — Termine & Kostenvoranschläge"),
    "events": ("🎟️", "Veranstalter — Tickets, Termine & Teilnehmerlisten"),
    "other": ("✨", "Etwas anderes — frei konfigurierbar"),
}


# #3/#5 (фидбэк владельца): «Demo ansehen» на карточках типов бизнеса → открыть
# ЖИВУЮ демо-витрину этого архетипа. Демо-тенанты создаёт `seed_demo_tenants`; они
# живут на стабильных поддоменах (kit.subdomain или «<kit>-demo»). Тип бизнеса → kit-
# поддомен ближайшего демо. Идёт волновой развод общих демо на dedicated-киты
# (план docs/demo-kits-per-type-plan-2026-07-10.md): волны 1–3 — bakery/butcher/cafe/
# clothing/tour_operator ✅; пока делят: online_shop/ритейл → магазин; события → retreat.
DEMO_KIT_HOST = {
    "bakery": "baeckerei",  # dedicated «Backhaus Krume» (волна 1)
    "butcher": "metzgerei",  # dedicated «Metzgerei Bergmann» (волна 1)
    "grocery": "aktionsmarkt",
    "clothing": "mode",  # dedicated «Studio Nordwind» (волна 2)
    "online_shop": "shop",  # generic-магазин с Versand; dedicated — по спросу
    "restaurant": "restaurant-demo",
    "cafe": "cafe",  # dedicated «Café Morgenrot» (волна 2)
    "retail": "shop",
    "tour_operator": "touren",  # dedicated «Stadtgold Touren» (волна 3)
    "hotel": "hotel",
    "friseur": "friseur",
    "handwerker": "handwerker",
    "werkstatt": "werkstatt",
    "events": "retreat",
    # other → без демо (нейтральный тип)
}


def _seeded_demo_hosts() -> set[str]:
    """Поддомены демо, реально созданные на сервере (есть Domain) — чтобы не показывать
    мёртвые ссылки, если `seed_demo_tenants` ещё не прогнан. Пусто при любой ошибке."""
    from django.conf import settings

    from apps.tenants.models import Domain

    base = getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de").split(":")[0]
    wanted = {f"{sub}.{base}" for sub in set(DEMO_KIT_HOST.values())}
    try:
        return set(Domain.objects.filter(domain__in=wanted).values_list("domain", flat=True))
    except Exception:  # noqa: BLE001 — нет таблицы/схемы → без демо-кнопок
        return set()


def business_type_cards(request=None) -> list[dict]:
    """AB3: типы бизнеса как визуальные карточки ({value, label, icon, blurb, demo_url})
    в порядке модели. Для шага 1 мастера онбординга и визуализации архетипов при
    регистрации. `demo_url` — ссылка на живую демо-витрину архетипа (пусто, если демо
    для этого типа не засеяно; #3/#5)."""
    from django.conf import settings

    from apps.tenants.models import Tenant

    base = getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de")  # с портом (dev)
    base_host = base.split(":")[0]
    scheme = getattr(request, "scheme", "https") if request is not None else "https"
    seeded = _seeded_demo_hosts()

    cards = []
    for value, label in Tenant.BUSINESS_TYPES:
        icon, blurb = BUSINESS_TYPE_META.get(value, ("✨", ""))
        sub = DEMO_KIT_HOST.get(value)
        demo_url = f"{scheme}://{sub}.{base}/" if sub and f"{sub}.{base_host}" in seeded else ""
        cards.append(
            {
                "value": value,
                "label": str(label),
                "icon": icon,
                "blurb": blurb,
                "demo_url": demo_url,
            }
        )
    return cards


def _ordered(keys) -> list[str]:
    """Список ключей шагов в порядке реестра (стабильный state без дублей)."""
    wanted = set(keys)
    return [k for k in STEP_KEYS if k in wanted]


def get_state(tenant) -> dict:
    """Валидное состояние мастера из site_config (мусор → дефолты).

    Понимает оба формата: v2 (слаги) и легаси v1 (int-шаги из прода до AB6.1) —
    v1 мапится консервативно: шаги ДО текущего и не пропущенные считаются
    выполненными (для рельсы/прогресса), completed не понижается.
    """
    config = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    raw = config.get("onboarding")
    raw = raw if isinstance(raw, dict) else {}
    non_final = STEP_KEYS[:-1]
    if raw.get("v") == 2:
        step = raw.get("step") if raw.get("step") in STEP_KEYS else STEP_KEYS[0]
        raw_skipped = raw.get("skipped") if isinstance(raw.get("skipped"), list) else []
        raw_done = raw.get("done") if isinstance(raw.get("done"), list) else []
        skipped = [k for k in non_final if k in set(raw_skipped)]
        done = [k for k in non_final if k in set(raw_done) and k not in skipped]
        completed = bool(raw.get("completed"))
    else:
        num = raw.get("step")
        num = num if isinstance(num, int) and 1 <= num <= TOTAL_STEPS else 1
        step = _LEGACY_STEP_KEYS[num]
        skipped_nums = {
            s for s in raw.get("skipped", []) if isinstance(s, int) and 1 <= s < TOTAL_STEPS
        }
        skipped = [_LEGACY_STEP_KEYS[n] for n in sorted(skipped_nums)]
        completed = bool(raw.get("completed"))
        passed = non_final if completed else STEP_KEYS[: num - 1]
        done = [k for k in passed if k not in skipped]
    return {"v": 2, "step": step, "done": done, "skipped": skipped, "completed": completed}


def save_state(tenant, state: dict) -> None:
    config = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    config["onboarding"] = state
    tenant.site_config = config
    tenant.save(update_fields=["site_config", "updated_at"])


def advance(tenant, *, skip: bool = False) -> dict:
    """Перейти к следующему шагу; текущий помечается выполненным (или пропущенным
    при skip=True). Достижение финального шага = мастер завершён."""
    state = get_state(tenant)
    cur = state["step"]
    idx = STEP_KEYS.index(cur)
    if cur != _FINAL:
        if skip:
            state["skipped"] = _ordered({*state["skipped"], cur})
            state["done"] = [k for k in state["done"] if k != cur]
        else:
            state["done"] = _ordered({*state["done"], cur})
            state["skipped"] = [k for k in state["skipped"] if k != cur]
        state["step"] = STEP_KEYS[idx + 1]
    if state["step"] == _FINAL:
        state["completed"] = True
    save_state(tenant, state)
    return state


def back(tenant) -> dict:
    """Вернуться на шаг назад (сравнить варианты, поменять тип бизнеса).

    Возврат не «раз-завершает» мастер: completed остаётся, плашка прогресса
    на дашборде не воскресает из-за просмотра прежних шагов.
    """
    state = get_state(tenant)
    idx = STEP_KEYS.index(state["step"])
    if idx > 0:
        prev = STEP_KEYS[idx - 1]
        state["step"] = prev
        state["skipped"] = [k for k in state["skipped"] if k != prev]
        save_state(tenant, state)
    return state


def goto(tenant, key: str) -> dict:
    """AB6.1: прыжок к произвольному шагу (?step=<key> из рельсы прогресса) —
    дозаполнить пропущенное можно в любой момент. Невалидный ключ игнорируется;
    done/skipped/completed не трогаются (это позиция, не прогресс)."""
    state = get_state(tenant)
    if key in STEP_KEYS and key != state["step"]:
        state["step"] = key
        save_state(tenant, state)
    return state


def progress(tenant) -> tuple[int, int]:
    """(пройдено, всего) для плашки «Setup-Fortschritt N/7» на дашборде.
    Пройдено = выполненные + пропущенные (позиция step на счёт не влияет —
    прыжки по рельсе прогресс не искажают)."""
    state = get_state(tenant)
    if state["completed"]:
        return TOTAL_STEPS, TOTAL_STEPS
    return len({*state["done"], *state["skipped"]}), TOTAL_STEPS


def steps_with_status(tenant) -> list[dict]:
    """AB6.1: шаги для рельсы прогресса — {key, icon, label, num, status} со
    статусом done|skipped|pending (подсветка активного — по state["step"] в
    шаблоне). Завершённый мастер: всё непропущенное — done, вкл. финал."""
    state = get_state(tenant)
    rows = []
    for i, spec in enumerate(SETUP_STEPS):
        if spec.key in state["skipped"]:
            status = "skipped"
        elif spec.key in state["done"] or (state["completed"] and spec.key not in state["skipped"]):
            status = "done"
        else:
            status = "pending"
        rows.append(
            {
                "key": spec.key,
                "icon": spec.icon,
                "label": spec.label,
                "num": i + 1,
                "status": status,
            }
        )
    return rows


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


def offer_cta(tenant):
    """W3: архетип-осознанный CTA «добавь первое X» — (label, url_name) по primary-архетипу
    тенанта. Friseur/Werkstatt → услуга, events → событие, каталог → товар (фолбэк)."""
    from django.utils.translation import gettext as _t

    from apps.core import archetypes

    return _OFFER_CTA.get(
        archetypes.primary_module(tenant),
        (_t("Add your first item to sell"), "catalog:product-list"),
    )


def completeness(tenant) -> dict:
    """AB4: «Dein Site ist zu X% fertig» — пункты готовности из реального наполнения.

    → {percent, done, total, items:[{key,label,done,url_name}]}. Считается по факту
    (фото/часы/контакты/первый товар/Impressum), а не по шагам мастера — мотивирует
    допилить сайт и даёт прямой путь к действию (анти-«пустой кабинет»)."""
    from django.utils.translation import gettext as _t

    from . import siteconfig

    cfg = siteconfig.normalize(tenant.site_config)
    has_photo = bool(cfg.get("hero_image")) or bool(cfg.get("gallery"))
    # Пункт «первый товар» — по главному архетипу тенанта (язык задач + верная ссылка).
    _offer_label, _offer_url = offer_cta(tenant)
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
