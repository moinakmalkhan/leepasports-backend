from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import UUIDModel


class Cart(UUIDModel):
    """One open cart per user; guests get a token-based cart merged on sign-in."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="cart")
    guest_token = models.CharField(max_length=64, blank=True, db_index=True)
    coupon_code = models.CharField(max_length=30, blank=True)
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        indexes = [models.Index(fields=["updated_at"])]
        constraints = [models.CheckConstraint(condition=Q(user__isnull=False) | ~Q(guest_token=""), name="cart_has_owner")]

    def __str__(self):
        return f"Cart {self.uid}"


class CartItem(UUIDModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.CASCADE, related_name="+")
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(fields=["cart", "variant"], name="uniq_cart_variant"),
            models.CheckConstraint(condition=Q(quantity__gte=1), name="cart_item_qty_positive"),
        ]

    def __str__(self):
        return f"{self.variant_id} × {self.quantity}"


class Wishlist(UUIDModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist")
    products = models.ManyToManyField("catalog.Product", through="WishlistItem", related_name="wishlisted_by")

    def __str__(self):
        return f"Wishlist {self.user_id}"


class WishlistItem(models.Model):
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="+")
    variant = models.ForeignKey("catalog.ProductVariant", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-added_at",)
        constraints = [models.UniqueConstraint(fields=["wishlist", "product"], name="uniq_wishlist_product")]

    def __str__(self):
        return f"{self.product_id} in {self.wishlist_id}"
