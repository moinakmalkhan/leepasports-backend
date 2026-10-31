from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import CompanyContextMixin

from .selectors import resolve_configuration
from .serializers import PriceQuoteRequestSerializer
from .services import compute_price


class PriceQuoteView(CompanyContextMixin, APIView):
    """Live price for a configured line (used by the product configurator).

    Works for anonymous visitors (list price) and signed-in buyers (their
    group / contract pricing). Public, read-only and cheap: ~3 queries.
    """

    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = PriceQuoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product, fabric, adjustment, breakdown = resolve_configuration(**serializer.validated_data)
        result = compute_price(
            product=product, fabric=fabric, breakdown=breakdown, company=request.company, fabric_adjustment=adjustment
        )
        return Response(result.as_dict())
