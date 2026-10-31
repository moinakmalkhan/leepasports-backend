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
    carrier = forms.ChoiceField(
        choices=[
            ("TCS", "TCS"),
            ("Leopards", "Leopards Courier"),
            ("M&P", "M&P"),
            ("Trax", "Trax"),
            ("PostEx", "PostEx"),
            ("BlueEx", "BlueEx"),
            ("Other", "Other"),
        ],
        widget=UnfoldAdminSelectWidget,
    )
    tracking_number = forms.CharField(max_length=100, widget=UnfoldAdminTextInputWidget)
    tracking_url = forms.URLField(required=False, widget=UnfoldAdminURLInputWidget)
    estimated_delivery = forms.DateField(required=False, widget=UnfoldAdminTextInputWidget(attrs={"type": "date"}))
    note = forms.CharField(
        required=False, max_length=500, widget=UnfoldAdminTextareaWidget(attrs={"rows": 2}), help_text="Shown to the customer."
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


class ConfirmPaymentForm(BaseDialogForm):
    amount = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        max_digits=12,
        widget=UnfoldAdminDecimalFieldWidget,
        help_text="Leave blank to confirm the full amount.",
    )
    reference = forms.CharField(required=False, max_length=120, widget=UnfoldAdminTextInputWidget)


class StockAdjustForm(BaseDialogForm):
    delta = forms.IntegerField(widget=UnfoldAdminIntegerFieldWidget, help_text="Positive to add stock, negative to remove.")
    reason = forms.CharField(required=False, max_length=120, widget=UnfoldAdminTextInputWidget)


class PriceAdjustForm(BaseDialogForm):
    percent = forms.DecimalField(
        decimal_places=2,
        max_digits=6,
        widget=UnfoldAdminDecimalFieldWidget,
        help_text="e.g. -20 puts the selected products 20% on sale (original price kept as compare-at).",
    )


class ResolveReturnForm(BaseDialogForm):
    status = forms.ChoiceField(
        choices=[
            ("approved", "Approve"),
            ("received", "Mark received"),
            ("completed", "Complete (refund / exchange done)"),
            ("rejected", "Reject"),
        ],
        widget=UnfoldAdminSelectWidget,
    )
    refund_amount = forms.DecimalField(
        required=False, min_value=0, decimal_places=2, max_digits=12, widget=UnfoldAdminDecimalFieldWidget
    )
    refund_method = forms.ChoiceField(
        required=False,
        choices=[
            ("", "—"),
            ("bank transfer", "Bank transfer"),
            ("JazzCash/EasyPaisa", "JazzCash / EasyPaisa"),
            ("store credit", "Store credit"),
            ("original method", "Original method"),
        ],
        widget=UnfoldAdminSelectWidget,
    )
    staff_notes = forms.CharField(
        required=False,
        max_length=1000,
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 3}),
        help_text="Shown to the customer if rejected.",
    )


class ReviewReplyForm(BaseDialogForm):
    reply = forms.CharField(max_length=1000, widget=UnfoldAdminTextareaWidget(attrs={"rows": 3}))
