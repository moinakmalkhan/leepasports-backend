from django.db import transaction
from django.db.models import Avg, Count, F

from apps.catalog.models import Product
from apps.core.exceptions import BusinessError

from .models import Review, ReviewVote


def recompute_rating(product_id: int):
    agg = Review.objects.filter(product_id=product_id, status=Review.Status.APPROVED).aggregate(avg=Avg("rating"), n=Count("id"))
    Product.objects.filter(pk=product_id).update(rating_avg=round(agg["avg"] or 0, 2), rating_count=agg["n"])


@transaction.atomic
def create_review(*, user, product: Product, data: dict) -> Review:
    from apps.orders.models import Order, OrderItem

    if Review.objects.filter(product=product, user=user).exists():
        raise BusinessError("You've already reviewed this product. You can edit your review instead.")
    purchased = (
        OrderItem.objects.filter(
            order__user=user, variant__product=product, order__status__in=[Order.Status.DELIVERED, Order.Status.COMPLETED]
        )
        .exclude(review__isnull=False)
        .select_related("variant__size")
        .first()
    )
    review = Review.objects.create(
        product=product,
        user=user,
        order_item=purchased,
        is_verified_purchase=purchased is not None,
        size_purchased=data.get("size_purchased")
        or (purchased.variant.size.label if purchased and purchased.variant and purchased.variant.size_id else ""),
        rating=data["rating"],
        title=data.get("title", ""),
        body=data.get("body", ""),
        fit=data.get("fit", ""),
        image=data.get("image"),
        # Verified purchases from real customers go live immediately; others wait for moderation.
        status=Review.Status.APPROVED if purchased else Review.Status.PENDING,
    )
    if review.status == Review.Status.APPROVED:
        recompute_rating(product.pk)
    from apps.core.utils import after_commit
    from apps.notifications.events import emit

    after_commit(lambda: emit("review.created", review_id=review.pk))
    return review


@transaction.atomic
def moderate(review: Review, status: str, reply: str = "") -> Review:
    from django.utils import timezone

    review.status = status
    if reply:
        review.staff_reply = reply
        review.replied_at = timezone.now()
    review.save(update_fields=["status", "staff_reply", "replied_at", "updated_at"])
    recompute_rating(review.product_id)
    return review


@transaction.atomic
def toggle_helpful(review: Review, user) -> bool:
    vote, created = ReviewVote.objects.get_or_create(review=review, user=user)
    if created:
        Review.objects.filter(pk=review.pk).update(helpful_count=F("helpful_count") + 1)
        return True
    vote.delete()
    Review.objects.filter(pk=review.pk).update(helpful_count=F("helpful_count") - 1)
    return False
