from django.db import transaction

from inventory.models import Inventory, StockMovement


def record_stock_movement(*, product, warehouse, quantity, movement_type, reference="", user=None, notes=""):
    with transaction.atomic():
        movement = StockMovement.objects.create(
            product=product, warehouse=warehouse, quantity=quantity,
            movement_type=movement_type, reference=reference, user=user, notes=notes,
        )
        inventory, _ = Inventory.objects.select_for_update().get_or_create(product=product, warehouse=warehouse)
        inventory.quantity += quantity
        inventory.save(update_fields=["quantity", "updated_at"])
        if inventory.is_low_stock:
            trigger_low_stock_alert(inventory)
    return movement


def transfer_stock(*, product, from_warehouse, to_warehouse, quantity, user=None, reference=""):
    if quantity <= 0:
        raise ValueError("Transfer quantity must be positive")
    reference = reference or f"TR-{product.sku}"
    with transaction.atomic():
        out_movement = record_stock_movement(
            product=product, warehouse=from_warehouse, quantity=-quantity,
            movement_type=StockMovement.MovementType.TRANSFER_OUT, reference=reference, user=user,
        )
        in_movement = record_stock_movement(
            product=product, warehouse=to_warehouse, quantity=quantity,
            movement_type=StockMovement.MovementType.TRANSFER_IN, reference=reference, user=user,
        )
    return out_movement, in_movement


def receive_purchase_item(*, purchase_item, quantity_received, warehouse, user=None):
    from inventory.models import Purchase

    with transaction.atomic():
        purchase_item.quantity_received += quantity_received
        purchase_item.save(update_fields=["quantity_received"])
        record_stock_movement(
            product=purchase_item.product, warehouse=warehouse, quantity=quantity_received,
            movement_type=StockMovement.MovementType.PURCHASE,
            reference=f"PO-{purchase_item.purchase_id:04d}", user=user,
        )
        purchase = purchase_item.purchase
        items = purchase.items.all()
        if all(i.quantity_received >= i.quantity_ordered for i in items):
            purchase.status = Purchase.Status.RECEIVED
        elif any(i.quantity_received > 0 for i in items):
            purchase.status = Purchase.Status.PARTIALLY_RECEIVED
        purchase.save(update_fields=["status"])
    return purchase_item


class SaleNotReady(Exception):
    """Raised when a sale cannot be confirmed (no items, or not enough stock)."""


def confirm_sale(*, sale, user=None):
    """
    Confirm a draft sale and take the goods out of the warehouse.
    Refuses (changing nothing) if the sale has no items or the warehouse
    does not hold enough of any product.
    """
    from inventory.models import Sale

    with transaction.atomic():
        items = list(sale.items.select_related("product"))
        if not items:
            raise SaleNotReady("this sale has no items yet")

        needed = {}
        for item in items:
            needed.setdefault(item.product, 0)
            needed[item.product] += item.quantity

        shortages = []
        for product, qty in needed.items():
            record = (Inventory.objects.select_for_update()
                      .filter(product=product, warehouse=sale.warehouse).first())
            available = record.available_quantity if record else 0
            if qty > available:
                shortages.append(f"{product.name}: needs {qty}, only {available} available at {sale.warehouse}")
        if shortages:
            raise SaleNotReady("not enough stock - " + "; ".join(shortages))

        for item in items:
            record_stock_movement(
                product=item.product, warehouse=sale.warehouse, quantity=-item.quantity,
                movement_type=StockMovement.MovementType.SALE, reference=f"S-{sale.id:04d}", user=user,
            )
        sale.status = Sale.Status.CONFIRMED
        sale.refresh_balance_cache()
        sale.save(update_fields=["status"])
    return sale


def apply_reconciliation(*, reconciliation, user=None):
    variance = reconciliation.variance
    if variance == 0:
        reconciliation.status = reconciliation.Status.APPROVED
        reconciliation.approved_by = user
        reconciliation.save(update_fields=["status", "approved_by"])
        return reconciliation

    movement_type = (
        StockMovement.MovementType.ADJUSTMENT_IN if variance > 0 else StockMovement.MovementType.ADJUSTMENT_OUT
    )
    with transaction.atomic():
        record_stock_movement(
            product=reconciliation.product, warehouse=reconciliation.warehouse, quantity=variance,
            movement_type=movement_type, reference=f"RECON-{reconciliation.id}", user=user,
            notes=reconciliation.reason,
        )
        reconciliation.status = reconciliation.Status.APPROVED
        reconciliation.approved_by = user
        reconciliation.save(update_fields=["status", "approved_by"])
    return reconciliation


def trigger_low_stock_alert(inventory):
    pass
