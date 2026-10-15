import json

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path
from django.utils.html import format_html

from .forms import ReceivePurchaseForm, TransferStockForm
from .importers import apply_import, build_template_xlsx, parse_file, validate_rows
from .invoices import generate_invoice_pdf
from .models import (
    Customer,
    Inventory,
    Payment,
    Product,
    Purchase,
    PurchaseItem,
    Reconciliation,
    Sale,
    SaleItem,
    StockMovement,
    Supplier,
    Warehouse,
)
from .services.stock import SaleNotReady, apply_reconciliation, confirm_sale, receive_purchase_item, transfer_stock

# Branding — edit these to your actual business name.
admin.site.site_header = "Mouka & Golden Penny Distribution"
admin.site.site_title = "Inventory Admin"
admin.site.index_title = "Inventory & Sales Dashboard"


def _can_see_money(request):
    return request.user.has_perm("inventory.view_financials")


def _can_see_balances(request):
    return request.user.has_perm("inventory.view_balances")


def _price_map_json(field_name):
    """Builds {product_id: price} as a JSON string for the auto-fill JS."""
    values = Product.objects.values_list("id", field_name)
    return json.dumps({str(pid): str(price) for pid, price in values})


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "payment_terms", "lead_time_days", "active")
    search_fields = ("name", "phone", "email")
    list_filter = ("active",)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "manager", "capacity", "active")
    list_filter = ("active",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "category", "unit", "cost_price", "selling_price", "reorder_level", "stock_status", "active")
    search_fields = ("sku", "name")
    list_filter = ("category", "unit", "active")

    def get_list_display(self, request):
        cols = list(super().get_list_display(request))
        if not _can_see_money(request):
            cols.remove("cost_price")
        return cols

    def get_exclude(self, request, obj=None):
        return None if _can_see_money(request) else ("cost_price",)

    @admin.display(description="Total stock")
    def stock_status(self, obj):
        total = obj.total_stock
        if total <= obj.reorder_level:
            return format_html('<span style="color:#b91c1c;font-weight:600;">{} (low)</span>', total)
        return total


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "credit_limit", "balance_display", "payment_terms_days", "active")
    search_fields = ("name", "phone", "email")
    list_filter = ("active",)
    readonly_fields = ("current_balance",)

    def get_list_display(self, request):
        cols = list(super().get_list_display(request))
        if not _can_see_balances(request):
            cols.remove("balance_display")
        return cols

    def get_readonly_fields(self, request, obj=None):
        return ("current_balance",) if _can_see_balances(request) else ()

    @admin.display(description="Current balance")
    def balance_display(self, obj):
        bal = obj.current_balance
        if bal > 0:
            return format_html('<span style="color:#b91c1c;font-weight:600;">{}</span>', bal)
        return bal


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("product", "warehouse", "quantity", "reserved_quantity", "available_quantity", "low_stock_flag")
    list_filter = ("warehouse",)
    search_fields = ("product__sku", "product__name")
    actions = ["transfer_selected"]
    readonly_fields = ("product", "warehouse", "quantity", "reserved_quantity")

    def has_transfer_permission(self, request):
        return request.user.has_perm("inventory.transfer_stock")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(boolean=True, description="Low stock")
    def low_stock_flag(self, obj):
        return obj.is_low_stock

    @admin.action(description="Transfer selected stock to another warehouse", permissions=["transfer"])
    def transfer_selected(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one inventory row to transfer.", level=messages.WARNING)
            return
        inventory = queryset.first()
        return redirect("admin:inventory_transfer", pk=inventory.pk)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("transfer/<int:pk>/", self.admin_site.admin_view(self.transfer_view), name="inventory_transfer"),
            path("import/", self.admin_site.admin_view(self.import_view), name="inventory_import"),
            path("import/confirm/", self.admin_site.admin_view(self.import_confirm_view), name="inventory_import_confirm"),
            path("import/template/", self.admin_site.admin_view(self.import_template_view), name="inventory_import_template"),
        ]
        return custom + urls

    def _can_import(self, request):
        return request.user.has_perm("inventory.import_stock")

    def import_template_view(self, request):
        if not self._can_import(request):
            return redirect("admin:inventory_inventory_changelist")
        response = HttpResponse(
            build_template_xlsx(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="opening-stock-template.xlsx"'
        return response

    def import_view(self, request):
        if not self._can_import(request):
            self.message_user(request, "You do not have permission to import stock.", level=messages.ERROR)
            return redirect("admin:inventory_inventory_changelist")
        context = {**self.admin_site.each_context(request), "opts": Inventory._meta, "title": "Import opening stock", "preview": None, "errors": None}
        if request.method == "POST" and request.FILES.get("file"):
            try:
                rows = parse_file(request.FILES["file"])
            except ValueError as exc:
                context["errors"] = [str(exc)]
            else:
                clean, errors = validate_rows(rows)
                if errors:
                    context["errors"] = errors
                else:
                    request.session["stock_import_rows"] = clean
                    context["preview"] = clean
                    context["total_units"] = sum(r["quantity"] for r in clean)
                    context["new_products"] = len({r["new_product"]["sku"] for r in clean if r["new_product"]})
        elif request.method == "POST":
            context["errors"] = ["Please choose a file first."]
        return render(request, "admin/inventory/import_stock.html", context)

    def import_confirm_view(self, request):
        if request.method != "POST" or not self._can_import(request):
            return redirect("admin:inventory_import")
        rows = request.session.pop("stock_import_rows", None)
        if not rows:
            self.message_user(request, "Nothing to import - upload the file again.", level=messages.WARNING)
            return redirect("admin:inventory_import")
        # Re-validate right before saving in case data changed since the preview.
        rows_for_check = [{**{"_row": r["row"], "sku": r["sku"], "warehouse": r["warehouse_name"],
                              "quantity": str(r["quantity"])}, **(r["new_product"] or {})} for r in rows]
        clean, errors = validate_rows(rows_for_check)
        if errors:
            self.message_user(request, "The data changed since the preview: " + "; ".join(errors[:3]), level=messages.ERROR)
            return redirect("admin:inventory_import")
        summary = apply_import(rows, user=request.user)
        self.message_user(
            request,
            f"Opening stock loaded: {summary['units']} units across {summary['stock_lines']} lines, "
            f"{summary['products_created']} new product(s) created.",
        )
        return redirect("admin:inventory_inventory_changelist")

    def transfer_view(self, request, pk):
        if not self.has_transfer_permission(request):
            self.message_user(request, "You do not have permission to transfer stock.", level=messages.ERROR)
            return redirect("admin:inventory_inventory_changelist")
        inventory = Inventory.objects.get(pk=pk)
        if request.method == "POST":
            form = TransferStockForm(request.POST)
            if form.is_valid():
                to_warehouse = form.cleaned_data["to_warehouse"]
                quantity = form.cleaned_data["quantity"]
                if to_warehouse == inventory.warehouse:
                    form.add_error("to_warehouse", "Pick a different warehouse.")
                elif quantity > inventory.available_quantity:
                    form.add_error("quantity", f"Only {inventory.available_quantity} available to transfer.")
                else:
                    transfer_stock(
                        product=inventory.product, from_warehouse=inventory.warehouse,
                        to_warehouse=to_warehouse, quantity=quantity, user=request.user,
                    )
                    self.message_user(
                        request,
                        f"Transferred {quantity} x {inventory.product} from {inventory.warehouse} to {to_warehouse}.",
                    )
                    return redirect("admin:inventory_inventory_changelist")
        else:
            form = TransferStockForm()
        return render(request, "admin/inventory/transfer_form.html", {
            **self.admin_site.each_context(request), "form": form, "inventory": inventory, "opts": Inventory._meta, "title": "Transfer stock",
        })


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 1
    readonly_fields = ("total_cost", "quantity_outstanding")

    def get_fields(self, request, obj=None):
        fields = ["product", "quantity_ordered", "quantity_received", "unit_cost", "total_cost", "quantity_outstanding"]
        if not _can_see_money(request):
            fields.remove("unit_cost")
            fields.remove("total_cost")
        return fields
    class Media:
        js = ("inventory/auto_price.js",)


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("id", "supplier", "purchase_date", "expected_delivery", "status", "total_cost")
    list_filter = ("status", "supplier")
    inlines = [PurchaseItemInline]
    readonly_fields = ("total_cost",)
    actions = ["receive_selected"]

    def has_receive_goods_permission(self, request):
        return request.user.has_perm("inventory.receive_goods")

    def get_list_display(self, request):
        cols = list(super().get_list_display(request))
        if not _can_see_money(request):
            cols.remove("total_cost")
        return cols

    def get_readonly_fields(self, request, obj=None):
        base = ("total_cost",) if _can_see_money(request) else ()
        return base + ("created_by",) if obj else base

    def get_exclude(self, request, obj=None):
        return ("created_by",) if obj is None else None

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def _price_context(self, extra_context):
        extra_context = extra_context or {}
        extra_context["product_price_map_json"] = _price_map_json("cost_price")
        return extra_context

    def add_view(self, request, form_url="", extra_context=None):
        return super().add_view(request, form_url, self._price_context(extra_context))

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return super().change_view(request, object_id, form_url, self._price_context(extra_context))

    @admin.action(description="Receive goods for selected purchase", permissions=["receive_goods"])
    def receive_selected(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one purchase to receive.", level=messages.WARNING)
            return
        return redirect("admin:purchase_receive", pk=queryset.first().pk)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("receive/<int:pk>/", self.admin_site.admin_view(self.receive_view), name="purchase_receive"),
        ]
        return custom + urls

    def receive_view(self, request, pk):
        if not self.has_receive_goods_permission(request):
            self.message_user(request, "You do not have permission to receive goods.", level=messages.ERROR)
            return redirect("admin:inventory_purchase_changelist")
        purchase = Purchase.objects.get(pk=pk)
        items = list(purchase.items.select_related("product"))

        if request.method == "POST":
            warehouse_form = ReceivePurchaseForm(request.POST)
            if warehouse_form.is_valid():
                warehouse = warehouse_form.cleaned_data["warehouse"]
                received_any = False
                for item in items:
                    raw = request.POST.get(f"qty_{item.id}", "0").strip()
                    qty = int(raw) if raw.isdigit() else 0
                    if qty > 0:
                        receive_purchase_item(purchase_item=item, quantity_received=qty, warehouse=warehouse, user=request.user)
                        received_any = True
                if received_any:
                    self.message_user(request, f"Received goods for {purchase} at {warehouse}.")
                else:
                    self.message_user(request, "No quantities entered — nothing received.", level=messages.WARNING)
                return redirect("admin:inventory_purchase_changelist")
        else:
            warehouse_form = ReceivePurchaseForm()

        rows = [{"item": item, "outstanding": item.quantity_outstanding} for item in items]
        return render(request, "admin/purchase/receive_form.html", {
            **self.admin_site.each_context(request), "purchase": purchase, "warehouse_form": warehouse_form, "rows": rows,
            "opts": Purchase._meta, "title": "Receive purchase",
        })


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 1
    readonly_fields = ("total_price",)
    class Media:
        js = ("inventory/auto_price.js",)


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "warehouse", "sale_date", "due_date", "status", "total_amount", "amount_paid", "balance_display", "invoice_link")
    list_filter = ("status", "warehouse")
    inlines = [SaleItemInline]
    readonly_fields = ("total_amount", "amount_paid", "balance_due")
    actions = ["confirm_selected"]

    def get_readonly_fields(self, request, obj=None):
        base = ("total_amount", "amount_paid", "balance_due")
        return base + ("created_by",) if obj else base

    def get_exclude(self, request, obj=None):
        return ("created_by",) if obj is None else None

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def _price_context(self, extra_context):
        extra_context = extra_context or {}
        extra_context["product_price_map_json"] = _price_map_json("selling_price")
        return extra_context

    def add_view(self, request, form_url="", extra_context=None):
        return super().add_view(request, form_url, self._price_context(extra_context))

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return super().change_view(request, object_id, form_url, self._price_context(extra_context))

    @admin.display(description="Balance due")
    def balance_display(self, obj):
        bal = obj.balance_due
        if bal > 0:
            return format_html('<span style="color:#b91c1c;font-weight:600;">{}</span>', bal)
        return bal

    @admin.display(description="Invoice")
    def invoice_link(self, obj):
        if not obj.pk:
            return ""
        return format_html('<a href="/admin/inventory/sale/{}/invoice/">Download PDF</a>', obj.pk)

    @admin.action(description="Confirm selected sales (deducts stock)")
    def confirm_selected(self, request, queryset):
        confirmed = 0
        skipped = 0
        for sale in queryset:
            if sale.status != Sale.Status.DRAFT:
                skipped += 1
                continue
            try:
                confirm_sale(sale=sale, user=request.user)
            except SaleNotReady as exc:
                self.message_user(request, f"{sale} was not confirmed: {exc}.", level=messages.ERROR)
                continue
            confirmed += 1
        if confirmed:
            self.message_user(request, f"Confirmed {confirmed} sale(s) — stock deducted.")
        if skipped:
            self.message_user(request, f"Skipped {skipped} sale(s) that weren't in Draft status.", level=messages.WARNING)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("<int:pk>/invoice/", self.admin_site.admin_view(self.invoice_view), name="sale_invoice"),
        ]
        return custom + urls

    def invoice_view(self, request, pk):
        sale = Sale.objects.select_related("customer").get(pk=pk)
        pdf_bytes = generate_invoice_pdf(sale)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="invoice-S-{sale.id:04d}.pdf"'
        return response


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("customer", "sale", "date", "amount", "method")
    list_filter = ("method",)
    search_fields = ("customer__name",)

    def get_readonly_fields(self, request, obj=None):
        return ("recorded_by",) if obj else ()

    def get_exclude(self, request, obj=None):
        return ("recorded_by",) if obj is None else None

    def save_model(self, request, obj, form, change):
        if not change and not obj.recorded_by_id:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)
        if obj.sale_id:
            obj.sale.refresh_balance_cache()


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "product", "warehouse", "movement_type", "quantity", "reference", "user")
    list_filter = ("movement_type", "warehouse")
    search_fields = ("product__sku", "reference")
    date_hierarchy = "timestamp"
    readonly_fields = [f.name for f in StockMovement._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Reconciliation)
class ReconciliationAdmin(admin.ModelAdmin):
    list_display = ("date", "product", "warehouse", "system_quantity", "physical_quantity", "variance", "status", "approved_by")
    list_filter = ("status", "warehouse")
    actions = ["approve_selected"]

    def get_exclude(self, request, obj=None):
        # On a new count the person only types what they physically counted;
        # the system quantity is filled in from the stock records when saved.
        return ("system_quantity", "status", "approved_by") if obj is None else None

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        if obj.status in (Reconciliation.Status.APPROVED, Reconciliation.Status.REJECTED):
            return ("approved_by", "system_quantity", "product", "warehouse", "physical_quantity", "status")
        return ("approved_by", "system_quantity")

    def save_model(self, request, obj, form, change):
        if not change:
            record = Inventory.objects.filter(product=obj.product, warehouse=obj.warehouse).first()
            obj.system_quantity = record.quantity if record else 0
        super().save_model(request, obj, form, change)

    def has_approve_reconciliation_permission(self, request):
        return request.user.has_perm("inventory.approve_reconciliation")

    @admin.action(description="Approve selected reconciliations (posts adjustment)", permissions=["approve_reconciliation"])
    def approve_selected(self, request, queryset):
        approved = 0
        skipped = 0
        for recon in queryset:
            if recon.status != Reconciliation.Status.PENDING and recon.status != Reconciliation.Status.INVESTIGATING:
                skipped += 1
                continue
            apply_reconciliation(reconciliation=recon, user=request.user)
            approved += 1
        if approved:
            self.message_user(request, f"Approved {approved} reconciliation(s) — stock adjusted.")
        if skipped:
            self.message_user(request, f"Skipped {skipped} already-resolved reconciliation(s).", level=messages.WARNING)
