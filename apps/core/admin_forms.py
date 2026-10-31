from django import forms
from unfold.forms import BaseDialogForm
from unfold.widgets import (
    UnfoldAdminDecimalFieldWidget,
    UnfoldAdminIntegerFieldWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminTextareaWidget,
    UnfoldAdminTextInputWidget,
    UnfoldAdminURLInputWidget,
)


class ShipOrderForm(BaseDialogForm):
    carrier = forms.CharField(max_length=60, widget=UnfoldAdminTextInputWidget)
    tracking_number = forms.CharField(max_length=100, widget=UnfoldAdminTextInputWidget)
    tracking_url = forms.URLField(required=False, widget=UnfoldAdminURLInputWidget)
    note = forms.CharField(
        required=False,
        max_length=500,
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 2}),
        help_text="Shown to the customer in the timeline.",
    )


class NoteForm(BaseDialogForm):
    note = forms.CharField(
        required=False,
        max_length=500,
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 3}),
        help_text="Optional note shown to the customer.",
    )


class CancelOrderForm(BaseDialogForm):
    reason = forms.CharField(max_length=300, widget=UnfoldAdminTextareaWidget(attrs={"rows": 3}))


class QuoteRespondForm(BaseDialogForm):
    message = forms.CharField(
        required=False,
        max_length=3000,
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 4}),
        help_text="Shown to the customer with the quote.",
    )
    valid_days = forms.IntegerField(min_value=1, max_value=120, initial=14, widget=UnfoldAdminIntegerFieldWidget)
    discount_percent = forms.DecimalField(
        required=False,
        min_value=0,
        max_value=60,
        decimal_places=2,
        max_digits=5,
        widget=UnfoldAdminDecimalFieldWidget,
        help_text="Optional: apply this discount to every line that has no quoted price yet.",
    )


class FabricPriceAdjustForm(BaseDialogForm):
    percent = forms.DecimalField(
        decimal_places=2,
        max_digits=6,
        widget=UnfoldAdminDecimalFieldWidget,
        help_text="e.g. 4.5 raises prices by 4.5 %, -3 lowers them by 3 %.",
    )


class CompanyTermsForm(BaseDialogForm):
    payment_terms = forms.ChoiceField(widget=UnfoldAdminSelectWidget)
    credit_limit = forms.DecimalField(min_value=0, decimal_places=2, max_digits=12, widget=UnfoldAdminDecimalFieldWidget)
    approval_threshold = forms.DecimalField(
        min_value=0, decimal_places=2, max_digits=12, widget=UnfoldAdminDecimalFieldWidget, required=False
    )
    customer_group = forms.ChoiceField(required=False, widget=UnfoldAdminSelectWidget)
    is_verified = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.accounts.models import Company
        from apps.pricing.models import CustomerGroup

        self.fields["payment_terms"].choices = Company.PaymentTerms.choices
        self.fields["customer_group"].choices = [("", "— keep —")] + [(g.pk, g.name) for g in CustomerGroup.objects.all()]
        if self.object_id:
            company = Company.objects.filter(pk=self.object_id).first()
            if company and not self.is_bound:
                self.initial.update(
                    payment_terms=company.payment_terms,
                    credit_limit=company.credit_limit,
                    approval_threshold=company.approval_threshold,
                    customer_group=company.customer_group_id or "",
                    is_verified=company.is_verified,
                )


class ConfirmPaymentForm(BaseDialogForm):
    amount = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        max_digits=12,
        widget=UnfoldAdminDecimalFieldWidget,
        help_text="Leave blank to confirm the full expected amount.",
    )
    reference = forms.CharField(required=False, max_length=120, widget=UnfoldAdminTextInputWidget)
