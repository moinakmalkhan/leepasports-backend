from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import UUIDModel


class Review(UUIDModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending moderation"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    order_item = models.OneToOneField("orders.OrderItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="review")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=120, blank=True)
    body = models.TextField(max_length=3000, blank=True)
    size_purchased = models.CharField(max_length=12, blank=True)
    fit = models.CharField(
        max_length=10, blank=True, choices=[("small", "Runs small"), ("true", "True to size"), ("large", "Runs large")]
    )
    image = models.ImageField(upload_to="reviews/%Y/%m/", blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING, db_index=True)
    is_verified_purchase = models.BooleanField(default=False)
    helpful_count = models.PositiveIntegerField(default=0)
    staff_reply = models.TextField(blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=["product", "user"], name="uniq_review_per_user_product")]
        indexes = [models.Index(fields=["product", "status", "-created_at"]), models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return f"{self.rating}★ {self.product_id} by {self.user_id}"


class ReviewVote(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["review", "user"], name="uniq_review_vote")]

    def __str__(self):
        return f"vote {self.review_id}"
