"""
customer_db.py
==============
Defines and seeds the PaperTrail Co. customer relational database.

Schema follows 2NF with three tables demonstrating every key type:

    users                — one row per registered customer
    customer_transactions — one row per order header (FK → users)
    transaction_items    — one row per line item   (composite FK → customer_transactions)

Key types used
--------------
  Primary key   : users.user_id, customer_transactions.transaction_id,
                  (transaction_items.transaction_id + transaction_items.product_sku)
  Identity key  : user_id and transaction_id — AUTOINCREMENT integers with no
                  business meaning; used solely as surrogate row identifiers
  Candidate keys: (user_id) and (email) in users — both uniquely identify a row
  Alternate key : email in users — unique, not chosen as the primary key
  Super key     : any superset of a candidate key, e.g. (user_id, email),
                  (user_id, full_name), (email, company)
  Foreign key   : customer_transactions.user_id → users.user_id
                  transaction_items.transaction_id → customer_transactions.transaction_id
  Composite key : (transaction_id, product_sku) in transaction_items — the
                  primary key spans two columns

Run from the project root to initialise and seed:
    python src/database/customer_db.py
"""

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.abspath(os.path.join(_here, "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from sqlalchemy import create_engine, text

DB_PATH = "db/papertrail_customers.db"
_db_url = f"sqlite:///{DB_PATH}"


def _get_engine():
    os.makedirs("db", exist_ok=True)
    return create_engine(_db_url, connect_args={"check_same_thread": False})


# ── DDL ───────────────────────────────────────────────────────────────────────

_DDL = """
-- ============================================================
--  TABLE 1: users
--  Primary key   : user_id  (INTEGER AUTOINCREMENT → identity key)
--  Alternate key : email    (UNIQUE → candidate key not chosen as PK)
--  Super keys    : (user_id), (email), (user_id, email),
--                  (user_id, full_name), (email, company), …
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    UNIQUE NOT NULL,
    full_name     TEXT    NOT NULL,
    company       TEXT    NOT NULL,
    customer_type TEXT    NOT NULL
);

-- ============================================================
--  TABLE 2: customer_transactions
--  Primary key  : transaction_id  (INTEGER AUTOINCREMENT → identity key)
--  Foreign key  : user_id → users(user_id)
--  Candidate key: only (transaction_id) — user_id is not unique
--                 (one user can have many transactions)
--  Super keys   : (transaction_id), (transaction_id, user_id), …
-- ============================================================
CREATE TABLE IF NOT EXISTS customer_transactions (
    transaction_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL,
    transaction_date TEXT    NOT NULL,
    status           TEXT    NOT NULL,
    total_amount     REAL    NOT NULL DEFAULT 0.0,
    event_name       TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- ============================================================
--  TABLE 3: transaction_items
--  Composite key : (transaction_id, product_sku) — PRIMARY KEY
--                  spans two columns (neither column alone is unique)
--  Candidate key : only (transaction_id, product_sku)
--  Foreign key   : transaction_id → customer_transactions(transaction_id)
--  Super keys    : (transaction_id, product_sku),
--                  (transaction_id, product_sku, quantity), …
-- ============================================================
CREATE TABLE IF NOT EXISTS transaction_items (
    transaction_id INTEGER NOT NULL,
    product_sku    TEXT    NOT NULL,
    product_name   TEXT    NOT NULL,
    quantity       INTEGER NOT NULL,
    unit_price     REAL    NOT NULL,
    PRIMARY KEY (transaction_id, product_sku),
    FOREIGN KEY (transaction_id)
        REFERENCES customer_transactions(transaction_id)
);
"""

# ── Seed data ─────────────────────────────────────────────────────────────────

_USERS = [
    # (email, full_name, company, customer_type)
    ("sarah.johnson@springfield.edu",  "Sarah Johnson",   "Springfield Elementary",  "School Admin"),
    ("m.chen@vividmedia.co",           "Michael Chen",    "Vivid Media Co.",          "Marketing Agency"),
    ("a.foster@hopefoundation.org",    "Amanda Foster",   "Hope Foundation",          "Non-profit Coordinator"),
    ("d.rodriguez@grandevents.com",    "David Rodriguez", "Grand Events LLC",         "Event Planner"),
    ("j.kim@acmecorp.com",             "Jennifer Kim",    "Acme Corporation",         "Corporate Buyer"),
    ("r.williams@oakridgehs.edu",      "Robert Williams", "Oakridge High School",     "School Admin"),
    ("l.thompson@pixelcraft.co",       "Lisa Thompson",   "Pixel Craft Studio",       "Marketing Agency"),
    ("j.martinez@greengala.org",       "James Martinez",  "Green Gala Society",       "Non-profit Coordinator"),
    ("e.davis@premierevents.co",       "Emily Davis",     "Premiere Events Co.",      "Event Planner"),
    ("t.anderson@globaltech.com",      "Thomas Anderson", "Global Tech Inc.",         "Corporate Buyer"),
]

# Transactions: (user_email, date, status, total_amount, event_name, items)
# items: [(sku, name, qty, unit_price), ...]
_TRANSACTIONS = [
    ("sarah.johnson@springfield.edu", "2026-01-10", "completed", 28.00, "Spring Festival", [
        ("A4-001", "A4 Paper",           200, 0.02),
        ("CP-002", "Construction Paper", 200, 0.08),
        ("PB-003", "Paper Party Bags",    50, 0.12),
    ]),
    ("sarah.johnson@springfield.edu", "2026-02-14", "completed", 14.50, "Science Fair", [
        ("NP-004", "Notepads",           50, 0.15),
        ("SN-005", "Sticky Notes",      100, 0.10),
    ]),
    ("m.chen@vividmedia.co", "2026-01-15", "completed", 215.00, "Product Launch", [
        ("FL-006", "Flyers",            1000, 0.15),
        ("PP-007", "Poster Paper 24x36",  20, 2.50),
        ("BR-008", "Banner Paper Roll",    5, 8.00),
    ]),
    ("m.chen@vividmedia.co", "2026-03-01", "completed", 90.00, "Brand Refresh", [
        ("FL-006", "Flyers",             500, 0.15),
        ("PF-009", "Presentation Folders", 30, 0.75),
    ]),
    ("a.foster@hopefoundation.org", "2026-01-20", "completed", 150.00, "Charity Gala", [
        ("IC-010", "Invitation Cards",   300, 0.25),
        ("EN-011", "Envelopes",          300, 0.10),
        ("TC-012", "Table Covers",        50, 0.80),
    ]),
    ("d.rodriguez@grandevents.com", "2026-01-25", "completed", 320.00, "Food Festival", [
        ("DC-013", "Disposable Cups",   2000, 0.05),
        ("PL-014", "Paper Plates",      2000, 0.06),
        ("PN-015", "Paper Napkins",     4000, 0.02),
    ]),
    ("j.kim@acmecorp.com", "2026-01-28", "completed", 465.00, "Quarterly Conference", [
        ("PF-009", "Presentation Folders", 100, 0.75),
        ("NP-004", "Notepads",             200, 0.15),
        ("SN-005", "Sticky Notes",         500, 0.10),
    ]),
    ("r.williams@oakridgehs.edu", "2026-02-05", "completed", 42.00, "Art Week", [
        ("CP-002", "Construction Paper", 300, 0.08),
        ("A4-001", "A4 Paper",           500, 0.02),
    ]),
    ("l.thompson@pixelcraft.co", "2026-02-10", "completed", 175.00, "Trade Show", [
        ("FL-006", "Flyers",             500, 0.15),
        ("PP-007", "Poster Paper 24x36",  30, 2.50),
        ("PF-009", "Presentation Folders", 50, 0.75),
    ]),
    ("j.martinez@greengala.org", "2026-02-20", "completed", 95.00, "Annual Gala", [
        ("IC-010", "Invitation Cards",   200, 0.25),
        ("EN-011", "Envelopes",          200, 0.10),
        ("TC-012", "Table Covers",        30, 0.80),
    ]),
    ("e.davis@premierevents.co", "2026-03-05", "completed", 280.00, "Corporate Dinner", [
        ("DC-013", "Disposable Cups",   1000, 0.05),
        ("PL-014", "Paper Plates",      1000, 0.06),
        ("TC-012", "Table Covers",        50, 0.80),
    ]),
    ("t.anderson@globaltech.com", "2026-03-10", "completed", 390.00, "Annual Summit", [
        ("PF-009", "Presentation Folders", 200, 0.75),
        ("NP-004", "Notepads",             300, 0.15),
        ("SN-005", "Sticky Notes",        1000, 0.10),
    ]),
]


def init_customer_db(engine=None) -> None:
    """Create tables (if not exist) and seed with 10 users and 12 completed transactions."""
    if engine is None:
        engine = _get_engine()

    with engine.begin() as conn:
        # Create all three tables
        for stmt in _DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))

        # Seed users — skip if already present (idempotent)
        existing = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
        if existing > 0:
            return

        # Build email → user_id map after insert
        for email, full_name, company, customer_type in _USERS:
            conn.execute(text(
                "INSERT INTO users (email, full_name, company, customer_type) "
                "VALUES (:email, :full_name, :company, :customer_type)"
            ), {"email": email, "full_name": full_name,
                "company": company, "customer_type": customer_type})

        email_to_id = {
            row[0]: row[1]
            for row in conn.execute(text("SELECT email, user_id FROM users")).fetchall()
        }

        for email, date, status, total, event, items in _TRANSACTIONS:
            uid = email_to_id[email]
            result = conn.execute(text(
                "INSERT INTO customer_transactions "
                "(user_id, transaction_date, status, total_amount, event_name) "
                "VALUES (:uid, :date, :status, :total, :event)"
            ), {"uid": uid, "date": date, "status": status, "total": total, "event": event})
            txn_id = result.lastrowid

            for sku, name, qty, price in items:
                conn.execute(text(
                    "INSERT INTO transaction_items "
                    "(transaction_id, product_sku, product_name, quantity, unit_price) "
                    "VALUES (:txn_id, :sku, :name, :qty, :price)"
                ), {"txn_id": txn_id, "sku": sku, "name": name, "qty": qty, "price": price})


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_users_with_completed_transactions(engine=None) -> list[dict]:
    """Return users who have at least one 'completed' transaction.

    Used to populate the email dropdown on the landing page.
    SQL uses a JOIN across users and customer_transactions (FK relationship),
    filtering on status = 'completed'.

    Returns list of dicts with keys: email, full_name, company, customer_type.
    """
    if engine is None:
        engine = _get_engine()

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT u.email, u.full_name, u.company, u.customer_type
            FROM users u
            JOIN customer_transactions ct ON u.user_id = ct.user_id
            WHERE ct.status = 'completed'
            ORDER BY u.full_name
        """)).fetchall()

    return [
        {"email": r[0], "full_name": r[1], "company": r[2], "customer_type": r[3]}
        for r in rows
    ]


def get_user_by_email(email: str, engine=None) -> dict | None:
    """Look up a single user by email (alternate key lookup).

    Demonstrates querying by the alternate key (email) rather than the
    primary key (user_id).
    """
    if engine is None:
        engine = _get_engine()

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT user_id, email, full_name, company, customer_type "
                 "FROM users WHERE email = :email"),
            {"email": email},
        ).fetchone()

    if row is None:
        return None
    return {
        "user_id": row[0], "email": row[1], "full_name": row[2],
        "company": row[3], "customer_type": row[4],
    }


# ── Standalone init ───────────────────────────────────────────────────────────

customer_engine = _get_engine()
init_customer_db(customer_engine)


if __name__ == "__main__":
    init_customer_db()
    users = get_users_with_completed_transactions()
    print(f"\nSeeded {len(users)} users with completed transactions:\n")
    for u in users:
        print(f"  {u['email']:<40}  {u['full_name']:<20}  {u['company']}")
    print()
