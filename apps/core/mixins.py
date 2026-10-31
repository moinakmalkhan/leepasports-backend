from django.utils.functional import cached_property


class CompanyContextMixin:
    """Resolve the acting company for the request.

    A user may belong to several companies (e.g. an agent buying for multiple
    clubs). The active company comes from the `X-Company-Id` header, falling
    back to the user's default membership. The membership is cached on the
    request so permission classes and views share one query.
    """

    def initial(self, request, *args, **kwargs):
        request.membership = self._resolve_membership(request)
        request.company = request.membership.company if request.membership else None
        super().initial(request, *args, **kwargs)

    @staticmethod
    def _resolve_membership(request):
        user = request.user
        if not user.is_authenticated:
            return None
        from apps.accounts.models import CompanyMember

        qs = CompanyMember.objects.select_related("company").filter(user=user, is_active=True, company__is_active=True)
        company_uid = request.headers.get("X-Company-Id")
        if company_uid:
            membership = qs.filter(company__uid=company_uid).first()
            if membership:
                return membership
        return qs.order_by("-is_default", "id").first()

    @cached_property
    def company(self):
        return getattr(self.request, "company", None)
