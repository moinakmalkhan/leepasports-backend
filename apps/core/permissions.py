from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsStaff(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class IsStaffOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class HasCompany(BasePermission):
    """User must belong to an active company (set by `CompanyContextMixin`)."""

    message = "You need to join or create a company before performing this action."

    def has_permission(self, request, view):
        membership = getattr(request, "membership", None)
        return bool(request.user.is_authenticated and membership is not None)


class CompanyRolePermission(BasePermission):
    """Checks `view.required_roles` (dict of action -> allowed roles)."""

    message = "Your role in this company does not allow this action."

    def has_permission(self, request, view):
        membership = getattr(request, "membership", None)
        if membership is None:
            return False
        required = getattr(view, "required_roles", {})
        action = getattr(view, "action", None) or request.method.lower()
        allowed = required.get(action)
        if allowed is None:
            return True
        return membership.role in allowed
