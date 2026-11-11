"""FB-27 R4d: экран «Seitenvorlagen» снесён — настройки типа страницы правятся в
«Seitenaufbau». Замки старого экрана (плитки, сетка, «на все списки») остаются в силе:
они ходят сюда, а не выбрасываются.

`settings_screen(request)` принимает тот же запрос, что старая вьюха (`typ`, а в POST —
`setting`, `value`, `out_*`, `apply_all`): GET отдаёт панель настроек этого типа, POST
кладёт настройку в черновик и сразу сохраняет его (старый экран писал сразу).
"""

from urllib.parse import parse_qs, urlsplit

from django.http import QueryDict

from apps.core import site_schema
from apps.core.site_schema_views import site_schema_view


def _target(typ: str) -> dict:
    query = parse_qs(urlsplit(site_schema.settings_url(typ)).query)
    return {k: v[0] for k, v in query.items()}


def _query(data: dict) -> QueryDict:
    q = QueryDict(mutable=True)
    for key, value in data.items():
        q[key] = value
    return q


def settings_screen(request):
    if request.method != "POST":
        request.GET = _query(_target(request.GET.get("typ", "")))
        return site_schema_view(request)
    target = _target(request.POST.get("typ", ""))
    post = request.POST.copy()
    post["seite"] = target.get("seite", "")
    post["ref"] = target.get("block", "")
    post["op"] = "setting"
    request.POST = post
    site_schema_view(request)
    request.POST = _query({"seite": target.get("seite", ""), "op": "save"})
    return site_schema_view(request)
