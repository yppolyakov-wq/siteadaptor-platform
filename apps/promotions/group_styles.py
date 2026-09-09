"""DL-20: реестр шаблонов СТРАНИЦЫ ГРУППЫ АКЦИЙ (`/aktionen/?gruppe=<группа>`).

До этой волны страницы группы фактически не было: фильтр по группе отдавал плоскую
сетку под общим заголовком «Aktuelle Angebote», и посетитель, пришедший по ссылке из
меню, не видел даже названия того, что открыл.

Механика — копия DL-19/DL-20 для товарной категории, но хранение другое: **модели
группы не существует**, `Promotion.group` — свободный текст. Поэтому выбор «только
для этой группы» живёт в `site_config["promo_groups"] = {<группа>: <стиль>}`
(ключ = то же плоское значение, что и у фасета `?gruppe=`), а общий дефолт — в
`site_defaults["promo_group_style"]`. Оба presence-minimal → golden-эталоны целы,
миграций нет.

**LAY-2 (2026-09-09):** состав всех трёх реестров переехал в
`apps/core/compositions.py` — владелец назвал «кашей» то, что одни и те же коды
живут в четырёх местах (`schaufenster` описан трижды, `magazin` четырежды, а
`kompakt` обзора рендерит буквально тот же include, что `prospekt` группы).
Здесь остались РЕЗОЛВЕРЫ (какой шаблон действует у этой страницы); публичная
форма модуля прежняя — тройки (код, метка, подсказка) в том же порядке.
"""

from __future__ import annotations

from apps.core import compositions

# (код, метка, подсказка «когда уместно»). Порядок = порядок плиток выбора.
# LAY-2: производное представление единого реестра `apps.core.compositions`.
GROUP_PAGE_STYLES = compositions.styles_for("promo_group")
VALID_GROUP_STYLES = compositions.valid_for("promo_group")


def group_style(group: str, per_group=None, site_default: str = "") -> str:
    """Эффективный шаблон страницы группы: свой у группы → дефолт сайта → Standard.

    Правило приоритета то же, что у форм карточки и шаблона категории. Неизвестный
    ключ в любом слое → "" (прежняя плоская сетка), а не 500: имя группы —
    свободный текст, и переименование в форме акции осиротит запись словаря.
    """
    own = ((per_group or {}).get(group or "") or "").strip()
    if own in VALID_GROUP_STYLES and own:
        return own
    site_default = (site_default or "").strip()
    return site_default if site_default in VALID_GROUP_STYLES else ""


# ── DL-21.2: ОБЗОРНАЯ страница `/aktionen/` ────────────────────────────────────
# Шесть стилей категории ложатся на акции именно здесь: «подкатегории» обзора —
# группы, «товары» — акции. У страницы группы (выше) под-сущностей нет — там DL-20.
# Без «sets» (у акций нет наборов) и без «mosaik» (бенто режет цену/срок на малых
# плитках — честнее не обещать).
PROMO_PAGE_STYLES = compositions.styles_for("promos")
VALID_PROMO_PAGE_STYLES = compositions.valid_for("promos")


def promo_page_style(raw) -> str:
    """Шаблон обзорной страницы акций (`site_config["promo_page_style"]`); мусор → ""."""
    code = (raw or "").strip() if isinstance(raw, str) else ""
    return code if code in VALID_PROMO_PAGE_STYLES and code else ""


# ── STU-15a: ШАБЛОН СТРАНИЦЫ ОДНОЙ АКЦИИ (`/p/<uuid>/`) ───────────────────────
# Проверка STU-14 показала последнюю дыру охвата: у страницы товара шаблон есть
# (`product_detail.layout`), у категории и группы акций — тоже, а у детали акции
# не было ни одного. Между тем именно у акции выбор осмыслен НА КАЖДУЮ: одна —
# длинный рассказ («почему этот сет выгоден»), другая — короткий флаер, где важны
# только цена, срок и кнопка.
#
# Хранение — как у формы карточки (DL-19): поле `Promotion.page_style` («только эта
# акция») побеждает `site_defaults["promo_detail_style"]` («для всех»).
PROMOTION_DETAIL_STYLES = compositions.styles_for("promo")
VALID_PROMOTION_DETAIL_STYLES = compositions.valid_for("promo")


def promotion_detail_style(own: str, site_default: str = "") -> str:
    """Эффективный шаблон страницы акции: своё у акции → дефолт сайта → Standard.

    Правило и fail-safe те же, что у формы карточки и шаблона категории: мусор в
    любом слое проваливается ниже, а не роняет страницу (значение приезжает и из
    старых конфигов, и из формы, и из живого черновика канвы).
    """
    own = (own or "").strip() if isinstance(own, str) else ""
    if own and own in VALID_PROMOTION_DETAIL_STYLES:
        return own
    site_default = (site_default or "").strip() if isinstance(site_default, str) else ""
    return site_default if site_default in VALID_PROMOTION_DETAIL_STYLES else ""
