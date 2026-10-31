from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessError
from apps.core.utils import after_commit, money
from apps.notifications.events import emit

from .models import Payment


def create_pending_payment(order) -> Payment:
    """50% deposit for prepaid-deposit companies, otherwise full amount."""
    terms = order.payment_terms
    if terms == "deposit_50":
        amount, kind = money(order.grand_total * Decimal("0.5")), Payment.Kind.DEPOSIT
    else:
        amount, kind = order.grand_total, Payment.Kind.FULL
    return Payment.objects.create(
        order=order, kind=kind, method=order.payment_method, amount=amount, currency=order.currency, due_date=order.due_date
    )


@transaction.atomic
def submit_proof(payment: Payment, *, reference: str, proof=None, note: str = "") -> Payment:
    if payment.status not in (Payment.Status.PENDING, Payment.Status.FAILED):
        raise BusinessError("This payment has already been submitted.")
    payment.reference = reference[:120]
    payment.note = note[:500]
    if proof:
        payment.proof = proof
    payment.status = Payment.Status.SUBMITTED
    payment.submitted_at = timezone.now()
    payment.save()
    after_commit(lambda: emit("payment.submitted", payment_id=payment.pk))
    return payment


@transaction.atomic
def confirm(payment: Payment, *, by, amount=None) -> Payment:
    from apps.orders.services import record_payment

    payment = Payment.objects.select_for_update().select_related("order").get(pk=payment.pk)
    if payment.status == Payment.Status.CONFIRMED:
        raise BusinessError("Already confirmed.")
    if amount is not None:
        payment.amount = money(amount)
    payment.status = Payment.Status.CONFIRMED
    payment.confirmed_at = timezone.now()
    payment.confirmed_by = by
    payment.save()
    record_payment(payment.order, payment.amount)
    if payment.kind == Payment.Kind.DEPOSIT:
        balance = money(payment.order.grand_total - payment.order.amount_paid)
        if balance > 0 and not Payment.objects.filter(order=payment.order, kind=Payment.Kind.BALANCE).exists():
            Payment.objects.create(
                order=payment.order, kind=Payment.Kind.BALANCE, method=payment.method, amount=balance, currency=payment.currency
            )
    return payment
