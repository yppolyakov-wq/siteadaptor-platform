"""SP (a11y-ревью ECC 2026-11-03): замки правок доступности серии «пространство».

Вкладки связаны с панелями (4.1.2), инфотекст не gray-400 (1.4.3), бейдж Text-Check
контрастный, выбранный тип акции не только цветом (aria-current), язык textarea
правовых текстов задан (3.1.2), уникальные имена кнопок дня/переноса (2.4.6).
"""

from pathlib import Path

from django.conf import settings

T = Path(settings.BASE_DIR) / "templates"


def _t(rel):
    return (T / rel).read_text(encoding="utf-8")


def test_tabs_linked_to_panels():
    for rel, prefix in (
        ("promotions/promotion_form.html", "pf"),
        ("tenant/legal_docs.html", "lg"),
    ):
        text = _t(rel)
        assert f'aria-controls="{prefix}-panel-' in text and 'role="tabpanel"' in text
        assert f'aria-labelledby="{prefix}-tab-' in text


def test_contrast_and_names():
    assert "text-gray-400" not in _t("catalog/_pf_field.html").split("_helptext")[0][-120:]
    assert "bg-amber-500 text-white" not in _t("promotions/_text_check_results.html")
    assert 'aria-current="page"' in _t("storefront/promo_page/_type_chips.html")
    assert 'lang="{{ cell.locale }}"' in _t("tenant/legal_docs.html")
    # UX-D D3.1 (осознанная переписка): чипы удаления правил — на странице ресурса
    assert "{{ it.day }} {{ g.time }}" in _t("booking/resource_page.html")
    assert "data-skip-neu" in _t("booking/_tagesplan_body.html")
