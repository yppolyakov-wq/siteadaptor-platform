"""Публичные вьюхи онбординга (живут в public-схеме, см. urls_public)."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views import View

from .forms import BusinessSignupForm
from .services import create_business


class BusinessSignupView(View):
    template_name = "tenants/onboarding.html"

    def get(self, request):
        return render(request, self.template_name, {"form": BusinessSignupForm()})

    def post(self, request):
        form = BusinessSignupForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        cd = form.cleaned_data
        tenant, login_url = create_business(
            business_name=cd["business_name"],
            slug=cd["slug"],
            business_type=cd["business_type"],
            city=cd["city"],
            email=cd["email"],
            password=cd["password1"],
        )
        messages.success(
            request,
            _("Business '%(name)s' created. Sign in on your subdomain.")
            % {"name": tenant.name},
        )
        return redirect(login_url)
