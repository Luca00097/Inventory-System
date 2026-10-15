from django import forms

from .models import Warehouse


class TransferStockForm(forms.Form):
    to_warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.filter(active=True), label="Transfer to")
    quantity = forms.IntegerField(min_value=1)


class ReceivePurchaseForm(forms.Form):
    warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.filter(active=True), label="Receiving warehouse")
