"""
app.py — Main Flask application for the RBAC Banking Management System.
Every route passes through the RBAC engine before any DB operation.
All business-rule constants are fetched from the `settings` table at runtime.
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os, random

from database import get_db, init_db, log_action, get_setting, set_setting
from rbac import check_permission, get_permissions

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    import warnings
    warnings.warn("SECRET_KEY env var not set — using insecure fallback. Set SECRET_KEY in production!")
    app.secret_key = 'rbac-bank-dev-fallback-key'

# ── Bootstrap DB on first run ─────────────────────────────────────────────────
with app.app_context():
    init_db()


@app.before_request
def check_first_run():
    """Redirect to /setup if no users exist (first-time deployment)."""
    if request.endpoint in ('setup', 'static', 'login', None):
        return None
    db = get_db()
    user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    db.close()
    if user_count == 0:
        return redirect(url_for('setup'))

# ── Helpers — runtime settings ────────────────────────────────────────────────

def s_float(key, default):
    try:
        return float(get_setting(key, str(default)))
    except (ValueError, TypeError):
        return float(default)


def s_int(key, default):
    try:
        return int(get_setting(key, str(default)))
    except (ValueError, TypeError):
        return int(default)

# ── Decorators ────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrap


def permission_required(action):
    def decorator(f):
        @wraps(f)
        def wrap(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            role = session.get('role')
            if not check_permission(role, action):
                log_action(session['user_id'], session['username'], action, 'DENIED',
                           f'Role "{role}" lacks permission for "{action}"',
                           request.remote_addr)
                flash(f'Access Denied: your role ({role}) cannot perform "{action}".', 'error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return wrap
    return decorator

# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('dashboard') if 'user_id' in session else url_for('login'))


@app.route('/setup', methods=['GET', 'POST'])
def setup():
    """First-run: create the initial admin account. Disabled once any user exists."""
    db = get_db()
    user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    db.close()
    if user_count > 0:
        flash('System is already configured. Please log in.', 'info')
        return redirect(url_for('login'))

    if request.method == 'POST':
        username         = request.form.get('username', '').strip()
        password         = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        full_name        = request.form.get('full_name', '').strip()
        email            = request.form.get('email', '').strip()

        if not username or not password:
            flash('Username and password are required.', 'error')
        elif password != confirm_password:
            flash('Passwords do not match.', 'error')
        elif len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
        else:
            db = get_db()
            db.execute(
                "INSERT INTO users (username, password_hash, role, full_name, email) VALUES (?,?,?,?,?)",
                (username, generate_password_hash(password), 'admin', full_name, email)
            )
            db.commit()
            db.close()
            log_action(None, username, 'SETUP', 'SUCCESS', 'First admin account created', request.remote_addr)
            flash(f'Admin account "{username}" created! Please sign in.', 'success')
            return redirect(url_for('login'))

    return render_template('setup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username=? AND is_active=1", (username,)
        ).fetchone()
        db.close()

        if user and check_password_hash(user['password_hash'], password):
            session.update({
                'user_id':   user['id'],
                'username':  user['username'],
                'role':      user['role'],
                'full_name': user['full_name'] or user['username'],
            })
            log_action(user['id'], user['username'], 'LOGIN', 'SUCCESS',
                       f'Logged in as {user["role"]}', request.remote_addr)
            flash(f'Welcome, {session["full_name"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            log_action(None, username, 'LOGIN', 'FAILED', 'Invalid credentials', request.remote_addr)
            flash('Invalid username or password.', 'error')

    # Fetch active users for the quick-select panel (username + role only — no passwords)
    db = get_db()
    active_users = db.execute(
        "SELECT username, role, full_name FROM users WHERE is_active=1 ORDER BY role, username"
    ).fetchall()
    db.close()

    return render_template('login.html', active_users=active_users)


@app.route('/logout')
@login_required
def logout():
    log_action(session['user_id'], session['username'], 'LOGOUT', 'SUCCESS', '', request.remote_addr)
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    role      = session['role']
    db        = get_db()
    page_size = s_int('txn_page_size', 20)

    if role == 'admin':
        stats = {
            'users_count':    db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            'accounts_count': db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0],
            'total_balance':  db.execute("SELECT COALESCE(SUM(balance),0) FROM accounts").fetchone()[0],
            'pending_txns':   db.execute("SELECT COUNT(*) FROM transactions WHERE status='pending'").fetchone()[0],
            'total_txns':     db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
            'denied_logs':    db.execute("SELECT COUNT(*) FROM logs WHERE status='DENIED'").fetchone()[0],
        }
        recent_logs = db.execute(
            "SELECT * FROM logs ORDER BY timestamp DESC LIMIT 8"
        ).fetchall()
        users = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        db.close()
        log_action(session['user_id'], session['username'], 'view', 'ALLOWED', 'Admin dashboard')
        return render_template('admin_dashboard.html', stats=stats, recent_logs=recent_logs, users=users)

    elif role == 'manager':
        pending = db.execute("""
            SELECT t.*, u.username, u.full_name, a.account_number, a.balance AS acc_balance
            FROM transactions t
            JOIN users u ON t.user_id = u.id
            LEFT JOIN accounts a ON t.account_id = a.account_id
            WHERE t.status = 'pending' ORDER BY t.created_at DESC
        """).fetchall()
        accounts = db.execute("""
            SELECT a.*, u.username, u.full_name
            FROM accounts a JOIN users u ON a.owner_id = u.id ORDER BY a.account_id
        """).fetchall()
        total = db.execute("SELECT COALESCE(SUM(balance),0) FROM accounts").fetchone()[0]
        db.close()
        log_action(session['user_id'], session['username'], 'view', 'ALLOWED', 'Manager dashboard')
        return render_template('manager_dashboard.html', pending=pending, accounts=accounts, total=total)

    elif role == 'teller':
        accounts = db.execute("""
            SELECT a.*, u.username, u.full_name
            FROM accounts a JOIN users u ON a.owner_id = u.id
            WHERE u.role = 'customer' ORDER BY a.account_id
        """).fetchall()
        recent_txns = db.execute(f"""
            SELECT t.*, u.username, a.account_number
            FROM transactions t
            JOIN users u ON t.user_id = u.id
            LEFT JOIN accounts a ON t.account_id = a.account_id
            WHERE t.initiated_by = ? ORDER BY t.created_at DESC LIMIT {page_size}
        """, (session['user_id'],)).fetchall()
        db.close()
        log_action(session['user_id'], session['username'], 'view', 'ALLOWED', 'Teller dashboard')
        return render_template('teller_dashboard.html', accounts=accounts, recent_txns=recent_txns)

    elif role == 'customer':
        account = db.execute(
            "SELECT * FROM accounts WHERE owner_id=?", (session['user_id'],)
        ).fetchone()
        txns = []
        if account:
            txns = db.execute(
                f"SELECT * FROM transactions WHERE account_id=? ORDER BY created_at DESC LIMIT {page_size}",
                (account['account_id'],)
            ).fetchall()
        db.close()
        withdraw_limit = s_float('customer_withdraw_limit', 100000)
        approval_above = s_float('require_approval_above', 0)
        log_action(session['user_id'], session['username'], 'view_own', 'ALLOWED', 'Customer dashboard')
        return render_template('customer_dashboard.html', account=account, txns=txns,
                               limit=withdraw_limit, approval_above=approval_above)

    db.close()
    return redirect(url_for('login'))

# ── Deposit ───────────────────────────────────────────────────────────────────

@app.route('/deposit', methods=['GET', 'POST'])
@login_required
@permission_required('deposit')
def deposit():
    db            = get_db()
    role          = session['role']
    max_deposit   = s_float('max_deposit_per_txn', 0)

    if role == 'customer':
        accounts = db.execute(
            "SELECT * FROM accounts WHERE owner_id=?", (session['user_id'],)
        ).fetchall()
    else:
        accounts = db.execute("""
            SELECT a.*, u.username, u.full_name
            FROM accounts a JOIN users u ON a.owner_id = u.id WHERE u.role='customer'
        """).fetchall()

    if request.method == 'POST':
        account_id = request.form.get('account_id', type=int)
        amount     = request.form.get('amount', 0, type=float)
        notes      = request.form.get('notes', '')
        error      = None

        if amount <= 0:
            error = 'Amount must be greater than 0.'
        elif max_deposit > 0 and amount > max_deposit:
            error = f'Maximum deposit per transaction is ₹{max_deposit:,.0f}.'
        else:
            acct = db.execute("SELECT * FROM accounts WHERE account_id=?", (account_id,)).fetchone()
            if not acct:
                error = 'Account not found.'
            elif role == 'customer' and acct['owner_id'] != session['user_id']:
                log_action(session['user_id'], session['username'], 'deposit', 'DENIED',
                           'Attempted deposit to another customer account', request.remote_addr)
                error = 'Access Denied: you can only deposit to your own account.'

        if not error:
            db.execute("UPDATE accounts SET balance=balance+? WHERE account_id=?", (amount, account_id))
            db.execute("""
                INSERT INTO transactions (user_id, account_id, amount, type, status, initiated_by, notes)
                VALUES (?,?,?,'deposit','completed',?,?)
            """, (acct['owner_id'], account_id, amount, session['user_id'], notes))
            db.commit()
            log_action(session['user_id'], session['username'], 'deposit', 'SUCCESS',
                       f'Deposited Rs.{amount:,.2f} to account {account_id}', request.remote_addr)
            flash(f'Rs.{amount:,.2f} deposited successfully!', 'success')
            db.close()
            return redirect(url_for('dashboard'))
        else:
            flash(error, 'error')

    db.close()
    return render_template('deposit.html', accounts=accounts, max_deposit=max_deposit)

# ── Withdraw ──────────────────────────────────────────────────────────────────

@app.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    role = session['role']

    if not (check_permission(role, 'withdraw') or check_permission(role, 'withdraw_limited')):
        log_action(session['user_id'], session['username'], 'withdraw', 'DENIED',
                   f'Role {role} lacks withdraw permission', request.remote_addr)
        flash('Access Denied: your role cannot perform withdrawals.', 'error')
        return redirect(url_for('dashboard'))

    # Fetch runtime settings
    withdraw_limit  = s_float('customer_withdraw_limit', 100000)
    approval_above  = s_float('require_approval_above', 0)
    min_balance     = s_float('min_account_balance', 0)

    db = get_db()
    if role == 'customer':
        accounts = db.execute(
            "SELECT * FROM accounts WHERE owner_id=?", (session['user_id'],)
        ).fetchall()
    else:
        accounts = db.execute("""
            SELECT a.*, u.username, u.full_name
            FROM accounts a JOIN users u ON a.owner_id = u.id WHERE u.role='customer'
        """).fetchall()

    if request.method == 'POST':
        account_id = request.form.get('account_id', type=int)
        amount     = request.form.get('amount', 0, type=float)
        notes      = request.form.get('notes', '')
        acct       = db.execute("SELECT * FROM accounts WHERE account_id=?", (account_id,)).fetchone()
        error      = None

        if amount <= 0:
            error = 'Amount must be greater than 0.'
        elif not acct:
            error = 'Account not found.'
        elif role == 'customer' and acct['owner_id'] != session['user_id']:
            log_action(session['user_id'], session['username'], 'withdraw', 'DENIED',
                       'Attempted withdrawal from another account', request.remote_addr)
            error = 'Access Denied: you can only withdraw from your own account.'
        elif role == 'customer' and amount > withdraw_limit:
            log_action(session['user_id'], session['username'], 'withdraw_limited', 'DENIED',
                       f'Exceeded limit: Rs.{amount} > Rs.{withdraw_limit}', request.remote_addr)
            error = f'Withdrawal limit exceeded. Max Rs.{withdraw_limit:,.0f} per transaction.'
        elif (acct['balance'] - amount) < min_balance:
            error = f'Insufficient funds. Minimum balance of Rs.{min_balance:,.0f} must be maintained.'

        if error:
            flash(error, 'error')
        else:
            # Determine if approval is needed (customer only, and amount above approval threshold)
            needs_approval = (role == 'customer') and (amount > approval_above)

            if needs_approval:
                db.execute("""
                    INSERT INTO transactions (user_id, account_id, amount, type, status, initiated_by, notes)
                    VALUES (?,?,?,'withdraw','pending',?,?)
                """, (acct['owner_id'], account_id, amount, session['user_id'], notes))
                db.commit()
                log_action(session['user_id'], session['username'], 'withdraw_limited', 'ALLOWED',
                           f'Withdrawal Rs.{amount:,.2f} submitted — pending approval', request.remote_addr)
                flash(f'Withdrawal of Rs.{amount:,.2f} submitted — pending manager approval.', 'info')
            else:
                db.execute("UPDATE accounts SET balance=balance-? WHERE account_id=?", (amount, account_id))
                db.execute("""
                    INSERT INTO transactions (user_id, account_id, amount, type, status, initiated_by, notes)
                    VALUES (?,?,?,'withdraw','completed',?,?)
                """, (acct['owner_id'], account_id, amount, session['user_id'], notes))
                db.commit()
                log_action(session['user_id'], session['username'], 'withdraw', 'SUCCESS',
                           f'Withdrew Rs.{amount:,.2f} from account {account_id}', request.remote_addr)
                flash(f'Rs.{amount:,.2f} withdrawn successfully!', 'success')
            db.close()
            return redirect(url_for('dashboard'))

    db.close()
    return render_template('withdraw.html', accounts=accounts,
                           limit=withdraw_limit if role == 'customer' else None,
                           approval_above=approval_above)

# ── Transactions ──────────────────────────────────────────────────────────────

@app.route('/transactions')
@login_required
@permission_required('approve')
def transactions():
    page_size = s_int('txn_page_size', 20)
    db        = get_db()
    pending   = db.execute("""
        SELECT t.*, u.username, u.full_name, a.account_number, a.balance AS acc_balance
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.account_id
        WHERE t.status='pending' ORDER BY t.created_at DESC
    """).fetchall()
    history = db.execute(f"""
        SELECT t.*, u.username, u.full_name, a.account_number
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.account_id
        WHERE t.status != 'pending' ORDER BY t.updated_at DESC LIMIT {page_size * 2}
    """).fetchall()
    db.close()
    log_action(session['user_id'], session['username'], 'approve', 'ALLOWED', 'Viewed pending transactions')
    return render_template('transactions.html', pending=pending, history=history)


@app.route('/transactions/<int:txn_id>/approve', methods=['POST'])
@login_required
@permission_required('approve')
def approve_txn(txn_id):
    db  = get_db()
    txn = db.execute("SELECT * FROM transactions WHERE id=? AND status='pending'", (txn_id,)).fetchone()
    if txn:
        db.execute("UPDATE accounts SET balance=balance-? WHERE account_id=?",
                   (txn['amount'], txn['account_id']))
        db.execute("""UPDATE transactions SET status='approved', approved_by=?,
                   updated_at=CURRENT_TIMESTAMP WHERE id=?""", (session['user_id'], txn_id))
        db.commit()
        log_action(session['user_id'], session['username'], 'approve', 'SUCCESS',
                   f'Approved txn #{txn_id} Rs.{txn["amount"]:,.2f}', request.remote_addr)
        flash(f'Transaction #{txn_id} approved.', 'success')
    else:
        flash('Transaction not found or already processed.', 'error')
    db.close()
    return redirect(url_for('transactions'))


@app.route('/transactions/<int:txn_id>/reject', methods=['POST'])
@login_required
@permission_required('approve')
def reject_txn(txn_id):
    db  = get_db()
    txn = db.execute("SELECT * FROM transactions WHERE id=? AND status='pending'", (txn_id,)).fetchone()
    if txn:
        db.execute("""UPDATE transactions SET status='rejected', approved_by=?,
                   updated_at=CURRENT_TIMESTAMP WHERE id=?""", (session['user_id'], txn_id))
        db.commit()
        log_action(session['user_id'], session['username'], 'approve', 'SUCCESS',
                   f'Rejected txn #{txn_id}', request.remote_addr)
        flash(f'Transaction #{txn_id} rejected.', 'info')
    else:
        flash('Transaction not found or already processed.', 'error')
    db.close()
    return redirect(url_for('transactions'))

# ── User Management ───────────────────────────────────────────────────────────

@app.route('/users')
@login_required
@permission_required('manage_users')
def manage_users():
    db    = get_db()
    users = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    db.close()
    log_action(session['user_id'], session['username'], 'manage_users', 'ALLOWED', 'Viewed user list')
    return render_template('manage_users.html', users=users)


@app.route('/users/create', methods=['GET', 'POST'])
@login_required
@permission_required('manage_users')
def create_user():
    # Fetch runtime defaults
    acc_prefix   = get_setting('account_number_prefix', 'ACC')
    default_type = get_setting('default_account_type', 'savings')

    if request.method == 'POST':
        username     = request.form.get('username', '').strip()
        password     = request.form.get('password', '')
        role         = request.form.get('role')
        full_name    = request.form.get('full_name', '').strip()
        email        = request.form.get('email', '').strip()
        account_type = request.form.get('account_type', default_type)
        opening_bal  = request.form.get('opening_balance', 0, type=float)

        if not username or not password or role not in ('admin', 'manager', 'teller', 'customer'):
            flash('All fields are required and role must be valid.', 'error')
            return render_template('create_user.html', default_type=default_type)

        db      = get_db()
        existing = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if existing:
            flash('Username already exists.', 'error')
            db.close()
            return render_template('create_user.html', default_type=default_type)

        db.execute(
            "INSERT INTO users (username, password_hash, role, full_name, email) VALUES (?,?,?,?,?)",
            (username, generate_password_hash(password), role, full_name, email)
        )

        if role == 'customer':
            user_id = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()['id']
            acc_no  = f"{acc_prefix}-{random.randint(1000, 9999)}-{account_type[:3].upper()}"
            db.execute(
                "INSERT INTO accounts (owner_id, account_number, balance, account_type) VALUES (?,?,?,?)",
                (user_id, acc_no, opening_bal, account_type)
            )

        db.commit()
        db.close()
        log_action(session['user_id'], session['username'], 'manage_users', 'SUCCESS',
                   f'Created user {username} ({role})', request.remote_addr)
        flash(f'User "{username}" created successfully!', 'success')
        return redirect(url_for('manage_users'))

    return render_template('create_user.html', default_type=default_type)


@app.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@permission_required('manage_users')
def toggle_user(user_id):
    if user_id == session['user_id']:
        flash('You cannot deactivate your own account.', 'error')
        return redirect(url_for('manage_users'))
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if user:
        new_status   = 0 if user['is_active'] else 1
        action_label = 'Activated' if new_status else 'Deactivated'
        db.execute("UPDATE users SET is_active=? WHERE id=?", (new_status, user_id))
        db.commit()
        log_action(session['user_id'], session['username'], 'manage_users', 'SUCCESS',
                   f'{action_label} user {user["username"]}', request.remote_addr)
        flash(f'User "{user["username"]}" {action_label.lower()}.', 'info')
    db.close()
    return redirect(url_for('manage_users'))


@app.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@permission_required('delete')
def delete_user(user_id):
    if user_id == session['user_id']:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('manage_users'))
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if user:
        db.execute("DELETE FROM users WHERE id=?", (user_id,))
        db.commit()
        log_action(session['user_id'], session['username'], 'delete', 'SUCCESS',
                   f'Deleted user {user["username"]}', request.remote_addr)
        flash(f'User "{user["username"]}" deleted.', 'success')
    db.close()
    return redirect(url_for('manage_users'))

# ── Audit Logs ────────────────────────────────────────────────────────────────

@app.route('/logs')
@login_required
@permission_required('view_logs')
def view_logs():
    retention   = s_int('log_retention_count', 200)
    db          = get_db()
    logs        = db.execute(
        f"SELECT * FROM logs ORDER BY timestamp DESC LIMIT {retention}"
    ).fetchall()
    total_count = db.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
    db.close()
    log_action(session['user_id'], session['username'], 'view_logs', 'ALLOWED', 'Viewed audit logs')
    return render_template('logs.html', logs=logs, total_count=total_count)


@app.route('/logs/<int:log_id>/delete', methods=['POST'])
@login_required
@permission_required('delete')
def delete_log(log_id):
    db = get_db()
    db.execute("DELETE FROM logs WHERE id=?", (log_id,))
    db.commit()
    db.close()
    log_action(session['user_id'], session['username'], 'delete', 'SUCCESS',
               f'Deleted log entry #{log_id}', request.remote_addr)
    flash(f'Log entry #{log_id} deleted.', 'info')
    return redirect(url_for('view_logs'))


@app.route('/logs/clear', methods=['POST'])
@login_required
@permission_required('delete')
def clear_logs():
    db    = get_db()
    count = db.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
    db.execute("DELETE FROM logs")
    db.commit()
    db.close()
    # Re-log the clear action after wiping
    log_action(session['user_id'], session['username'], 'delete', 'SUCCESS',
               f'Cleared all {count} log entries', request.remote_addr)
    flash(f'All {count} log entries have been cleared.', 'success')
    return redirect(url_for('view_logs'))

# ── Settings (Admin only) ─────────────────────────────────────────────────────

@app.route('/settings', methods=['GET', 'POST'])
@login_required
@permission_required('manage_settings')
def manage_settings():
    db       = get_db()
    settings = db.execute("SELECT * FROM settings ORDER BY key").fetchall()
    db.close()

    if request.method == 'POST':
        updated = 0
        db = get_db()
        all_keys = db.execute("SELECT key FROM settings").fetchall()
        db.close()
        for row in all_keys:
            key = row['key']
            new_val = request.form.get(f'setting_{key}', '').strip()
            if new_val != '':
                set_setting(key, new_val)
                updated += 1
        log_action(session['user_id'], session['username'], 'manage_settings', 'SUCCESS',
                   f'Updated {updated} settings', request.remote_addr)
        flash(f'{updated} settings updated successfully. Changes take effect immediately.', 'success')
        return redirect(url_for('manage_settings'))

    db       = get_db()
    settings = db.execute("SELECT * FROM settings ORDER BY key").fetchall()
    db.close()
    return render_template('settings.html', settings=settings)

# ── Context processor ─────────────────────────────────────────────────────────

@app.context_processor
def inject_globals():
    perms     = get_permissions(session.get('role', '')) if 'role' in session else []
    bank_name = get_setting('bank_name', 'SecureBank')
    return dict(user_permissions=perms, check_permission=check_permission,
                bank_name=bank_name, get_setting=get_setting)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
