from django.db.models import Count, OuterRef, Q, Subquery
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.exceptions import BusinessError
from apps.core.pagination import SmallPagination, TimelineCursorPagination
from apps.core.throttling import ChatRateThrottle

from . import services
from .models import Conversation, Message, Participant
from .serializers import ConversationSerializer, MessageSerializer, PostMessageSerializer, StartConversationSerializer


class ConversationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = ConversationSerializer
    pagination_class = SmallPagination
    lookup_field = "uid"
    filterset_fields = ("status",)
    throttle_classes = (ChatRateThrottle,)

    def get_queryset(self):
        user = self.request.user
        base = Conversation.objects.select_related("created_by", "assigned_to", "order")
        qs = base if user.is_staff else base.filter(created_by=user)
        last_read = Participant.objects.filter(conversation=OuterRef("pk"), user=user).values("last_read_at")[:1]
        return qs.annotate(
            unread_count=Count("messages", filter=Q(messages__created_at__gt=Subquery(last_read)) & ~Q(messages__sender=user))
        )

    @extend_schema(request=StartConversationSerializer, responses=ConversationSerializer)
    def create(self, request):
        serializer = StartConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        order = None
        if data.get("order"):
            from apps.orders.models import Order

            order = Order.objects.filter(uid=data["order"], user=request.user).first()
        subject = data.get("subject") or (f"Order {order.number}" if order else "Support request")
        conversation = services.start_conversation(
            user=request.user, subject=subject, body=data["body"], order=order, topic=data.get("topic", "")
        )
        return Response(ConversationSerializer(self.get_queryset().get(pk=conversation.pk)).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"])
    def messages(self, request, uid=None):
        conversation = self.get_object()
        if request.method == "GET":
            qs = Message.objects.filter(conversation=conversation).select_related("sender")
            paginator = TimelineCursorPagination()
            page = paginator.paginate_queryset(qs, request, view=self)
            services.mark_read(conversation, request.user)
            return paginator.get_paginated_response(MessageSerializer(page, many=True, context={"request": request}).data)
        serializer = PostMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        message = services.post_message(
            conversation,
            sender=request.user,
            body=data.get("body", ""),
            attachment=data.get("attachment"),
            client_id=data.get("client_id", ""),
        )
        return Response(MessageSerializer(message, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def read(self, request, uid=None):
        services.mark_read(self.get_object(), request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def close(self, request, uid=None):
        conversation = self.get_object()
        services.post_message(conversation, sender=request.user, body="Conversation closed.", kind=Message.Kind.SYSTEM)
        Conversation.objects.filter(pk=conversation.pk).update(status=Conversation.Status.CLOSED)
        return Response(ConversationSerializer(self.get_queryset().get(pk=conversation.pk)).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, uid=None):
        if not request.user.is_staff:
            raise BusinessError("Only staff can assign conversations.")
        conversation = self.get_object()
        conversation.assigned_to = request.user
        conversation.save(update_fields=["assigned_to", "updated_at"])
        return Response(ConversationSerializer(self.get_queryset().get(pk=conversation.pk)).data)

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        total = sum(
            c.unread_count for c in self.get_queryset().filter(status__in=[Conversation.Status.OPEN, Conversation.Status.PENDING])
        )
        return Response({"count": total, "at": timezone.now()})
