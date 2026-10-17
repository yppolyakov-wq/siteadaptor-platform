"""T-8.1: профиль витрины «Nur Aktionen» (план docs/t8-1-aktion-demos-plan-2026-10-09.md).

Витрина = визитка + акции. Каталог — core-модуль и выключен быть не может, поэтому
профиль не выключает модуль, а убирает ВХОДЫ в каталог и корзину: пункты меню,
авто-нижний бар, поиск шапки, hero-плитки, секции главной — и уводит прямые адреса
этих страниц на главную. Подтверждение заказа, акции и Merkzettel не трогаются.

Хранение — `site_config["profile"]` (presence-minimal, `siteconfig.STOREFRONT_PROFILES`).
"""

from __future__ import annotations

from functools import wraps

from django.shortcuts import redirect

AKTIONEN = "aktionen"
#: T-8.27d (Р-A): «Nur Eintrag» — визитка бизнеса без своей витрины у нас. Каталог
#: скрыт так же, как у «Nur Aktionen», но позиции живут в каталоге города со ссылкой
#: на сайт владельца (`Product.external_url`).
EINTRAG = "eintrag"
#: Лёгкие профили: каталог/корзина на витрине скрыты, ступень бесплатного старта.
LITE_PROFILES = frozenset({AKTIONEN, EINTRAG})

#: Секции главной, которые при профиле не рендерятся (каталог/наборы).
HIDDEN_HOME_SECTIONS = frozenset({"products", "categories", "combos"})

#: url_name витрины, ведущие в каталог/корзину. Узлы меню и hero-плитки с такими
#: целями при профиле отбрасываются.
CATALOG_URL_NAMES = frozenset(
    {
        "storefront-products",
        "storefront-category",
        "storefront-cart",
        "storefront-combos",
    }
)


def _config(obj) -> dict:
    if isinstance(obj, dict):
        return obj
    cfg = getattr(obj, "site_config", None)
    return cfg if isinstance(cfg, dict) else {}


def _profile(obj) -> str:
    tenant = getattr(obj, "tenant", None) if hasattr(obj, "META") else obj
    if tenant is None:
        return ""
    return _config(tenant).get("profile") or ""


def is_aktionen(obj) -> bool:
    """Лёгкий профиль витрины («Nur Aktionen» или «Nur Eintrag»): каталог и корзина
    скрыты. Принимает тенанта, запрос или dict конфига."""
    return _profile(obj) in LITE_PROFILES


def is_eintrag(obj) -> bool:
    """T-8.27d: визитка «Nur Eintrag» — позиции ведут на сайт владельца."""
    return _profile(obj) == EINTRAG


def redirect_if_aktionen(view):
    """Декоратор публичных вьюх каталога/корзины: при профиле → 302 на главную."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if is_aktionen(request):
            return redirect("storefront-home")
        return view(request, *args, **kwargs)

    return wrapper
