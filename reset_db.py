"""
reset_db.py — Wipes and recreates the database from scratch.
Deletes bank.db, recreates schema, and seeds default settings.
No user data is seeded — use /setup to create the first admin.

Usage:
    python reset_db.py
    python reset_db.py --confirm    (skip the confirmation prompt)
"""

import os
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), 'bank.db')


def reset(confirm=False):
    if not confirm:
        print("WARNING: This will permanently delete ALL data in bank.db.")
        print("         Users, accounts, transactions, and audit logs will be erased.")
        print("")
        ans = input("Type 'yes' to confirm: ").strip().lower()
        if ans != 'yes':
            print("Aborted — database not changed.")
            return

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"[OK] Deleted {DB_PATH}")
    else:
        print(f"[--] No existing DB found at {DB_PATH}")

    from init_db import seed
    seed()

    print("")
    print("Database has been reset.")
    print("Visit http://127.0.0.1:5000/setup to create the first admin account.")


if __name__ == '__main__':
    skip_prompt = '--confirm' in sys.argv
    reset(confirm=skip_prompt)
