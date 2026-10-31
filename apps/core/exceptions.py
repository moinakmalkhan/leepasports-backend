import logging
import uuid

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("apps.core")


class BusinessError(APIException):
    """Raised by services when a domain rule is violated (returns 400)."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The request could not be processed."
    default_code = "business_error"


class ConflictError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The resource has changed, please refresh and try again."
    default_code = "conflict"


def api_exception_handler(exc, context):
    """Normalise every error into `{"detail": str, "code": str, "errors": {...}}`.

    The frontend relies on this shape to render toast messages consistently.
    """
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(detail=exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
    elif isinstance(exc, Http404):
        pass
    elif isinstance(exc, PermissionDenied):
        pass
    elif isinstance(exc, IntegrityError):
        logger.warning("Integrity error: %s", exc)
        exc = ConflictError("A record with these values already exists.")

    response = drf_exception_handler(exc, context)
    if response is None:
        request_id = getattr(context.get("request"), "request_id", uuid.uuid4().hex)
        logger.exception("Unhandled API error [%s]", request_id)
        return Response(
            {"detail": "Something went wrong on our side. Please try again.", "code": "server_error", "request_id": request_id},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    data = response.data
    code = getattr(exc, "default_code", "error")
    if isinstance(data, dict):
        detail = data.get("detail")
        if detail is not None and not isinstance(detail, (list, dict)):
            payload = {"detail": str(detail), "code": getattr(detail, "code", code)}
        else:
            # Field validation errors -> pick a friendly summary + keep per-field errors.
            first_key = next(iter(data), None)
            first_val = data[first_key] if first_key else None
            if isinstance(first_val, list) and first_val:
                summary = f"{first_key.replace('_', ' ').title()}: {first_val[0]}" if first_key != "detail" else str(first_val[0])
            elif isinstance(first_val, dict):
                summary = "Please correct the highlighted fields."
            else:
                summary = str(first_val) if first_val else "Invalid request."
            payload = {"detail": summary, "code": "validation_error", "errors": data}
    elif isinstance(data, list):
        payload = {"detail": str(data[0]) if data else "Invalid request.", "code": code, "errors": data}
    else:
        payload = {"detail": str(data), "code": code}
    response.data = payload
    return response
