"""
db_schema.py
------------
Holds two things that get injected into every LLM prompt:

1. SCHEMA_DESCRIPTION - a human-written description of the tables, columns,
   relationships, and known "gotchas" (e.g. pre-tax totals, partial payments).
   This is more reliable than dumping raw `PRAGMA table_info` output, because
   it captures *meaning*, not just structure.

2. FEW_SHOT_EXAMPLES - worked (question -> SQL) pairs. Few-shot examples are
   the single highest-leverage thing you can do to stop an LLM from
   hallucinating table/column names or writing subtly wrong JOINs, because
   they show the exact table/column vocabulary in context rather than
   describing it abstractly.
"""

SCHEMA_DESCRIPTION = """
DATABASE: company.db (SQLite)
Today's date for relative date calculations ("this month", "last year"): 2026-08-31

TABLE customers
  customer_id   INTEGER PRIMARY KEY
  first_name    TEXT
  last_name     TEXT
  email         TEXT (unique)
  signup_date   DATE
  region        TEXT   -- one of: North, South, East, West
  customer_tier TEXT   -- one of: standard, premium, enterprise

TABLE products
  product_id    INTEGER PRIMARY KEY
  product_name  TEXT
  category      TEXT   -- one of: Electronics, Office Supplies, Software, Home & Kitchen
  unit_price    NUMERIC  -- CURRENT catalog price (may differ from price paid historically)

TABLE orders
  order_id      INTEGER PRIMARY KEY
  customer_id   INTEGER  -- FK -> customers.customer_id
  order_date    DATE
  status        TEXT   -- one of: pending, completed, cancelled, refunded
  total_amount  NUMERIC  -- pre-tax order total, BEFORE refunds. Not always equal
                          -- to SUM(payments.amount) for that order.

TABLE order_items
  order_item_id INTEGER PRIMARY KEY
  order_id      INTEGER  -- FK -> orders.order_id
  product_id    INTEGER  -- FK -> products.product_id
  quantity      INTEGER
  unit_price    NUMERIC  -- price AT TIME OF PURCHASE (may differ from products.unit_price today)

TABLE payments
  payment_id    INTEGER PRIMARY KEY
  order_id      INTEGER  -- FK -> orders.order_id (an order MAY have multiple payment rows -
                          -- partial/installment payments are allowed)
  payment_date  DATE
  amount        NUMERIC  -- amount of THIS payment (may be partial, not the full order total)
  method        TEXT   -- one of: credit_card, paypal, bank_transfer, gift_card
  status        TEXT   -- one of: succeeded, failed, refunded

RELATIONSHIPS
  customers (1) -> (many) orders
  orders    (1) -> (many) order_items
  orders    (1) -> (many) payments

IMPORTANT SEMANTIC NOTES (read carefully - these drive ambiguity detection)
  - "revenue" / "sales" is ambiguous: it could mean SUM(orders.total_amount)
    (gross, pre-refund) or net cash actually collected, i.e.
    SUM(payments.amount WHERE status='succeeded') - SUM(payments.amount WHERE status='refunded').
  - "best" / "top" customers is ambiguous: highest total spend vs. highest
    order count vs. most recent activity are all different rankings here.
  - "customers" alone is ambiguous between ALL rows in customers (LEFT JOIN)
    vs. only customers who have placed an order (INNER JOIN).
  - Relative time windows ("recent", "last month", "this quarter") are
    ambiguous without a fixed definition - always confirm the exact date
    range rather than guessing.
"""

FEW_SHOT_EXAMPLES = [
    {
        "question": "How many customers do we have in the North region?",
        "sql": "SELECT COUNT(*) AS customer_count FROM customers WHERE region = 'North';",
    },
    {
        "question": "List the 5 most recent orders with the customer's name.",
        "sql": (
            "SELECT o.order_id, c.first_name, c.last_name, o.order_date, o.status, o.total_amount "
            "FROM orders o "
            "JOIN customers c ON c.customer_id = o.customer_id "
            "ORDER BY o.order_date DESC "
            "LIMIT 5;"
        ),
    },
    {
        "question": "What is the total gross order value for completed orders in 2025?",
        "sql": (
            "SELECT SUM(total_amount) AS gross_total "
            "FROM orders "
            "WHERE status = 'completed' AND order_date >= '2025-01-01' AND order_date < '2026-01-01';"
        ),
    },
    {
        "question": "Which products are in the Electronics category, cheapest first?",
        "sql": (
            "SELECT product_name, unit_price FROM products "
            "WHERE category = 'Electronics' ORDER BY unit_price ASC;"
        ),
    },
    {
        "question": "For each customer, how many orders have they placed, including customers with zero orders?",
        "sql": (
            "SELECT c.customer_id, c.first_name, c.last_name, COUNT(o.order_id) AS order_count "
            "FROM customers c "
            "LEFT JOIN orders o ON o.customer_id = c.customer_id "
            "GROUP BY c.customer_id "
            "ORDER BY order_count DESC;"
        ),
    },
]


def format_few_shot_block() -> str:
    """Render the few-shot examples as text to embed in a prompt."""
    lines = []
    for i, ex in enumerate(FEW_SHOT_EXAMPLES, 1):
        lines.append(f"Example {i}:")
        lines.append(f"Q: {ex['question']}")
        lines.append(f"SQL: {ex['sql']}")
        lines.append("")
    return "\n".join(lines)
