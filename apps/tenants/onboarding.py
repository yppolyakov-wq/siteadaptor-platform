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

from collections.abc import Callable
from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _l


@dataclass(frozen=True)
class SetupStep:
    """Шаг мастера: метаданные для рельсы/диспетчера.

    check(tenant) → bool: шаг выполнен по РЕАЛЬНОМУ контенту (авто-✓ в рельсе,
    даже без явного «Weiter»); None = только ручное done. gate(tenant) → bool:
    показывать ли шаг (модули/архетип); скрытый шаг вне рельсы и вне счётчика, но
    достижим прыжком ?step= (escape-hatch). tile_url — плитки AB7 (позже)."""

    key: str
    icon: str
    label: str  # короткая подпись рельсы (DE, язык задач)
    check: Callable | None = None
    gate: Callable | None = None
    tile_url: str = ""


# --- check/gate (AB6.2): «done по реальному контенту» + видимость шага ------------
def _check_start(t) -> bool:
    # AB6.9: слайд «Start» выполнен, когда добавлены демо-примеры (или шаг пройден
    # явно — это учитывает state["done"] в _is_done).
    from . import demo

    return demo.has_demo(t)


def _check_company(t) -> bool:
    return bool(t.public_email or t.public_phone or t.address)


def _check_offer(t) -> bool:
    return _has_offering(t)  # определён ниже; резолвится в рантайме


def _check_home(t) -> bool:
    cfg = t.site_config if isinstance(t.site_config, dict) else {}
    return bool(cfg.get("hero_title") or cfg.get("hero_image"))


def _has_legal_doc(t) -> bool:
    try:
        from apps.core.models import LegalDoc

        return LegalDoc.objects.exists()
    except Exception:  # noqa: BLE001 — модель/таблица недоступна
        return False


def _check_texts(t) -> bool:
    cfg = t.site_config if isinstance(t.site_config, dict) else {}
    return bool(cfg.get("about_title") or cfg.get("about_text")) or _has_legal_doc(t)


_CHECKOUT_MODULES = ("orders", "booking", "stays", "events", "jobs")


def _gate_business(t) -> bool:
    # Тип бизнеса задаётся при регистрации → слайд скрыт (не сбивать с толку);
    # достижим по «Andere Branche / erweitern» (?step=business) для смежных архетипов.
    return not bool(t.business_type)


def _gate_category(t) -> bool:
    return t.is_module_active("catalog")


def _gate_payment(t) -> bool:
    return any(t.is_module_active(m) for m in _CHECKOUT_MODULES)


# AB6.2: целевая карта слайдов (план master-slides-v3 §0d). business — escape-hatch
# (gate скрывает, тип уже выбран при регистрации); category — только при catalog;
# payment — только при чекаут-модуле. Порядок = порядок рельсы.
SETUP_STEPS = (
    SetupStep("business", "🏪", "Branche", gate=_gate_business),
    SetupStep("start", "🚀", "Start", check=_check_start),
    SetupStep("company", "🏠", "Firma & Logo", check=_check_company),
    SetupStep("stil", "🎨", "Stil", tile_url="site-home"),
    SetupStep("menu", "🧭", "Menü", tile_url="site-menu"),
    SetupStep("offer", "🛍️", "Angebot", check=_check_offer),
    SetupStep(
        "category", "📁", "Kategorien", gate=_gate_category, tile_url="catalog:category-list"
    ),
    SetupStep("home", "🖼️", "Startseite", check=_check_home, tile_url="site-home"),
    SetupStep("payment", "💳", "Zahlung", gate=_gate_payment, tile_url="payment-settings"),
    SetupStep("texts", "📄", "Texte & Recht", check=_check_texts, tile_url="legal-docs"),
    SetupStep("done", "🎉", "Fertig"),
)
STEP_KEYS = tuple(s.key for s in SETUP_STEPS)
_STEP_BY_KEY = {s.key: s for s in SETUP_STEPS}
_FINAL = STEP_KEYS[-1]
TOTAL_STEPS = len(SETUP_STEPS)

# Легаси-ремап на новую карту. v1-int (прод до AB6.1) → старый слаг → новый ключ;
# v2-AB6.1-слаги (business/template/modules/basics/hero/content/done) → новые ключи.
# Дропнутые слайды (modules) приземляются на company; новые ключи маппятся сами
# (_REMAP.get(k, k)). completed никогда не понижается.
_LEGACY_INT_TO_OLD = {
    1: "business",
    2: "template",
    3: "modules",
    4: "basics",
    5: "hero",
    6: "content",
    7: "done",
}
_REMAP = {
    "template": "stil",
    "modules": "company",
    "basics": "company",
    "hero": "home",
    "content": "offer",
}

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


def _remap_key(key: str) -> str | None:
    """Легаси-слаг/новый ключ → актуальный ключ реестра (или None, если неведом)."""
    new = _REMAP.get(key, key)
    return new if new in _STEP_BY_KEY else None


def get_state(tenant) -> dict:
    """Валидное состояние мастера из site_config (мусор → дефолты).

    Ремапит на текущую карту (AB6.2): v2-слаги старой карты AB6.1 и v1-int из прода
    приводятся к новым ключам через `_REMAP`; шаги без соответствия отбрасываются,
    дропнутые (modules) приземляются на company. completed не понижается.
    """
    config = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    raw = config.get("onboarding")
    raw = raw if isinstance(raw, dict) else {}
    non_final = set(STEP_KEYS[:-1])
    completed = bool(raw.get("completed"))
    if raw.get("v") == 2:
        step = _remap_key(raw.get("step")) or STEP_KEYS[0]
        raw_skipped = raw.get("skipped") if isinstance(raw.get("skipped"), list) else []
        raw_done = raw.get("done") if isinstance(raw.get("done"), list) else []
        skipped_keys = {_remap_key(k) for k in raw_skipped} & non_final
        done_keys = ({_remap_key(k) for k in raw_done} & non_final) - skipped_keys
    else:
        num = raw.get("step")
        num = num if isinstance(num, int) and 1 <= num <= len(_LEGACY_INT_TO_OLD) else 1
        step = _remap_key(_LEGACY_INT_TO_OLD[num]) or STEP_KEYS[0]
        skipped_nums = {
            s for s in raw.get("skipped", []) if isinstance(s, int) and s in _LEGACY_INT_TO_OLD
        }
        skipped_keys = {_remap_key(_LEGACY_INT_TO_OLD[n]) for n in skipped_nums} & non_final
        # v1 не хранил done-список: шаги ДО текущего int и не пропущенные — выполнены.
        passed_olds = [_LEGACY_INT_TO_OLD[n] for n in range(1, num)]
        done_keys = ({_remap_key(o) for o in passed_olds} & non_final) - skipped_keys
    return {
        "v": 2,
        "step": step,
        "done": _ordered(done_keys),
        "skipped": _ordered(skipped_keys),
        "completed": completed,
    }


def save_state(tenant, state: dict) -> None:
    config = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    config["onboarding"] = state
    tenant.site_config = config
    tenant.save(update_fields=["site_config", "updated_at"])


def visible_keys(tenant) -> list[str]:
    """AB6.2: ключи шагов, видимых ДЛЯ ЭТОГО тенанта (gate пройден) — рельса,
    навигация и счётчик работают по ним. Скрытые (business/category/payment без
    условий) остаются достижимы прыжком ?step= (escape-hatch)."""
    return [k for k in STEP_KEYS if (_STEP_BY_KEY[k].gate is None or _STEP_BY_KEY[k].gate(tenant))]


def _is_done(spec, tenant, state) -> bool:
    """Шаг «выполнен»: явный done, ИЛИ авто-✓ по контенту (check), ИЛИ мастер
    завершён и шаг не пропущен."""
    if spec.key in state["skipped"]:
        return False
    if spec.key in state["done"]:
        return True
    if spec.check is not None and spec.check(tenant):
        return True
    return state["completed"] and spec.key != _FINAL


def advance(tenant, *, skip: bool = False) -> dict:
    """Перейти к следующему ВИДИМОМУ шагу; текущий помечается выполненным (или
    пропущенным при skip=True). Достижение финального шага = мастер завершён."""
    state = get_state(tenant)
    cur = state["step"]
    vis = visible_keys(tenant)
    if cur != _FINAL:
        if skip:
            state["skipped"] = _ordered({*state["skipped"], cur})
            state["done"] = [k for k in state["done"] if k != cur]
        else:
            state["done"] = _ordered({*state["done"], cur})
            state["skipped"] = [k for k in state["skipped"] if k != cur]
        # Следующий видимый шаг после текущего (текущий мог быть escape-hatch вне vis).
        after = [k for k in vis if STEP_KEYS.index(k) > STEP_KEYS.index(cur)]
        state["step"] = after[0] if after else _FINAL
    if state["step"] == _FINAL:
        state["completed"] = True
    save_state(tenant, state)
    return state


def back(tenant) -> dict:
    """Вернуться на предыдущий ВИДИМЫЙ шаг. Возврат не «раз-завершает» мастер:
    completed остаётся, плашка прогресса на дашборде не воскресает."""
    state = get_state(tenant)
    vis = visible_keys(tenant)
    before = [k for k in vis if STEP_KEYS.index(k) < STEP_KEYS.index(state["step"])]
    if before:
        prev = before[-1]
        state["step"] = prev
        state["skipped"] = [k for k in state["skipped"] if k != prev]
        save_state(tenant, state)
    return state


def leave(tenant) -> dict:
    """AB6.9 «Später fertigstellen»: выйти из мастера в кабинет, пометив его тронутым
    (текущий шаг ⏭) — чтобы AB5-редирект не вернул сразу назад. Позицию не двигаем и
    мастер не завершаем: владелец может вернуться и дозаполнить."""
    state = get_state(tenant)
    if not state["completed"] and state["step"] != _FINAL and state["step"] not in state["skipped"]:
        state["skipped"] = _ordered({*state["skipped"], state["step"]})
        save_state(tenant, state)
    return state


def goto(tenant, key: str) -> dict:
    """Прыжок к произвольному шагу (?step=<key> из рельсы) — дозаполнить пропущенное
    или escape-hatch к скрытому шагу (business «erweitern»). Любой валидный ключ
    реестра (даже гейченный); done/skipped/completed не трогаются (это позиция)."""
    state = get_state(tenant)
    if key in _STEP_BY_KEY and key != state["step"]:
        state["step"] = key
        save_state(tenant, state)
    return state


def progress(tenant) -> tuple[int, int]:
    """(пройдено, всего) для плашки «Setup-Fortschritt N/M» на дашборде. Всего =
    видимые шаги; пройдено = выполненные+пропущенные среди видимых (позиция step на
    счёт не влияет — прыжки прогресс не искажают)."""
    state = get_state(tenant)
    vis = visible_keys(tenant)
    total = len(vis)
    if state["completed"]:
        return total, total
    done = sum(1 for k in vis if _is_done(_STEP_BY_KEY[k], tenant, state) or k in state["skipped"])
    return done, total


def steps_with_status(tenant) -> list[dict]:
    """Шаги рельсы прогресса (только видимые) — {key, icon, label, num, status:
    done|skipped|pending}; подсветка активного — по state["step"] в шаблоне.
    done учитывает авто-✓ по реальному контенту (SetupStep.check)."""
    state = get_state(tenant)
    rows = []
    for i, key in enumerate(visible_keys(tenant)):
        spec = _STEP_BY_KEY[key]
        if key in state["skipped"]:
            status = "skipped"
        elif _is_done(spec, tenant, state):
            status = "done"
        else:
            status = "pending"
        rows.append(
            {"key": key, "icon": spec.icon, "label": spec.label, "num": i + 1, "status": status}
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
