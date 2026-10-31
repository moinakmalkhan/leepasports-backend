from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.throttling import SearchRateThrottle


class CouponPreviewView(APIView):
    """Validate a code against the current cart without applying it."""

    permission_classes = (AllowAny,)
    throttle_classes = (SearchRateThrottle,)

    def post(self, request):
        from apps.cart import services as cart_services

        from .services import validate_coupon

        cart = cart_services.get_or_create_cart(request)
        items = cart_services.priced_items(cart)
        result = validate_coupon(
            request.data.get("code", ""),
            items=items,
            user=request.user if request.user.is_authenticated else None,
            email=request.data.get("email", ""),
        )
        return Response(
            {
                "code": result.coupon.code,
                "discount": result.discount,
                "free_shipping": result.free_shipping,
                "message": result.message,
            }
        )
