"""
init_db.py — Initializes database schema and seeds only runtime settings.
NO hardcoded user data. The first admin account is created via the /setup page.

Run once: python init_db.py
"""

from database import get_db, init_db, set_setting

DEFAULT_SETTINGS = [
    ('bank_name',                'SecureBank',  'Display name of the bank'),
    ('bank_tagline',             'Role-Based Access Control Banking System', 'Bank tagline shown on login'),
    ('customer_withdraw_limit',  '100000',      'Maximum withdrawal per transaction for customers (INR)'),
    ('require_approval_above',   '0',           'Customer withdrawals above this amount go to pending (0 = always pending)'),
    ('min_account_balance',      '0',           'Minimum balance a customer account must maintain (INR)'),
    ('max_deposit_per_txn',      '0',           'Maximum deposit per transaction (0 = unlimited)'),
    ('account_number_prefix',    'ACC',         'Prefix used when generating new account numbers'),
    ('default_account_type',     'savings',     'Default account type for new customer accounts'),
    ('txn_page_size',            '20',          'Number of transactions shown per page'),
    ('log_retention_count',      '200',         'Maximum number of audit log entries shown in the UI'),
    ('session_timeout_minutes',  '60',          'User session timeout in minutes'),
]


def seed():
    init_db()

    # Seed settings — skip keys that already have a custom value
    for key, value, description in DEFAULT_SETTINGS:
        conn = get_db()
        existing = conn.execute("SELECT key FROM settings WHERE key=?", (key,)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO settings (key, value, description) VALUES (?,?,?)",
                (key, value, description)
            )
            conn.commit()
        conn.close()

    # Check if any users exist
    db = get_db()
    user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    db.close()

    print("[OK] Database schema and settings initialized.")
    print(f"     Settings seeded: {len(DEFAULT_SETTINGS)} configurable values.")

    if user_count == 0:
        print("")
        print("  [!] No users found.")
        print("      Start the server and visit /setup to create the first admin account.")
    else:
        print(f"     Existing users: {user_count} — no changes made to user data.")


if __name__ == '__main__':
    seed()
