from django.core.cache import cache
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.pagination import TimelineCursorPagination

from .models import Notification
from .serializers import NotificationSerializer
from .services import unread_cache_key, unread_count


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = NotificationSerializer
    pagination_class = TimelineCursorPagination
    lookup_field = "uid"

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        if self.request.query_params.get("unread") == "1":
            qs = qs.filter(is_read=False)
        return qs

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread(self, request):
        return Response({"count": unread_count(request.user)})

    @action(detail=True, methods=["post"])
    def read(self, request, uid=None):
        Notification.objects.filter(user=request.user, uid=uid, is_read=False).update(is_read=True, read_at=timezone.now())
        cache.delete(unread_cache_key(request.user.pk))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True, read_at=timezone.now())
        cache.delete(unread_cache_key(request.user.pk))
        return Response({"detail": "All notifications marked as read."})

    @action(detail=False, methods=["delete"])
    def clear(self, request):
        Notification.objects.filter(user=request.user, is_read=True).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
