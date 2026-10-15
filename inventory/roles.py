"""
Roles for the system, built on Django groups and permissions.

  Owner        everything, including the money figures
  Sales        record sales and payments, see what customers owe; no cost prices, no purchases
  Storekeeper  look up stock, receive deliveries, move stock, record stock counts; no money

The groups are created automatically after `migrate` (see apps.py). They are only
created if missing, so permissions the owner adjusts later are never overwritten.
To reset a role to the defaults below, run:  python manage.py setup_roles --reset
"""

from django.contrib.auth.models import Group, Permission

APP = "inventory"

ALL_INVENTORY = "__all__"

ROLE_PERMISSIONS = {
    "Owner": [ALL_INVENTORY, "auth.add_user", "auth.change_user", "auth.view_user"],
    "Sales": [
        "view_product", "view_inventory", "view_warehouse",
        "view_customer", "add_customer", "change_customer", "view_balances",
        "view_sale", "add_sale", "change_sale",
        "view_saleitem", "add_saleitem", "change_saleitem", "delete_saleitem",
        "view_payment", "add_payment",
    ],
    "Storekeeper": [
        "view_product", "view_inventory", "view_warehouse", "view_supplier",
        "view_purchase", "view_purchaseitem", "receive_goods",
        "transfer_stock",
        "view_stockmovement",
        "view_reconciliation", "add_reconciliation",
    ],
}

ROLE_NAMES = tuple(ROLE_PERMISSIONS)


def _resolve(entry):
    """Turn 'view_product' or 'auth.add_user' into a Permission object."""
    if "." in entry:
        app_label, codename = entry.split(".", 1)
    else:
        app_label, codename = APP, entry
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def ensure_roles(reset=False):
    """Create the role groups (and their permissions) if missing. Returns the names created or reset."""
    touched = []
    for name, entries in ROLE_PERMISSIONS.items():
        group, created = Group.objects.get_or_create(name=name)
        if not created and not reset:
            continue
        perms = []
        for entry in entries:
            if entry == ALL_INVENTORY:
                perms.extend(Permission.objects.filter(content_type__app_label=APP))
            else:
                perms.append(_resolve(entry))
        group.permissions.set(perms)
        touched.append(name)
    return touched


def user_role_label(user):
    """A short plain-English label for the header, e.g. 'Owner' or 'Storekeeper'."""
    if user.is_superuser:
        return "Owner"
    names = sorted(g.name for g in user.groups.all() if g.name in ROLE_NAMES)
    if names:
        return " and ".join(names)
    return "Staff"
