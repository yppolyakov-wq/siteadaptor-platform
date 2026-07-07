"""U-D2: generischer FSM-Aktionsblock (_status_actions.html + status_actions-Tag)."""

from types import SimpleNamespace

from django.template.loader import render_to_string


def _render(**ctx):
    return render_to_string("core/_status_actions.html", ctx)


def test_renders_fsm_buttons_from_status_via_tag():
    html = _render(kind="stay", obj=SimpleNamespace(status="pending"))
    assert 'value="confirmed"' in html
    assert 'value="cancelled"' in html
    # aus pending NICHT direkt erreichbar → kein Button
    assert 'value="fulfilled"' not in html


def test_confirmed_stay_offers_fulfill_noshow_cancel():
    html = _render(kind="stay", obj=SimpleNamespace(status="confirmed"))
    for target in ("fulfilled", "cancelled", "no_show"):
        assert f'value="{target}"' in html
    # danger-Ziele (cancel/no_show) → rote Kontur
    assert "text-red-600" in html


def test_terminal_status_renders_no_buttons():
    html = _render(kind="stay", obj=SimpleNamespace(status="cancelled"))
    assert "value=" not in html


def test_precomputed_actions_take_precedence_over_tag():
    actions = [{"target": "confirmed", "label": "Los!", "stage": "in_progress", "danger": False}]
    html = _render(actions=actions)
    assert 'value="confirmed"' in html
    assert "Los!" in html
