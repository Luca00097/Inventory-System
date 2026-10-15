# Manual test checklist: Inventory system

Tick each box as you go. Format: **do this** → *expected result*. If a result is different, write what you saw in the Notes column at the end and stop to check it before moving on.

Time needed: about 60 to 75 minutes for everything.

---

## Part A. Set up (clean start)

- [ ] Delete `db.sqlite3` if it exists.
- [ ] `venv\Scripts\activate`, then `pip install -r requirements.txt` → *installs without errors*.
- [ ] `python manage.py migrate` → *ends with `OK` lines, including `inventory.0003_view_balances`*.
- [ ] `python manage.py createsuperuser` → *you create the owner login (use a real password)*.
- [ ] `python manage.py shell -c "from django.contrib.auth.models import Group; print(list(Group.objects.values_list('name', flat=True)))"` → *shows Owner, Sales and Storekeeper (roles were created by migrate)*.
- [ ] `python manage.py runserver`, then open http://127.0.0.1:8000/users/login/ → *the sign-in page loads with the business name*.

## Part B. Load opening stock from a spreadsheet (fresh database)

- [ ] Sign in as the owner. Admin → Warehouses → add `Main Warehouse`, `Warehouse East`, `Warehouse West` (exact names).
- [ ] Admin → Inventory → **Import opening stock** → upload `opening-stock-with-mistakes.xlsx` → *"Nothing was imported" with 7 errors (rows 3 to 9). Check Inventory afterwards: still empty*.
- [ ] Upload `opening-stock-sample.xlsx` → *preview says 3,042 units on 28 lines and 12 new products. Nothing saved yet*.
- [ ] Click **Load this stock** → *message "Opening stock loaded: 3042 units across 27 lines, 12 new product(s) created"*.
- [ ] Upload the sample again → *refused with "already loaded" messages (stock cannot be doubled)*.
- [ ] Open Stock movements → *27 rows, all `Adjustment In`, reference `OPENING-STOCK`, your username on each; none can be edited or deleted*.
- [ ] Now reset to the known demo state: stop the server (Ctrl+C), then `python seed_demo_data.py` (it wipes products, stock and sales, but keeps your owner login) → *prints the summary and the two demo logins*. Restart the server.

## Part C. Sign-in and the owner dashboard

- [ ] Open `/users/` without being signed in → *you are sent to the sign-in page*.
- [ ] Sign in with a wrong password → *"That username and password did not match"*.
- [ ] Sign in as the owner → *you land on `/users/`, header shows your username and "Owner"*.
- [ ] Money cards → *Stock value ₦23,247,500 and Owed by customers ₦2,354,500 (2 customers)*.
- [ ] Stock cards → *Units on hand 855 (6 products), Low on stock 1, Waiting for delivery 1, Stock counts to review 1*.
- [ ] Tables → *Low on stock: Mouka King Mattress 5 (reorder at 8). Who owes you: Distributor B ₦1,320,000, Retailer C ₦1,034,500. Waiting for delivery: PO-0007 ₦1,650,000. Stock counts: Golden Penny Flour 195 vs 183, difference -12*.
- [ ] **Log out** → *back to the sign-in page; pressing Back does not show the dashboard*.
- [ ] `/admin/dashboard/` (old address) when signed in → *redirects to `/users/`*.

## Part D. Roles. Create four test people

Admin → Users → Add. For each, set a password, save, then tick the groups. Do **not** tick "Staff status" yourself.

| Username | Groups |
|---|---|
| `t_sales` | Sales |
| `t_store` | Storekeeper |
| `t_both` | Sales **and** Storekeeper |
| `t_none` | (no group) |

- [ ] After saving `t_sales`, open it again → *"Staff status" is ticked automatically*.
- [ ] `t_none` → *"Staff status" is NOT ticked*.

Sign in as each person (use a private window so you stay signed in as owner elsewhere), and check:

| Check | t_sales | t_store | t_both | t_none |
|---|---|---|---|---|
| Header role label | Sales | Storekeeper | **Sales and Storekeeper** | Staff |
| "Owed by customers" card + "Who owes you" table | **Visible** | Hidden | **Visible** | Hidden |
| "Stock value" card, ₦ totals on deliveries | Hidden | Hidden | Hidden | Hidden |
| Shortcuts: Record a sale / payment | Yes | No | Yes | none |
| Shortcuts: Receive / Move stock / Stock count | No | Yes | Yes | none |
| "Manage data" link in header | Yes | Yes | Yes | **No** |
| Products page works, shows no cost price | Yes | Yes | Yes | Yes |

- [ ] All columns match the table.
- [ ] `t_none` opens `/admin/` → *sent to the admin sign-in page; cannot get in*.
- [ ] As `t_sales`: Admin → Customers → *shows a "Current balance" column*. Admin → Products → *no Cost price column; opening a product shows no cost price field*.
- [ ] As `t_sales`: open `/admin/inventory/purchase/` → *"403 Forbidden"*.
- [ ] As `t_store`: Admin → Purchases → *list shows no "Total cost"; opening PO-0007 shows no unit cost*. Admin → Customers → *403*.

## Part E. Daily work, in the right role

**Product page (any signed-in user)**
- [ ] Products → search `flour` → *only Golden Penny Flour 50kg*. Search `zzzz` → *"No product matches"*.
- [ ] Open Golden Penny Flour 50kg → *In stock 275. Main 195, East 80, West 0, Total 275. History lists the +300 purchase (PO-0004), -80 and +80 transfer, and -25 sale (S-0002)*.
- [ ] As owner, same page → *also shows Cost price ₦32,000*. As `t_store` → *no cost price*.

**Receive a delivery (as `t_store`)**
- [ ] Admin → Purchases → tick PO-0007 → action *Receive goods* → pick Main Warehouse, leave quantity 30 → Receive → *PO-0007 becomes Received; Mouka King at Main goes 5 → 35; Low on stock card drops to 0*.

**Move stock (as `t_store`)**
- [ ] Admin → Inventory → tick Mouka Queen at Main (40) → action *Transfer* → Warehouse West, 5 → *Main 35, West 5. Two movements: Transfer Out and Transfer In*.
- [ ] Try transferring more than is available → *refused with "Only N available"*.

**Sell on credit (as `t_sales`)**
- [ ] Admin → Sales → Add → customer Distributor B, warehouse Main Warehouse → add **three different products** → *the unit price fills in by itself when you pick each product*. Save (status Draft).
- [ ] *"Created by" shows `t_sales` when you reopen it*.
- [ ] Tick it → action *Confirm selected sales* → *status Confirmed; each product's stock dropped on its product page*.
- [ ] Sale row → **Download PDF** → *an invoice opens with every line, subtotal, paid and balance due*.
- [ ] Admin → Payments → Add → that sale, a partial amount → *Balance due on the sale drops; Distributor B's balance on the dashboard rises or falls accordingly; "Recorded by" shows `t_sales`*.

**Refuse overselling (as `t_sales`)**
- [ ] Create a sale for 999 of Mouka Single Mattress at Main → Confirm → *refused: "not enough stock - … needs 999, only N available". Status stays Draft; stock unchanged*.
- [ ] Create a sale with no items → Confirm → *refused: "this sale has no items yet"*.

**Stock count (as `t_store`, then owner)**
- [ ] As `t_store`: Admin → Reconciliations → Add → *the form has no "System quantity" or "Status" field*. Pick Golden Penny Semovita at Warehouse West, physical quantity 56, reason "4 bags torn" → Save → *the record shows System 60, Physical 56, Difference -4, Pending*.
- [ ] As `t_store`: tick it → *there is no "Approve" action available*.
- [ ] As owner: tick it → *Approve selected reconciliations* → *status Approved; Semovita at West becomes 56; an Adjustment Out of 4 appears with reference RECON-n*. Open the record → *fields are locked*.

## Part F. Things that must be refused (safety)

Do each as the person named. *Expected: blocked, and nothing changes.*

- [ ] `t_sales` tries `/admin/inventory/inventory/import/` → *sent back, no import page*.
- [ ] `t_store` tries `/admin/inventory/inventory/import/` → *sent back (import is owner only)*.
- [ ] `t_sales` opens a stock line and tries the Transfer URL → *refused*.
- [ ] `t_sales` tries to receive goods on a purchase → *403, no stock change*.
- [ ] `t_both` tries to approve a stock count → *action not offered*.
- [ ] Nobody except the owner can edit or delete Stock movements → *all fields read-only, no delete button*.
- [ ] Inventory quantity cannot be typed over directly → *fields are read-only; only workflows change stock*.

## Part G. Data integrity spot checks (owner)

- [ ] Pick any product. Add up its history quantities on the product page → *equals "In stock" total*.
- [ ] Dashboard "Units on hand" → *equals the sum of every product's In stock on the Products page*.
- [ ] Dashboard "Owed by customers" → *equals the sum of every unconfirmed balance across the Sales list*.
- [ ] Cancel nothing, delete nothing: after all the tests above, Stock movements shows *every change with a reference and a user*.

## Part H. Before real use (live system)

- [ ] **Delete** `demo_store` and `demo_sales` (and your `t_` test users) in Admin → Users.
- [ ] Do **not** run `seed_demo_data.py` on the live system (it wipes data). Remove the file from the deployed copy if you can.
- [ ] Railway variables set: `DEBUG=False`, a long random `SECRET_KEY`, `ALLOWED_HOSTS` = your domain, `DATABASE_URL` from the Postgres service.
- [ ] After deploying, run once: `railway run python manage.py migrate` → *roles are created on the live database*. Because roles are only created if missing, an existing live database needs `railway run python manage.py setup_roles --reset` once to pick up new permissions (this resets all three roles to the defaults).
- [ ] Visit the live `/users/login/` → *fonts load, sign-in works, wrong password is refused*.
- [ ] Make the real owner a superuser; give each staff member only their role.
- [ ] Open the live dashboard on a **phone** → *cards stack in one column; tables scroll sideways inside their panels*.
- [ ] Load real opening stock once (Part B), plus customers' old balances as sales.
- [ ] Backups: confirm the Postgres service has backups, and do one test restore.
- [ ] Choose who is responsible for correct data entry on his side.

---

## Notes (write what you saw when it did not match)

| Step | What I expected | What I saw |
|---|---|---|
|  |  |  |
|  |  |  |
|  |  |  |
