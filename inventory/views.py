from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from .models import Inventory, Product, Purchase, Reconciliation, Sale, StockMovement, Warehouse
from .roles import user_role_label


def _quick_actions(user):
    """Shortcuts into the admin pages, shown only if the person's role allows them."""
    if not user.is_staff:
        return []
    candidates = [
        ("Record a sale", reverse("admin:inventory_sale_add"), "inventory.add_sale",
         "Pick the customer and products. Prices fill in by themselves."),
        ("Record a payment", reverse("admin:inventory_payment_add"), "inventory.add_payment",
         "Money received from a customer."),
        ("Receive a delivery", reverse("admin:inventory_purchase_changelist"), "inventory.receive_goods",
         "Tick the purchase, then choose Receive goods."),
        ("Move stock between warehouses", reverse("admin:inventory_inventory_changelist"), "inventory.transfer_stock",
         "Tick the stock line, then choose Transfer."),
        ("Record a stock count", reverse("admin:inventory_reconciliation_add"), "inventory.add_reconciliation",
         "Enter what is on the shelf. The owner approves any difference."),
        ("Add a purchase", reverse("admin:inventory_purchase_add"), "inventory.add_purchase",
         "An order placed with a supplier."),
        ("Load opening stock", reverse("admin:inventory_import"), "inventory.import_stock",
         "One-time upload of starting stock from a spreadsheet."),
        ("Check stock levels", reverse("admin:inventory_inventory_changelist"), "inventory.view_inventory",
         "What is in each warehouse right now."),
    ]
    seen, actions = set(), []
    for title, url, perm, hint in candidates:
        if user.has_perm(perm) and title not in seen:
            seen.add(title)
            actions.append({"title": title, "url": url, "hint": hint})
    return actions


@login_required
def dashboard_view(request):
    user = request.user
    money = user.has_perm("inventory.view_financials")
    balances = user.has_perm("inventory.view_balances")
    can_admin = user.is_staff

    def can(perm):
        return can_admin and user.has_perm(perm)

    # ---- Stock figures (everyone) ----
    total_products = Product.objects.filter(active=True).count()
    total_stock = Inventory.objects.aggregate(total=Sum("quantity"))["total"] or 0

    low_stock_rows = [inv for inv in Inventory.objects.select_related("product", "warehouse").order_by("product__sku")
                      if inv.is_low_stock]
    low_stock_count = len({inv.product_id for inv in low_stock_rows})

    pending_qs = Purchase.objects.exclude(status__in=[Purchase.Status.RECEIVED, Purchase.Status.CANCELLED])
    pending_count = pending_qs.count()
    pending_rows = pending_qs.select_related("supplier").order_by("expected_delivery")[:10]

    recon_qs = Reconciliation.objects.filter(
        status__in=[Reconciliation.Status.PENDING, Reconciliation.Status.INVESTIGATING])
    recon_count = recon_qs.count()
    open_recons = recon_qs.select_related("product", "warehouse")[:10]

    recent_movements = StockMovement.objects.select_related("product", "warehouse").order_by("-timestamp")[:10]

    cards = {"stock": [
        {"label": "Units on hand", "value": f"{total_stock:,}",
         "note": f"Across {total_products} product{'s' if total_products != 1 else ''}"},
        {"label": "Low on stock", "value": str(low_stock_count), "alert": low_stock_count > 0,
         "note": "Below their reorder level" if low_stock_count else "Everything is above its reorder level"},
        {"label": "Waiting for delivery", "value": str(pending_count),
         "note": "Purchase orders not yet received" if pending_count else "Nothing on order"},
        {"label": "Stock counts to review", "value": str(recon_count), "alert": recon_count > 0,
         "note": "Waiting for the owner to approve" if recon_count else "No differences waiting"},
    ], "money": []}

    context = {
        "site_header": admin.site.site_header,
        "title": "Dashboard",
        "nav": "dashboard",
        "money": money,
        "balances": balances,
        "role_label": user_role_label(user),
        "cards": cards,
        "low_stock_rows": low_stock_rows,
        "pending_rows": pending_rows,
        "open_recons": open_recons,
        "recent_movements": recent_movements,
        "actions": _quick_actions(user),
        "links": {
            "product": can("inventory.view_product"),
            "customer": can("inventory.view_customer"),
            "purchase": can("inventory.view_purchase"),
            "reconciliation": can("inventory.view_reconciliation"),
            "stock": can("inventory.view_inventory"),
            "sales": can("inventory.view_sale"),
            "history": can("inventory.view_stockmovement"),
        },
    }

    # ---- Money figures: only calculated for people allowed to see them ----
    if money:
        stock_value = Inventory.objects.aggregate(
            value=Sum(ExpressionWrapper(F("quantity") * F("product__cost_price"), output_field=DecimalField()))
        )["value"] or 0
        cards["money"].append(
            {"label": "Stock value", "value": f"₦{stock_value:,.0f}", "note": "What the stock cost you"})

    if balances:
        today = timezone.now().date()
        owed = {}
        overdue_sales = 0
        for sale in Sale.objects.exclude(status=Sale.Status.CANCELLED).select_related("customer"):
            balance = sale.balance_due
            if balance <= 0:
                continue
            row = owed.setdefault(sale.customer_id, {"customer": sale.customer, "balance": 0, "count": 0,
                                                     "due": None, "overdue": False})
            row["balance"] += balance
            row["count"] += 1
            if sale.due_date and (row["due"] is None or sale.due_date < row["due"]):
                row["due"] = sale.due_date
            if sale.due_date and sale.due_date < today:
                row["overdue"] = True
                overdue_sales += 1
        owed_rows = sorted(owed.values(), key=lambda r: r["balance"], reverse=True)
        total_owed = sum((r["balance"] for r in owed_rows), 0)
        cards["money"].append(
            {"label": "Owed by customers", "value": f"₦{total_owed:,.0f}", "alert": total_owed > 0,
             "note": (f"{len(owed_rows)} customer{'s' if len(owed_rows) != 1 else ''}"
                      + (f", {overdue_sales} sale{'s' if overdue_sales != 1 else ''} past due" if overdue_sales else ""))
                     if owed_rows else "Nobody owes you anything"})
        context["owed_rows"] = owed_rows

    return render(request, "portal/dashboard.html", context)


def _page_context(request, nav):
    return {
        "site_header": admin.site.site_header,
        "role_label": user_role_label(request.user),
        "nav": nav,
        "money": request.user.has_perm("inventory.view_financials"),
    }


@login_required
def product_list_view(request):
    q = request.GET.get("q", "").strip()
    products = Product.objects.filter(active=True)
    if q:
        products = products.filter(Q(sku__icontains=q) | Q(name__icontains=q) | Q(category__icontains=q))
    products = products.annotate(total=Coalesce(Sum("inventory_records__quantity"), 0)).order_by("name")
    context = _page_context(request, "products")
    context.update({"title": "Products", "products": products, "q": q})
    return render(request, "portal/products.html", context)


@login_required
def product_detail_view(request, pk):
    """Stock by warehouse and the full history of one product (what came in, what went out, and why)."""
    product = get_object_or_404(Product, pk=pk)
    records = {r.warehouse_id: r for r in Inventory.objects.filter(product=product)}
    rows = []
    for wh in Warehouse.objects.filter(active=True).order_by("name"):
        r = records.get(wh.id)
        rows.append({"warehouse": wh, "quantity": r.quantity if r else 0,
                     "reserved": r.reserved_quantity if r else 0,
                     "available": r.available_quantity if r else 0})
    total = sum(r["quantity"] for r in rows)
    history = StockMovement.objects.filter(product=product).select_related("warehouse", "user").order_by("-timestamp")[:100]
    context = _page_context(request, "products")
    context.update({
        "title": product.name, "product": product, "rows": rows, "total": total,
        "total_available": sum(r["available"] for r in rows),
        "is_low": total <= product.reorder_level,
        "history": history,
    })
    return render(request, "portal/product_detail.html", context)
