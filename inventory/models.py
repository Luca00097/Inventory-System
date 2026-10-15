from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Supplier(TimeStampedModel):
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    payment_terms = models.CharField(max_length=100, blank=True)
    lead_time_days = models.PositiveIntegerField(default=7)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Warehouse(TimeStampedModel):
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    manager = models.CharField(max_length=255, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    class Unit(models.TextChoices):
        BAG = "BAG", "Bag"
        CARTON = "CARTON", "Carton"
        PIECE = "PIECE", "Piece"
        ROLL = "ROLL", "Roll"

    sku = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=20, choices=Unit.choices, default=Unit.PIECE)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    reorder_level = models.PositiveIntegerField(default=0)
    target_stock = models.PositiveIntegerField(default=0)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    active = models.BooleanField(default=True)

    class Meta:
        permissions = [
            ("view_financials", "Can see business money figures (cost prices, stock value, purchase totals)"),
        ]

    def __str__(self):
        return f"{self.sku} — {self.name}"

    @property
    def total_stock(self):
        return self.inventory_records.aggregate(total=models.Sum("quantity"))["total"] or 0


class Customer(TimeStampedModel):
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_terms_days = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        permissions = [
            ("view_balances", "Can see what customers owe"),
        ]

    def __str__(self):
        return self.name

    @property
    def current_balance(self):
        total = self.sales.aggregate(total=models.Sum("balance_due_cached"))["total"]
        return total or 0


class Inventory(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="inventory_records")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="inventory_records")
    quantity = models.IntegerField(default=0)
    reserved_quantity = models.IntegerField(default=0)

    class Meta:
        unique_together = ("product", "warehouse")
        verbose_name_plural = "Inventory"
        permissions = [
            ("transfer_stock", "Can move stock between warehouses"),
            ("import_stock", "Can load opening stock from a spreadsheet"),
        ]

    def __str__(self):
        return f"{self.product.sku} @ {self.warehouse.name}: {self.quantity}"

    @property
    def available_quantity(self):
        return self.quantity - self.reserved_quantity

    @property
    def is_low_stock(self):
        return self.available_quantity <= self.product.reorder_level


class Purchase(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ORDERED = "ORDERED", "Ordered"
        PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED", "Partially Received"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchases")
    purchase_date = models.DateField(default=timezone.now)
    expected_delivery = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        permissions = [
            ("receive_goods", "Can receive delivered goods against a purchase"),
        ]

    def __str__(self):
        return f"PO-{self.id:04d} — {self.supplier.name}" if self.id else "New Purchase"

    @property
    def total_cost(self):
        return self.items.aggregate(
            total=models.Sum(models.F("quantity_ordered") * models.F("unit_cost"))
        )["total"] or 0


class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="purchase_items")
    quantity_ordered = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    quantity_received = models.PositiveIntegerField(default=0, blank=True)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.product.sku} x{self.quantity_ordered}" if self.product_id else "unattached item"

    @property
    def total_cost(self):
        if self.quantity_ordered is None or self.unit_cost is None:
            return None
        return self.quantity_ordered * self.unit_cost

    @property
    def quantity_outstanding(self):
        if self.quantity_ordered is None:
            return None
        return self.quantity_ordered - (self.quantity_received or 0)


class Sale(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CONFIRMED = "CONFIRMED", "Confirmed"
        DISPATCHED = "DISPATCHED", "Dispatched"
        PAID = "PAID", "Paid"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Partially Paid"
        OVERDUE = "OVERDUE", "Overdue"
        CANCELLED = "CANCELLED", "Cancelled"

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="sales")
    sale_date = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)
    balance_due_cached = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)

    def __str__(self):
        return f"S-{self.id:04d} — {self.customer.name}" if self.id else "New Sale"

    @property
    def total_amount(self):
        return self.items.aggregate(
            total=models.Sum(models.F("quantity") * models.F("unit_price"))
        )["total"] or 0

    @property
    def amount_paid(self):
        return self.payments.aggregate(total=models.Sum("amount"))["total"] or 0

    @property
    def balance_due(self):
        return self.total_amount - self.amount_paid

    def refresh_balance_cache(self):
        self.balance_due_cached = self.balance_due
        self.save(update_fields=["balance_due_cached"])


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="sale_items")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.product.sku} x{self.quantity}" if self.product_id else "unattached item"

    @property
    def total_price(self):
        if self.quantity is None or self.unit_price is None:
            return None
        return self.quantity * self.unit_price


class Payment(TimeStampedModel):
    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer"
        POS = "POS", "POS"
        OTHER = "OTHER", "Other"

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="payments")
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.BANK_TRANSFER)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Payment {self.amount} — {self.customer.name}"


class StockMovement(models.Model):
    class MovementType(models.TextChoices):
        PURCHASE = "PURCHASE", "Purchase"
        SALE = "SALE", "Sale"
        DISPATCH = "DISPATCH", "Dispatch"
        TRANSFER_IN = "TRANSFER_IN", "Transfer In"
        TRANSFER_OUT = "TRANSFER_OUT", "Transfer Out"
        ADJUSTMENT_IN = "ADJUSTMENT_IN", "Adjustment In"
        ADJUSTMENT_OUT = "ADJUSTMENT_OUT", "Adjustment Out"
        RETURN = "RETURN", "Return"
        DAMAGE = "DAMAGE", "Damage"

    timestamp = models.DateTimeField(default=timezone.now)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity = models.IntegerField()
    reference = models.CharField(max_length=100, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.product.sku} {self.quantity:+d} {self.movement_type}"


class Reconciliation(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        INVESTIGATING = "INVESTIGATING", "Investigating"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    date = models.DateField(default=timezone.now)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="reconciliations")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="reconciliations")
    system_quantity = models.IntegerField()
    physical_quantity = models.IntegerField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        permissions = [
            ("approve_reconciliation", "Can approve a stock count and adjust stock to match it"),
        ]

    def __str__(self):
        return f"Recon {self.product.sku} @ {self.warehouse.name} ({self.date})"

    @property
    def variance(self):
        return self.physical_quantity - self.system_quantity
