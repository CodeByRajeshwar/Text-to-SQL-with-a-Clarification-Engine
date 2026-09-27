"""
verify_db.py
------------
Standalone health check for the database. Run this on its own (no API key
needed) to find out exactly what's wrong before touching main.py at all:

    python -m scripts.verify_db

(run from the repo root, so the app package is importable)

It checks:
  1. Does the file exist at the expected path?
  2. What is its file size? (a healthy company.db is ~350 KB; a broken,
     silently auto-created one is 0 bytes or just a few KB)
  3. What tables does it actually contain?
  4. How many rows are in each expected table?

Imports DB_PATH from app.config rather than recomputing it, so this always
checks the exact same file main.py/api.py would actually use -- including
respecting a DB_PATH override in your .env.
"""

from pathlib import Path

from app.config import DB_PATH

EXPECTED_TABLES = ["customers", "products", "orders", "order_items", "payments"]


def main() -> None:
    import sqlite3

    db_path = Path(DB_PATH)
    print(f"Looking for database at:\n  {db_path}\n")

    if not db_path.exists():
        print("PROBLEM: This file does not exist at all.")
        print("Fix: make sure data/company.db is present, or check DB_PATH in .env.")
        raise SystemExit(1)

    size_bytes = db_path.stat().st_size
    print(f"File size: {size_bytes:,} bytes")

    if size_bytes < 10_000:
        print("\nPROBLEM: This file is suspiciously small.")
        print("A healthy company.db with sample data is roughly 350 KB.")
        print("A file this small is almost certainly an EMPTY database that")
        print("sqlite3 silently auto-created because it couldn't find the real")
        print("one at this path on some earlier run.")
        raise SystemExit(1)

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    actual_tables = [row[0] for row in cur.fetchall()]

    print(f"\nTables found: {actual_tables if actual_tables else '(none)'}")

    missing = [t for t in EXPECTED_TABLES if t not in actual_tables]
    if missing:
        print(f"\nPROBLEM: missing expected table(s): {missing}")
        conn.close()
        raise SystemExit(1)

    print("\nRow counts:")
    all_good = True
    for table in EXPECTED_TABLES:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  {table}: {count} rows")
        if count == 0:
            all_good = False

    conn.close()

    if all_good:
        print("\nDatabase looks healthy. main.py should work correctly.")
    else:
        print("\nPROBLEM: some tables exist but are empty.")


if __name__ == "__main__":
    main()
