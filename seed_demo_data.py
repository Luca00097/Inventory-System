import os
import django
from datetime import timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "inventory_project.settings")
django.setup()

from django.utils import timezone

from inventory.models import (
    Customer, Inventory, Product, Purchase, PurchaseItem, Reconciliation,
    Sale, SaleItem, StockMovement, Supplier, Warehouse, Payment,
)
from inventory.services.stock import receive_purchase_item, confirm_sale, transfer_stock

print("Clearing existing demo data...")
for model in [Payment, StockMovement, SaleItem, Sale, PurchaseItem, Purchase,
              Reconciliation, Inventory, Customer, Product, Supplier, Warehouse]:
    model.objects.all().delete()

print("Creating warehouses...")
main_wh = Warehouse.objects.create(name="Main Warehouse", location="Benin City", manager="Uncle Tunde")
east_wh = Warehouse.objects.create(name="Warehouse East", location="Lagos", manager="Chidi")
west_wh = Warehouse.objects.create(name="Warehouse West", location="Ibadan", manager="Bisi")

print("Creating suppliers...")
mouka = Supplier.objects.create(
    name="Mouka Foam Nigeria Ltd", contact_person="Mr. Adeyemi", phone="0803xxxxxxx",
    email="sales@mouka.example", payment_terms="14-day", lead_time_days=7,
)
golden_penny = Supplier.objects.create(
    name="Golden Penny Distribution", contact_person="Mrs. Okafor", phone="0805xxxxxxx",
    email="orders@goldenpenny.example", payment_terms="7-day", lead_time_days=3,
)

print("Creating products...")
mouka_q = Product.objects.create(sku="MOUKA-Q-01", name="Mouka Queen Mattress", category="Mattress",
                        unit="PIECE", cost_price=45000, selling_price=60000,
                        reorder_level=10, target_stock=100, supplier=mouka)
mouka_k = Product.objects.create(sku="MOUKA-K-01", name="Mouka King Mattress", category="Mattress",
                        unit="PIECE", cost_price=55000, selling_price=72000,
                        reorder_level=8, target_stock=80, supplier=mouka)
mouka_s = Product.objects.create(sku="MOUKA-S-01", name="Mouka Single Mattress", category="Mattress",
                        unit="PIECE", cost_price=30000, selling_price=40000,
                        reorder_level=15, target_stock=120, supplier=mouka)
gp_flour = Product.objects.create(sku="GP-FLOUR-50", name="Golden Penny Flour 50kg", category="Food",
                        unit="BAG", cost_price=32000, selling_price=35500,
                        reorder_level=50, target_stock=400, supplier=golden_penny)
gp_semo = Product.objects.create(sku="GP-SEMO-50", name="Golden Penny Semovita 50kg", category="Food",
                        unit="BAG", cost_price=30000, selling_price=33500,
                        reorder_level=50, target_stock=350, supplier=golden_penny)
gp_pasta = Product.objects.create(sku="GP-PASTA-CT", name="Golden Penny Pasta (Carton)", category="Food",
                        unit="CARTON", cost_price=8500, selling_price=9800,
                        reorder_level=40, target_stock=300, supplier=golden_penny)

print("Creating customers...")
distributor_b = Customer.objects.create(
    name="Distributor B (Ring Road)", contact_person="Alhaji Musa", phone="0806xxxxxxx",
    credit_limit=2000000, payment_terms_days=14,
)
retailer_c = Customer.objects.create(
    name="Retailer C (New Benin Market)", contact_person="Mama Chioma", phone="0807xxxxxxx",
    credit_limit=500000, payment_terms_days=7,
)
cash_customer = Customer.objects.create(
    name="Walk-in / Cash Customers", payment_terms_days=0, credit_limit=0,
)

print("Receiving stock at Main Warehouse...")
def stock_up(product, warehouse, qty, unit_cost, supplier):
    po = Purchase.objects.create(supplier=supplier, status="ORDERED")
    item = PurchaseItem.objects.create(purchase=po, product=product, quantity_ordered=qty, unit_cost=unit_cost)
    receive_purchase_item(purchase_item=item, quantity_received=qty, warehouse=warehouse)
    return po

stock_up(mouka_q, main_wh, 60, 45000, mouka)
stock_up(mouka_k, main_wh, 40, 55000, mouka)
stock_up(mouka_s, main_wh, 90, 30000, mouka)
stock_up(gp_flour, main_wh, 300, 32000, golden_penny)
stock_up(gp_semo, main_wh, 250, 30000, golden_penny)
stock_up(gp_pasta, main_wh, 200, 8500, golden_penny)

print("Distributing stock to East and West warehouses...")
transfer_stock(product=mouka_q, from_warehouse=main_wh, to_warehouse=east_wh, quantity=20)
transfer_stock(product=gp_flour, from_warehouse=main_wh, to_warehouse=east_wh, quantity=80)
transfer_stock(product=gp_semo, from_warehouse=main_wh, to_warehouse=west_wh, quantity=60)

print("Creating a PENDING purchase...")
pending_po = Purchase.objects.create(
    supplier=mouka, status="ORDERED",
    expected_delivery=timezone.now().date() + timedelta(days=6),
    notes="Restocking king-size ahead of festive season",
)
PurchaseItem.objects.create(purchase=pending_po, product=mouka_k, quantity_ordered=30, unit_cost=55000)

print("Selling stock to create a LOW-STOCK situation and outstanding balances...")
sale1 = Sale.objects.create(customer=distributor_b, warehouse=main_wh,
                             due_date=timezone.now().date() + timedelta(days=14))
SaleItem.objects.create(sale=sale1, product=mouka_k, quantity=35, unit_price=72000)
confirm_sale(sale=sale1)
Payment.objects.create(customer=distributor_b, sale=sale1, amount=1200000, method="BANK_TRANSFER")
sale1.refresh_balance_cache()

sale2 = Sale.objects.create(customer=retailer_c, warehouse=main_wh,
                             due_date=timezone.now().date() + timedelta(days=7))
SaleItem.objects.create(sale=sale2, product=gp_flour, quantity=25, unit_price=35500)
SaleItem.objects.create(sale=sale2, product=gp_pasta, quantity=15, unit_price=9800)
confirm_sale(sale=sale2)
sale2.refresh_balance_cache()

sale3 = Sale.objects.create(customer=cash_customer, warehouse=main_wh)
SaleItem.objects.create(sale=sale3, product=mouka_s, quantity=10, unit_price=40000)
confirm_sale(sale=sale3)
Payment.objects.create(customer=cash_customer, sale=sale3, amount=sale3.total_amount, method="CASH")
sale3.refresh_balance_cache()

print("Creating a pending stock reconciliation...")
Reconciliation.objects.create(
    product=gp_flour, warehouse=main_wh,
    system_quantity=gp_flour.inventory_records.get(warehouse=main_wh).quantity,
    physical_quantity=gp_flour.inventory_records.get(warehouse=main_wh).quantity - 12,
    reason="12 bags short at physical count — awaiting investigation",
    status="PENDING",
)

print("\nDone. Demo data summary:")
print(f"  Products: {Product.objects.count()}")
print(f"  Suppliers: {Supplier.objects.count()}")
print(f"  Warehouses: {Warehouse.objects.count()}")
print(f"  Customers: {Customer.objects.count()}")
print(f"  Purchases: {Purchase.objects.count()} (1 still pending/ordered)")
print(f"  Sales: {Sale.objects.count()}")
mouka_k_main = mouka_k.inventory_records.get(warehouse=main_wh)
print(f"  Mouka King @ Main Warehouse: {mouka_k_main.quantity} units (reorder level {mouka_k.reorder_level}) -> LOW STOCK: {mouka_k_main.is_low_stock}")
print(f"  Pending reconciliation: 1 (Golden Penny Flour @ Main)")
print(f"  Outstanding balance — Retailer C: {sale2.balance_due}")
print(f"  Outstanding balance — Distributor B: {sale1.balance_due}")

# ---- Demo staff logins (DEMO ONLY - do not keep these on a real system) ----
from django.contrib.auth.models import Group, User
for username, role in (("demo_store", "Storekeeper"), ("demo_sales", "Sales")):
    user, created = User.objects.get_or_create(username=username)
    if created:
        user.set_password("demo12345")
        user.save()
    user.groups.add(Group.objects.get(name=role))
print("\nDemo staff logins (password demo12345): demo_store (Storekeeper), demo_sales (Sales)")
print("Sign in at /users/login/. Delete these accounts before real use.")
