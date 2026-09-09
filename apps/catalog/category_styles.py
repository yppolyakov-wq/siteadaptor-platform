"""KAT-1: шаблоны СТРАНИЦЫ категории /sortiment/<slug>/ и корня каталога.

Шаблон выбирает владелец per-категория (Category.page_style, select в форме);
"" = Standard — прежний вид фильтра байт-в-байт (замки характеризации целы).
Каждый шаблон собирается из ЖИВЫХ данных категории и деградирует сам: нет фото —
шапка текстовая, нет комбо — полосы нет (fail-soft, страница не пустеет).
Прецедент механики — catalog/option_styles.py (Product.variant_style).

**LAY-2 (2026-09-09): состав реестров переехал в `apps/core/compositions.py`.**
Владелец назвал «кашей» то, что одни и те же коды описаны в четырёх местах
(`schaufenster` — трижды, `magazin` — четырежды). Здесь остались РЕЗОЛВЕРЫ
(какой шаблон действует у этой категории) — а список кодов, порядок плиток и
подписи берутся из единого реестра. Публичная форма модуля не менялась:
`CATEGORY_PAGE_STYLES` и `root_styles()` по-прежнему отдают тройки
(код, метка, подсказка) в прежнем порядке (замки `test_lay2_compositions`).
"""

from apps.core import compositions

# Производные представления единого реестра (LAY-2). Порядок = порядок плиток.
CATEGORY_PAGE_STYLES = compositions.styles_for("category")
VALID_PAGE_STYLES = compositions.valid_for("category")

# DL-21.1: КОРНЕВАЯ страница каталога `/sortiment/` берёт тот же список — роль
# подкатегорий играют корневые направления. «Preisliste» на корне не шаблон:
# прайс-вид там уже даёт `catalog_layout.preset` в той же строке Studio, второй
# переключатель того же — урок DL-9. Исключение живёт в реестре с причиной
# (`compositions.EXCLUDED_REASONS`), а не молчаливым отсутствием.
ROOT_EXCLUDED = frozenset({"preisliste"})


def root_styles() -> list[tuple[str, object, object]]:
    return compositions.styles_for("catalog")


VALID_ROOT_STYLES = compositions.valid_for("catalog")


def root_page_style(raw) -> str:
    """Шаблон корневой страницы каталога (`site_config["catalog_page_style"]`).

    Дефолт КАТЕГОРИЙ сюда не наследуется (Р-2 плана DL-21): «поставил категориям
    Navigator — корень стал Navigator» был бы сюрпризом. Мусор → Standard.
    """
    code = (raw or "").strip() if isinstance(raw, str) else ""
    return code if code in VALID_ROOT_STYLES and code else ""


def page_style(category, site_default: str = "") -> str:
    """Эффективный шаблон страницы категории.

    DL-20 (запрос владельца «наследование через общие настройки»): два слоя и то же
    правило приоритета, что у форм карточки (`core.card_forms.card_form`) —

    * своё значение категории (`Category.page_style`) ПОБЕЖДАЕТ;
    * иначе действует дефолт сайта (`site_defaults["category_page_style"]`);
    * мусор в любом слое → "" (Standard), а не 500.

    До DL-20 второго слоя не было вовсе: владелец обязан был выставлять шаблон
    в каждой категории вручную.
    """
    code = (getattr(category, "page_style", "") or "").strip()
    if code in VALID_PAGE_STYLES and code:
        return code
    site_default = (site_default or "").strip()
    return site_default if site_default in VALID_PAGE_STYLES else ""
