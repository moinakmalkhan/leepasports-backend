"""
Price computation for a configured line.

unit_price = contract price (if any)
           | (labor + fabric_cost + fabric_adjustment)
             × (1 − group discount) × (1 − volume discount)

Each size may add a surcharge (2XL and up use more fabric). All lookups are
batched: one query for tiers, one for contract prices, one for the exchange
rate (cached) – no per-line database access.
"""

from dataclasses import asdict, dataclass, field
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.core.utils import jsonable, money

from .models import ExchangeRate, PriceListItem, VolumeTier

ONE = Decimal("1")
HUNDRED = Decimal("100")


@dataclass
class SizeLine:
    gender: str
    size_id: int
    size_label: str
    quantity: int
    surcharge_percent: Decimal
    unit_price: Decimal
    line_total: Decimal


@dataclass
class PriceBreakdown:
    currency: str
    quantity: int
    labor_price: Decimal
    fabric_cost: Decimal
    fabric_adjustment: Decimal
    list_unit_price: Decimal
    group_discount_percent: Decimal
    volume_discount_percent: Decimal
    contract_unit_price: Decimal | None
    unit_price: Decimal
    subtotal: Decimal
    savings: Decimal
    lines: list[SizeLine] = field(default_factory=list)
    next_tier: dict | None = None

    def as_dict(self):
        return jsonable(asdict(self))


def pkr_per_unit(currency: str | None = None) -> Decimal:
    currency = currency or settings.DEFAULT_CURRENCY
    key = f"fx:{currency}"
    rate = cache.get(key)
    if rate is None:
        row = ExchangeRate.objects.filter(currency=currency).values_list("pkr_per_unit", flat=True).first()
        rate = row or Decimal("280")
        cache.set(key, rate, 3600)
    return Decimal(rate)


def fabric_cost(fabric, consumption_kg: Decimal, currency: str | None = None) -> Decimal:
    """Convert the mill PKR price into selling currency for one piece."""
    if fabric.price_unit == fabric.Unit.METER:
        # Rough conversion: ~1.1 kg per metre at 72" width for 200 gsm; use gsm to scale.
        kg_per_meter = Decimal(fabric.gsm) * Decimal(fabric.width_inches) * Decimal("0.0254") / Decimal("1000")
        price_per_kg = fabric.price_pkr / (kg_per_meter or ONE)
    else:
        price_per_kg = fabric.price_pkr
    return money(price_per_kg * consumption_kg / pkr_per_unit(currency))


def volume_tiers_for(product) -> list[VolumeTier]:
    specific = list(VolumeTier.objects.filter(product=product).order_by("min_quantity"))
    if specific:
        return specific
    key = "volume_tiers:global"
    tiers = cache.get(key)
    if tiers is None:
        tiers = list(VolumeTier.objects.filter(product__isnull=True).order_by("min_quantity"))
        cache.set(key, tiers, 600)
    return tiers


def volume_discount(tiers, quantity: int):
    applied = Decimal("0")
    next_tier = None
    for tier in tiers:
        if quantity >= tier.min_quantity:
            applied = tier.discount_percent
        elif next_tier is None:
            next_tier = {
                "min_quantity": tier.min_quantity,
                "discount_percent": tier.discount_percent,
                "more_needed": tier.min_quantity - quantity,
            }
            break
    return applied, next_tier


def contract_price(product, company, quantity: int):
    if company is None:
        return None
    today = timezone.localdate()
    qs = PriceListItem.objects.filter(product=product, is_active=True, min_quantity__lte=quantity).filter(models_q_valid(today))
    item = qs.filter(company=company).order_by("-min_quantity").first()
    if item is None and company.customer_group_id:
        item = qs.filter(customer_group_id=company.customer_group_id).order_by("-min_quantity").first()
    return item.unit_price if item else None


def models_q_valid(today):
    from django.db.models import Q

    return (Q(valid_from__isnull=True) | Q(valid_from__lte=today)) & (Q(valid_to__isnull=True) | Q(valid_to__gte=today))


def compute_price(
    *, product, fabric, breakdown: list[dict], company=None, fabric_adjustment: Decimal | None = None, currency: str | None = None
) -> PriceBreakdown:
    """`breakdown` = [{"gender": "men", "size": <Size>, "quantity": 5}, ...]"""
    currency = currency or (company.currency if company else settings.DEFAULT_CURRENCY)
    quantity = sum(int(line["quantity"]) for line in breakdown)
    labor = money(product.labor_price)
    fabric_cost_value = fabric_cost(fabric, product.fabric_consumption_kg, currency)
    adjustment = money(fabric_adjustment or 0)
    list_price = money(labor + fabric_cost_value + adjustment)

    group_pct = money(company.customer_group.discount_percent) if company and company.customer_group_id else Decimal("0")
    tiers = volume_tiers_for(product)
    volume_pct, next_tier = volume_discount(tiers, quantity)

    contract = contract_price(product, company, quantity)
    if contract is not None:
        unit = money(contract)
        group_pct = Decimal("0")
        volume_pct = Decimal("0")
    else:
        unit = money(list_price * (ONE - group_pct / HUNDRED) * (ONE - volume_pct / HUNDRED))

    lines: list[SizeLine] = []
    subtotal = Decimal("0")
    for line in breakdown:
        size = line["size"]
        qty = int(line["quantity"])
        if qty <= 0:
            continue
        surcharge = Decimal(size.surcharge_percent or 0)
        line_unit = money(unit * (ONE + surcharge / HUNDRED))
        total = money(line_unit * qty)
        subtotal += total
        lines.append(SizeLine(line["gender"], size.id, size.label, qty, surcharge, line_unit, total))

    savings = money(max(list_price * quantity - subtotal, 0))
    return PriceBreakdown(
        currency=currency,
        quantity=quantity,
        labor_price=labor,
        fabric_cost=fabric_cost_value,
        fabric_adjustment=adjustment,
        list_unit_price=list_price,
        group_discount_percent=group_pct,
        volume_discount_percent=volume_pct,
        contract_unit_price=money(contract) if contract is not None else None,
        unit_price=unit,
        subtotal=money(subtotal),
        savings=savings,
        lines=lines,
        next_tier=next_tier,
    )


def base_price_for(product, currency: str | None = None) -> Decimal:
    """'From' price shown on cards: labor + base fabric at MOQ with global tiers."""
    tiers = volume_tiers_for(product)
    pct, _ = volume_discount(tiers, product.min_order_quantity)
    list_price = money(product.labor_price) + fabric_cost(product.base_fabric, product.fabric_consumption_kg, currency)
    return money(list_price * (ONE - pct / HUNDRED))
