# 🏦 BankAccess — Role-Based Security System

A production-ready **Role-Based Access Control (RBAC)** banking management system built with Python and Flask. Every user action is evaluated against a strict role-permission matrix before any database operation is performed.

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Role & Permission Matrix](#-role--permission-matrix)
- [Project Structure](#-project-structure)
- [Getting Started](#-getting-started)
- [Usage Guide](#-usage-guide)
- [Dynamic Settings](#-dynamic-settings)
- [Running Tests](#-running-tests)
- [Tech Stack](#-tech-stack)
- [Security Notes](#-security-notes)

---

## 🎯 Overview

BankAccess demonstrates a real-world banking security model where four distinct roles (Admin, Manager, Teller, Customer) each have precisely scoped permissions. No hardcoded business logic — all banking rules (withdrawal limits, approval thresholds, page sizes) are stored in the database and configurable at runtime without redeployment.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **RBAC Engine** | Centralized permission matrix in `rbac.py` — every route enforces role checks |
| **4 User Roles** | Admin, Manager, Teller, Customer with distinct access levels |
| **First-Run Setup** | Secure `/setup` route locks itself after the first admin is created |
| **Dynamic Settings** | Business rules (limits, thresholds) stored in DB — no code changes needed |
| **Audit Logging** | Every action (login, deposit, denial, settings change) is recorded with timestamp and IP |
| **Quick-Select Login** | Login panel shows active users for fast testing — no passwords exposed |
| **Responsive UI** | Professional Black & White theme with mobile sidebar support |
| **Dev Reset Tool** | `reset_db.py` wipes and re-seeds the database for clean development cycles |
| **Pytest Suite** | Automated tests covering all permission rules across all four roles |

---

## 🔐 Role & Permission Matrix

| Permission | Admin | Manager | Teller | Customer |
|------------|:-----:|:-------:|:------:|:--------:|
| View own account | ✅ | ✅ | ✅ | ✅ |
| Deposit funds | ✅ | ❌ | ✅ | ✅ |
| Withdraw (full) | ✅ | ❌ | ✅ | ❌ |
| Withdraw (limited) | ✅ | ❌ | ❌ | ✅ |
| Approve transactions | ✅ | ✅ | ❌ | ❌ |
| View audit logs | ✅ | ✅ | ❌ | ❌ |
| Manage users | ✅ | ❌ | ❌ | ❌ |
| Manage settings | ✅ | ❌ | ❌ | ❌ |
| Delete records | ✅ | ❌ | ❌ | ❌ |

> **Principle of Least Privilege** — roles only receive the minimum permissions required for their function.

---

## 📁 Project Structure

```
BankAccess-Role-Based-Security-System/
│
├── app.py              # Flask application — all routes with RBAC decorators
├── database.py         # SQLite connection, schema, audit log helper, settings API
├── rbac.py             # Core permission engine — role → permission mapping
├── init_db.py          # Standalone DB initializer (schema + settings seed)
├── reset_db.py         # Dev tool — wipes and re-seeds bank.db
├── test_rbac.py        # Pytest suite — full permission matrix coverage
├── requirements.txt    # Python dependencies
│
├── templates/
│   ├── base.html                # Sidebar layout, nav, topbar
│   ├── login.html               # Split-panel login with quick-select
│   ├── setup.html               # First-run admin creation
│   ├── admin_dashboard.html     # Stats, logs, users, quick actions
│   ├── manager_dashboard.html   # Pending approvals, account overview
│   ├── teller_dashboard.html    # Customer accounts, recent transactions
│   ├── customer_dashboard.html  # Own balance and transaction history
│   ├── deposit.html             # Deposit form
│   ├── withdraw.html            # Withdrawal form
│   ├── transactions.html        # Approve/reject pending transactions
│   ├── manage_users.html        # User list and status toggle
│   ├── create_user.html         # New user creation form
│   ├── logs.html                # Audit log viewer with delete controls
│   └── settings.html            # Runtime business rule configuration
│
└── static/
    ├── css/style.css   # Professional B&W theme with CSS custom properties
    └── js/main.js      # Clock, quick-select autofill, mobile menu
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.9+
- pip

### 1. Clone the repository

```bash
git clone https://github.com/VanshRai7000/BankAccess-Role-Based-Security-System.git
cd BankAccess-Role-Based-Security-System
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the server

```bash
python app.py
```

The app runs at **http://127.0.0.1:5000**

### 4. First-run setup

On a fresh database, visit:

```
http://127.0.0.1:5000/setup
```

Create your **Admin** account. The `/setup` route automatically disables itself once any user exists.

### 5. Log in

```
http://127.0.0.1:5000/login
```

Click your username in the **Quick Select** panel, enter your password, and sign in.

---

## 📖 Usage Guide

### Admin
- Full system access
- Create and manage users (assign roles, activate/deactivate)
- Configure all business rules via **Settings**
- View and delete audit logs
- Approve/reject transactions

### Manager
- View all customer accounts and total bank balance
- Approve or reject pending transactions
- View audit logs

### Teller
- Deposit and withdraw funds for customers
- View customer account list and their own recent transactions

### Customer
- View their own account balance and transaction history
- Deposit or withdraw (subject to configured limits)
- Large withdrawals are automatically queued for manager approval

---

## ⚙️ Dynamic Settings

All banking business rules are stored in the `settings` table and editable at runtime via the **Admin → Settings** page:

| Key | Description | Default |
|-----|-------------|---------|
| `customer_withdraw_limit` | Max single withdrawal for customers | ₹100,000 |
| `require_approval_above` | Amounts above this need manager approval | ₹0 |
| `max_deposit_per_txn` | Max single deposit amount | ₹500,000 |
| `min_account_balance` | Minimum balance that must remain | ₹500 |
| `default_account_type` | Default type for new accounts | savings |
| `account_number_prefix` | Prefix for generated account numbers | ACC |
| `txn_page_size` | Transactions shown per page | 20 |
| `log_retention_count` | Max log entries to display | 500 |
| `bank_name` | Displayed bank name | SecureBank |

> Changes take effect **immediately** — no server restart required.

---

## 🧪 Running Tests

```bash
python -m pytest test_rbac.py -v
```

The test suite covers:
- Permission grants and denials for all 4 roles across all 9 permissions
- Edge cases (empty role, unknown role, unknown action)

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3, Flask 3.0.3 |
| **Database** | SQLite 3 (via Python stdlib `sqlite3`) |
| **Auth** | Werkzeug `generate_password_hash` / `check_password_hash` |
| **Sessions** | Flask server-side sessions |
| **Frontend** | Vanilla HTML5, CSS3 (CSS custom properties), Vanilla JS |
| **Fonts** | Inter (Google Fonts) |
| **Testing** | pytest |

---

## 🔒 Security Notes

| Concern | Implementation |
|---------|---------------|
| Password storage | Bcrypt-style hashing via Werkzeug (PBKDF2) |
| Session security | Server-side Flask sessions with secret key |
| Permission enforcement | Every route uses `@permission_required` decorator |
| Setup lockdown | `/setup` is disabled after the first user is created |
| Audit trail | Every action logged with user, role, status, and IP |
| SQL injection | All queries use parameterised placeholders (`?`) |

> ⚠️ **Production checklist:**
> - Set `SECRET_KEY` as an environment variable (`$env:SECRET_KEY="your-secret"`)
> - Replace SQLite with PostgreSQL for multi-user deployments
> - Run behind Gunicorn + Nginx, not the Flask dev server

---

## 🔄 Development Reset

To wipe all data and start fresh:

```bash
python reset_db.py
# Type 'yes' when prompted
# Then visit http://127.0.0.1:5000/setup
```

---

## 📄 License

This project is for educational and demonstration purposes.

---

<div align="center">
  Built with Flask · Secured with RBAC · Styled with ♟ Black & White
</div>
