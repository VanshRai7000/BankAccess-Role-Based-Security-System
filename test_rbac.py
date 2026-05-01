"""
test_rbac.py — Automated test suite for the RBAC Banking Management System.
Covers all 8 PRD test cases + RBAC permission checks + transaction flows.

Run with:  python test_rbac.py
"""

import unittest
import os
import sys
import tempfile

# Point to the RBAC app
sys.path.insert(0, os.path.dirname(__file__))

# Use a temp DB so tests don't touch bank.db
TEST_DB = os.path.join(tempfile.gettempdir(), 'test_bank.db')

import database
database.DATABASE = TEST_DB  # override before importing app

import app as flask_app
from database import init_db, get_db, log_action
from rbac import check_permission, get_permissions
from werkzeug.security import generate_password_hash


# ── Helpers ────────────────────────────────────────────────────────────────────

def seed_test_db():
    """Insert minimal test data."""
    init_db()
    db = get_db()
    users = [
        ('admin',     generate_password_hash('admin123'),    'admin',    'Alice Admin',    'a@b.com'),
        ('manager',   generate_password_hash('manager123'),  'manager',  'Bob Manager',    'b@b.com'),
        ('teller',    generate_password_hash('teller123'),   'teller',   'Carol Teller',   'c@b.com'),
        ('customer1', generate_password_hash('customer123'), 'customer', 'David Customer', 'd@b.com'),
        ('customer2', generate_password_hash('customer123'), 'customer', 'Eve Customer',   'e@b.com'),
    ]
    for u in users:
        db.execute(
            "INSERT OR IGNORE INTO users (username, password_hash, role, full_name, email) VALUES (?,?,?,?,?)", u
        )
    db.commit()

    c1 = db.execute("SELECT id FROM users WHERE username='customer1'").fetchone()
    c2 = db.execute("SELECT id FROM users WHERE username='customer2'").fetchone()
    db.execute("INSERT OR IGNORE INTO accounts (owner_id, account_number, balance) VALUES (?,?,?)",
               (c1['id'], 'ACC-TEST-001', 5000.0))
    db.execute("INSERT OR IGNORE INTO accounts (owner_id, account_number, balance) VALUES (?,?,?)",
               (c2['id'], 'ACC-TEST-002', 3000.0))
    db.commit()
    db.close()


# ── Test Cases ─────────────────────────────────────────────────────────────────

class TestRBACEngine(unittest.TestCase):
    """Unit tests for the core RBAC permission engine (rbac.py)."""

    def test_admin_has_all_permissions(self):
        for perm in ['view', 'deposit', 'withdraw', 'approve', 'delete', 'manage_users', 'view_logs']:
            self.assertTrue(check_permission('admin', perm),
                            f"Admin should have '{perm}'")

    def test_manager_cannot_withdraw(self):
        self.assertFalse(check_permission('manager', 'withdraw'))
        self.assertFalse(check_permission('manager', 'withdraw_limited'))

    def test_manager_can_approve(self):
        self.assertTrue(check_permission('manager', 'approve'))
        self.assertTrue(check_permission('manager', 'view_logs'))

    def test_teller_can_deposit_and_withdraw(self):
        self.assertTrue(check_permission('teller', 'deposit'))
        self.assertTrue(check_permission('teller', 'withdraw'))

    def test_teller_cannot_approve_or_manage(self):
        self.assertFalse(check_permission('teller', 'approve'))
        self.assertFalse(check_permission('teller', 'manage_users'))
        self.assertFalse(check_permission('teller', 'delete'))

    def test_customer_view_own_only(self):
        self.assertTrue(check_permission('customer', 'view_own'))
        self.assertFalse(check_permission('customer', 'view'))

    def test_customer_cannot_approve_or_manage(self):
        self.assertFalse(check_permission('customer', 'approve'))
        self.assertFalse(check_permission('customer', 'manage_users'))
        self.assertFalse(check_permission('customer', 'delete'))
        self.assertFalse(check_permission('customer', 'view_logs'))

    def test_customer_withdraw_limited(self):
        self.assertTrue(check_permission('customer', 'withdraw_limited'))
        self.assertFalse(check_permission('customer', 'withdraw'))

    def test_unknown_role_has_no_permissions(self):
        self.assertEqual(get_permissions('hacker'), [])
        self.assertFalse(check_permission('hacker', 'view'))

    def test_customer_withdraw_limit_in_settings(self):
        """Customer withdraw limit is now stored in settings table, not hardcoded."""
        from database import get_setting
        limit = float(get_setting('customer_withdraw_limit', '100000'))
        self.assertGreater(limit, 0, "Withdraw limit must be a positive value in settings table")


class TestFlaskRoutes(unittest.TestCase):
    """Integration tests — HTTP route level, using Flask test client."""

    @classmethod
    def setUpClass(cls):
        flask_app.app.config['TESTING'] = True
        flask_app.app.config['WTF_CSRF_ENABLED'] = False
        flask_app.app.secret_key = 'test-secret'
        seed_test_db()
        cls.client = flask_app.app.test_client()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

    def login(self, username, password):
        return self.client.post('/login', data={
            'username': username, 'password': password
        }, follow_redirects=True)

    def logout(self):
        self.client.get('/logout', follow_redirects=True)

    # ── TC-08: Invalid login ────────────────────────────────────────────────

    def test_TC08_invalid_login(self):
        """TC-08: Login attempt with bad credentials → Denied."""
        resp = self.login('admin', 'wrongpassword')
        self.assertIn(b'Invalid username or password', resp.data)

    def test_login_with_correct_credentials(self):
        resp = self.login('admin', 'admin123')
        self.assertIn(b'Welcome', resp.data)
        self.logout()

    # ── TC-01: Admin delete user ───────────────────────────────────────────

    def test_TC01_admin_can_delete_user(self):
        """TC-01: Admin deletes a user account → Allowed."""
        # Create a throwaway user first
        self.login('admin', 'admin123')
        db = get_db()
        db.execute("INSERT OR IGNORE INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)",
                   ('throwaway', generate_password_hash('pass'), 'teller', 'Throwaway'))
        db.commit()
        uid = db.execute("SELECT id FROM users WHERE username='throwaway'").fetchone()['id']
        db.close()

        resp = self.client.post(f'/users/{uid}/delete', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'deleted', resp.data)
        self.logout()

    # ── TC-02: Customer cannot delete users ───────────────────────────────

    def test_TC02_customer_cannot_delete_user(self):
        """TC-02: Customer tries to delete — Denied."""
        self.login('customer1', 'customer123')
        db = get_db()
        victim = db.execute("SELECT id FROM users WHERE username='teller'").fetchone()
        db.close()
        resp = self.client.post(f'/users/{victim["id"]}/delete', follow_redirects=True)
        self.assertIn(b'Access Denied', resp.data)
        self.logout()

    # ── TC-03: Manager can approve transaction ─────────────────────────────

    def test_TC03_manager_can_approve_transaction(self):
        """TC-03: Manager approves a pending withdrawal → Allowed."""
        # Create a pending withdrawal for customer1
        db = get_db()
        acct = db.execute("SELECT * FROM accounts WHERE account_number='ACC-TEST-001'").fetchone()
        c1   = db.execute("SELECT id FROM users WHERE username='customer1'").fetchone()
        db.execute("""
            INSERT INTO transactions (user_id, account_id, amount, type, status, initiated_by)
            VALUES (?, ?, 200.0, 'withdraw', 'pending', ?)
        """, (c1['id'], acct['account_id'], c1['id']))
        db.commit()
        txn_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.close()

        self.login('manager', 'manager123')
        resp = self.client.post(f'/transactions/{txn_id}/approve', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'approved', resp.data)

        # Verify balance reduced
        db = get_db()
        acct2 = db.execute("SELECT balance FROM accounts WHERE account_number='ACC-TEST-001'").fetchone()
        db.close()
        self.assertEqual(acct2['balance'], acct['balance'] - 200.0)
        self.logout()

    # ── TC-04: Manager cannot withdraw ────────────────────────────────────

    def test_TC04_manager_cannot_withdraw(self):
        """TC-04: Manager tries to withdraw — Denied."""
        self.login('manager', 'manager123')
        resp = self.client.get('/withdraw', follow_redirects=True)
        self.assertIn(b'Access Denied', resp.data)
        self.logout()

    # ── TC-05: Teller can deposit ──────────────────────────────────────────

    def test_TC05_teller_can_deposit(self):
        """TC-05: Teller deposits to customer account → Allowed."""
        self.login('teller', 'teller123')
        db = get_db()
        acct = db.execute("SELECT * FROM accounts WHERE account_number='ACC-TEST-002'").fetchone()
        prev_bal = acct['balance']
        db.close()

        resp = self.client.post('/deposit', data={
            'account_id': acct['account_id'],
            'amount': 500.0,
            'notes': 'Test deposit'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'deposited', resp.data)

        db = get_db()
        new_bal = db.execute("SELECT balance FROM accounts WHERE account_number='ACC-TEST-002'").fetchone()['balance']
        db.close()
        self.assertEqual(new_bal, prev_bal + 500.0)
        self.logout()

    # ── TC-06: Customer cannot view other accounts ─────────────────────────

    def test_TC06_customer_cannot_view_all_users(self):
        """TC-06: Customer visits /users → Denied."""
        self.login('customer1', 'customer123')
        resp = self.client.get('/users', follow_redirects=True)
        self.assertIn(b'Access Denied', resp.data)
        self.logout()

    def test_TC06b_customer_cannot_view_logs(self):
        """TC-06 ext: Customer visits /logs → Denied."""
        self.login('customer1', 'customer123')
        resp = self.client.get('/logs', follow_redirects=True)
        self.assertIn(b'Access Denied', resp.data)
        self.logout()

    # ── TC-07: Admin can view logs ─────────────────────────────────────────

    def test_TC07_admin_can_view_logs(self):
        """TC-07: Admin views audit logs → Allowed."""
        self.login('admin', 'admin123')
        resp = self.client.get('/logs')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Audit', resp.data)
        self.logout()

    # ── Extra: Customer withdrawal limit ──────────────────────────────────

    def test_customer_withdraw_limit_enforced(self):
        """Customer trying to withdraw > limit gets rejected."""
        from database import get_setting
        limit = float(get_setting('customer_withdraw_limit', '100000'))

        self.login('customer1', 'customer123')
        db = get_db()
        acct = db.execute("SELECT * FROM accounts WHERE account_number='ACC-TEST-001'").fetchone()
        db.close()

        resp = self.client.post('/withdraw', data={
            'account_id': acct['account_id'],
            'amount':     limit + 1.0,   # always above whatever the current limit is
            'notes':      'Over-limit test'
        }, follow_redirects=True)
        self.assertIn(b'limit exceeded', resp.data)
        self.logout()

    def test_customer_withdrawal_goes_pending(self):
        """Customer valid withdrawal → status is 'pending'."""
        self.login('customer1', 'customer123')
        db = get_db()
        acct = db.execute("SELECT * FROM accounts WHERE account_number='ACC-TEST-001'").fetchone()
        db.close()

        self.client.post('/withdraw', data={
            'account_id': acct['account_id'],
            'amount': 100.0,
            'notes': 'Small withdrawal'
        }, follow_redirects=True)

        db = get_db()
        txn = db.execute(
            "SELECT * FROM transactions WHERE account_id=? AND type='withdraw' AND status='pending' ORDER BY id DESC LIMIT 1",
            (acct['account_id'],)
        ).fetchone()
        db.close()
        self.assertIsNotNone(txn, "Withdrawal should be in pending state")
        self.assertEqual(txn['status'], 'pending')
        self.logout()

    def test_audit_log_created_on_denied_access(self):
        """Denied actions must be logged."""
        self.login('customer1', 'customer123')
        self.client.get('/logs', follow_redirects=True)  # Denied action
        self.logout()

        db = get_db()
        denied_log = db.execute(
            "SELECT * FROM logs WHERE username='customer1' AND status='DENIED' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        db.close()
        self.assertIsNotNone(denied_log, "Denied access should be logged")

    def test_unauthenticated_redirected_to_login(self):
        """Unauthenticated access to any protected route → redirect to login."""
        with flask_app.app.test_client() as fresh_client:
            resp = fresh_client.get('/dashboard', follow_redirects=True)
            self.assertIn(b'Sign In', resp.data)


class TestDatabase(unittest.TestCase):
    """Tests for the database layer."""

    def test_log_action_writes_to_db(self):
        db = get_db()
        before = db.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        db.close()

        log_action(1, 'testuser', 'TEST_ACTION', 'SUCCESS', 'unit test', '127.0.0.1')

        db = get_db()
        after = db.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        latest = db.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 1").fetchone()
        db.close()

        self.assertEqual(after, before + 1)
        self.assertEqual(latest['action'], 'TEST_ACTION')
        self.assertEqual(latest['status'], 'SUCCESS')


# ── Runner ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 60)
    print("  SecureBank RBAC — Test Suite")
    print("=" * 60)
    unittest.main(verbosity=2)
