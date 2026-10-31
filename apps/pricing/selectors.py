from django.shortcuts import get_object_or_404

from apps.catalog.models import Product, ProductFabricOption, ProductSizeOption
from apps.core.exceptions import BusinessError


def resolve_configuration(*, product, fabric=None, breakdown):
    """Validate a (product, fabric, size breakdown) trio against the catalog.

    Returns (product, fabric, price_adjustment, normalised_breakdown) where each
    breakdown line carries the `Size` instance. Three queries total.
    """
    product_obj = (
        get_object_or_404(Product.objects.active().select_related("base_fabric"), slug=product)
        if isinstance(product, str)
        else product
    )

    options = {
        o.fabric.slug: o
        for o in ProductFabricOption.objects.select_related("fabric").filter(product=product_obj, fabric__is_active=True)
    }
    if fabric:
        option = options.get(fabric)
        if option is None:
            raise BusinessError("That fabric is not available for this product.")
        fabric_obj, adjustment = option.fabric, option.price_adjustment
    else:
        default = next((o for o in options.values() if o.is_default), None)
        fabric_obj = default.fabric if default else product_obj.base_fabric
        adjustment = default.price_adjustment if default else 0

    allowed = {
        (o.gender, o.size_id): o.size
        for o in ProductSizeOption.objects.select_related("size").filter(product=product_obj, is_active=True)
    }
    normalised = []
    for line in breakdown:
        qty = int(line["quantity"])
        if qty <= 0:
            continue
        size = allowed.get((line["gender"], int(line["size_id"])))
        if size is None:
            raise BusinessError(f"Size {line['size_id']} is not offered for {line['gender']} on this product.")
        normalised.append({"gender": line["gender"], "size": size, "quantity": qty})
    if not normalised:
        raise BusinessError("Add at least one size quantity.")
    total = sum(line["quantity"] for line in normalised)
    if total < product_obj.min_order_quantity:
        raise BusinessError(f"Minimum order for {product_obj.name} is {product_obj.min_order_quantity} pieces.")
    if product_obj.order_increment > 1 and total % product_obj.order_increment:
        raise BusinessError(f"Quantity must be a multiple of {product_obj.order_increment}.")
    return product_obj, fabric_obj, adjustment, normalised
