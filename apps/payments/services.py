from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessError
from apps.core.utils import after_commit, money
from apps.notifications.events import emit

from .models import Payment


def create_pending_payment(order) -> Payment:
    return Payment.objects.create(order=order, method=order.payment_method, amount=order.grand_total, currency=order.currency)


@transaction.atomic
def submit_proof(payment: Payment, *, reference: str, proof=None, note: str = "") -> Payment:
    if payment.status not in (Payment.Status.PENDING, Payment.Status.FAILED):
        raise BusinessError("This payment has already been submitted.")
    payment.reference = reference[:120]
    payment.note = note[:300]
    if proof:
        payment.proof = proof
    payment.status = Payment.Status.SUBMITTED
    payment.submitted_at = timezone.now()
    payment.save()
    after_commit(lambda: emit("payment.submitted", payment_id=payment.pk))
    return payment


@transaction.atomic
def confirm(payment: Payment, *, by, amount=None) -> Payment:
    from apps.orders.services import mark_paid

    payment = Payment.objects.select_for_update().select_related("order").get(pk=payment.pk)
    if payment.status == Payment.Status.CONFIRMED:
        raise BusinessError("Already confirmed.")
    if amount is not None:
        payment.amount = money(amount)
    payment.status = Payment.Status.CONFIRMED
    payment.confirmed_at = timezone.now()
    payment.confirmed_by = by
    payment.save()
    mark_paid(payment.order, by=by, amount=payment.amount)
    return payment
