# Inventory Management System — Django MVP

A working alternative to the Noloco/Airtable/Make.com stack, covering Products,
Suppliers, Warehouses, Inventory, Purchases, Sales & Credit, Stock Movements
(audit trail), Reconciliation, PDF invoices, and a branded login/dashboard.

## What's included

- `inventory/models.py` — all 12 tables.
- `inventory/services/stock.py` — business logic: `record_stock_movement()`,
  `transfer_stock()`, `receive_purchase_item()`, `confirm_sale()`,
  `apply_reconciliation()`.
- `inventory/admin.py` — the working CRUD dashboard, with real workflow
  buttons (Receive, Transfer, Confirm, Approve) wired to the service layer,
  not just raw field editing. Also handles invoice PDF downloads and branding.
- `inventory/invoices.py` — generates a PDF invoice per Sale (reportlab).
  Edit `COMPANY_NAME` / `COMPANY_ADDRESS` at the top before using for real.
- `inventory/static/inventory/auto_price.js` — auto-fills the unit price/cost
  field when you pick a product on a Sale or Purchase line item (still
  editable afterward — useful for discounts or negotiated prices). Works on
  rows already on the page and on rows added via "Add another".
- `inventory/templates/admin/` - dashboard page, branded login page, the Receive/Transfer
  intermediate forms, and the opening-stock import page.
- `inventory/static/inventory/theme.css` - the visual theme (palette, type, dashboard and import
  styles). It works by overriding Django admin's own CSS variables, so every admin page inherits
  it. IBM Plex Sans is bundled in `static/inventory/fonts/` (SIL Open Font License), so it works offline.
- `inventory/views.py` - the dashboard. It lives at `/users/` and adapts to the signed-in role: stock on hand, who
  owes you, low stock, deliveries waiting, stock counts to review, recent movements.
- `inventory/importers.py` - opening-stock import from Excel/CSV. In the admin go to
  Inventory -> **Import opening stock**: download the template, fill one row per product
  per warehouse, upload, check the preview, then confirm. Every row is validated first
  (all-or-nothing), new products can be created in the same file, stock is posted as
  `OPENING-STOCK` adjustments so the audit trail stays intact, and a second load for the
  same product and warehouse is blocked so stock can't be doubled.
- `smoke_test.py` — end-to-end test of the full lifecycle. Run after any
  model/service change to catch regressions.
- `seed_demo_data.py` — populates realistic demo data (Mouka mattresses,
  Golden Penny products) including a low-stock item, a pending purchase, a
  pending reconciliation, and customers with outstanding balances.

## Setup

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/admin/ and log in.

To load demo data:

```bash
python seed_demo_data.py
```

To verify everything still works after changes:

```bash
python smoke_test.py
```

## Sign-in and roles

Everyone signs in at **/users/login/** (the owner can still use /admin/ too) and lands on the
dashboard at **/users/**, which shows only what their role allows. **/users/products/** is a
searchable product list; each product page shows stock by warehouse and its full history.

| Role | Sees | Can do |
|---|---|---|
| Owner | Everything: stock value, cost prices, purchase totals, what customers owe | Everything, including importing opening stock and approving stock counts |
| Sales | Stock levels and **what customers owe**; no cost prices, no purchases | Record sales and payments, look up customers |
| Storekeeper | Stock levels; no money | Receive deliveries, move stock between warehouses, record stock counts |

**One person can hold several roles.** Tick more than one group on their user: they get the
union of the permissions (e.g. Sales + Storekeeper can sell and take payments, and also receive
and move stock, but still cannot see cost prices or approve counts). The header shows both roles.

Roles are Django groups, created automatically by `python manage.py migrate`. To give someone a
role: Admin -> Users -> open the person -> tick the group. They are made staff automatically.
Adjust a role in Admin -> Groups. Roles are only created if missing, so on a database that
already exists run `python manage.py setup_roles --reset` once to pick up new default
permissions (this resets all three roles to the defaults).

Permissions behind the roles:
- **view financials**: cost prices, stock value, purchase totals (owner only by default)
- **view balances**: what customers owe (Owner and Sales by default)
- **receive goods**, **transfer stock**, **import stock**, **approve stock count**: each action
  has its own permission, so any role can be given or denied it separately.

Safety rules built in: a sale cannot be confirmed for more than the warehouse holds (or with no
items); the system quantity on a stock count is read from the stock records, not typed; and
"created by" / "recorded by" are filled in automatically.

`seed_demo_data.py` also creates two demo logins (`demo_store`, `demo_sales`, password
`demo12345`). They exist for demos only: delete them before real use.

## Deployment (WSGI via Gunicorn)

This project is deployment-ready for Railway/Render-style hosts:
- `Procfile` tells the host to run `gunicorn inventory_project.wsgi`.
- `settings.py` reads `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, and
  `DATABASE_URL` from environment variables.
- WhiteNoise serves static files without needing a separate web server.

See prior conversation for the full Railway walkthrough (push to GitHub,
create a Railway project from the repo, add a Postgres database, set env
vars, run `migrate`/`createsuperuser`/`seed_demo_data.py` via `railway run`).

## What's not built yet

1. Automatic low-stock / overdue-payment email alerts — `trigger_low_stock_alert()`
   in `services/stock.py` is a stub.
2. Filtered reports beyond the dashboard (Inventory, Purchase, Movement,
   Variance, Accounts Receivable as standalone report views).
3. Auth/roles beyond Django's built-in permissions.
4. Automatic invoice emailing (currently manual download only).
