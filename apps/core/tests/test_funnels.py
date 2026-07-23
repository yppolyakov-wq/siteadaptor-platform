"""E5 «задача-первым»: прогресс-степпер воронок (funnels + тег funnel_steps)."""

from django.template import Context, Template

from apps.core import funnels


def test_funnel_steps_states():
    steps = funnels.funnel_steps("stay", 2)
    assert [(s["n"], s["state"]) for s in steps] == [
        (1, "done"),
        (2, "current"),
        (3, "upcoming"),
    ]
    assert [s["state"] for s in funnels.funnel_steps("service", 1)] == [
        "current",
        "upcoming",
        "upcoming",
    ]


def test_funnel_steps_out_of_range_is_empty():
    # вне диапазона / неизвестный kind → пусто (степпер не рендерится, без регрессии)
    assert funnels.funnel_steps("stay", 0) == []
    assert funnels.funnel_steps("stay", 9) == []
    assert funnels.funnel_steps("bogus", 1) == []


def test_funnel_steps_tag_renders_stepper():
    html = Template('{% load siteui %}{% funnel_steps "stay" 2 %}').render(Context({}))
    assert "Auswahl" in html and "Daten" in html
    assert 'aria-current="step"' in html  # текущий шаг помечен
    # неизвестный/вне диапазона → пустой рендер
    assert (
        Template('{% load siteui %}{% funnel_steps "stay" 9 %}').render(Context({})).strip() == ""
    )
