"""Context processors порталов (P2.3a): portal_user в каждом шаблоне портала."""


def portal_user(request):
    if getattr(request, "portal", None) is None:
        return {}
    from . import auth

    return {"portal_user": auth.current_portal_user(request)}
