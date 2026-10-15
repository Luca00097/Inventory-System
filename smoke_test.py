import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "inventory_project.settings")
django.setup()

from inventory.models import Customer, Product, Purchase, PurchaseItem, Sale, SaleItem, Supplier, Warehouse, Payment, Reconciliation
from inventory.services.stock import receive_purchase_item, confirm_sale, transfer_stock, apply_reconciliation

supplier = Supplier.objects.create(name="Mouka Foam Ltd", payment_terms="14-day", lead_time_days=7)
main_wh = Warehouse.objects.create(name="Main Warehouse Test", location="Benin City")
east_wh = Warehouse.objects.create(name="Warehouse East Test", location="Lagos")

product = Product.objects.create(
    sku="SMOKETEST-01", name="Smoke Test Mattress", category="Mattress",
    unit="PIECE", cost_price=45000, selling_price=60000, reorder_level=10, target_stock=100,
    supplier=supplier,
)

po = Purchase.objects.create(supplier=supplier, status="ORDERED")
item = PurchaseItem.objects.create(purchase=po, product=product, quantity_ordered=50, unit_cost=45000)
receive_purchase_item(purchase_item=item, quantity_received=45, warehouse=main_wh)
po.refresh_from_db()
inv = product.inventory_records.get(warehouse=main_wh)
assert inv.quantity == 45, f"expected 45, got {inv.quantity}"
assert po.status == "PARTIALLY_RECEIVED", po.status
print(f"[OK] Purchase receiving: {inv.quantity} units, PO status={po.status}")

transfer_stock(product=product, from_warehouse=main_wh, to_warehouse=east_wh, quantity=20)
main_inv = product.inventory_records.get(warehouse=main_wh)
east_inv = product.inventory_records.get(warehouse=east_wh)
assert main_inv.quantity == 25 and east_inv.quantity == 20
print(f"[OK] Transfer: Main={main_inv.quantity}, East={east_inv.quantity}")

customer = Customer.objects.create(name="Test Distributor", credit_limit=2000000, payment_terms_days=14)
sale = Sale.objects.create(customer=customer, warehouse=main_wh)
SaleItem.objects.create(sale=sale, product=product, quantity=5, unit_price=60000)
confirm_sale(sale=sale)
main_inv.refresh_from_db()
assert main_inv.quantity == 20 and sale.balance_due == 300000
print(f"[OK] Sale confirmed: stock={main_inv.quantity}, balance due={sale.balance_due}")

Payment.objects.create(customer=customer, sale=sale, amount=100000, method="BANK_TRANSFER")
sale.refresh_balance_cache()
assert sale.balance_due == 200000
print(f"[OK] Payment recorded: balance due now {sale.balance_due}")

recon = Reconciliation.objects.create(
    product=product, warehouse=main_wh, system_quantity=20, physical_quantity=18, reason="2 units damaged"
)
apply_reconciliation(reconciliation=recon)
main_inv.refresh_from_db()
assert main_inv.quantity == 18 and recon.status == "APPROVED"
print(f"[OK] Reconciliation applied: Main stock now {main_inv.quantity}")

movement_count = product.movements.count()
print(f"[OK] Stock movements recorded for full lifecycle: {movement_count}")

print("\nALL CHECKS PASSED")
