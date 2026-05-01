"""
Database layer — SQLite schema creation and helper utilities.
"""

import sqlite3
import os

DATABASE = os.path.join(os.path.dirname(__file__), 'bank.db')


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            key         TEXT PRIMARY KEY,
            value       TEXT NOT NULL,
            description TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            role          TEXT    NOT NULL CHECK(role IN ('admin','manager','teller','customer')),
            full_name     TEXT    DEFAULT '',
            email         TEXT    DEFAULT '',
            is_active     INTEGER DEFAULT 1,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS accounts (
            account_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id       INTEGER NOT NULL,
            account_number TEXT    UNIQUE NOT NULL,
            account_type   TEXT    DEFAULT 'savings',
            balance        REAL    DEFAULT 0.0,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            account_id   INTEGER,
            amount       REAL    NOT NULL,
            type         TEXT    NOT NULL CHECK(type IN ('deposit','withdraw')),
            status       TEXT    DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','completed')),
            initiated_by INTEGER,
            approved_by  INTEGER,
            notes        TEXT    DEFAULT '',
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id)      REFERENCES users(id),
            FOREIGN KEY (account_id)   REFERENCES accounts(account_id),
            FOREIGN KEY (initiated_by) REFERENCES users(id),
            FOREIGN KEY (approved_by)  REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            username   TEXT,
            action     TEXT NOT NULL,
            status     TEXT NOT NULL CHECK(status IN ('ALLOWED','DENIED','SUCCESS','FAILED')),
            details    TEXT DEFAULT '',
            ip_address TEXT DEFAULT '',
            timestamp  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


def get_setting(key: str, default: str = '') -> str:
    """Fetch a runtime-configurable setting from the DB."""
    try:
        conn = get_db()
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        conn.close()
        return row['value'] if row else default
    except Exception:
        return default


def set_setting(key: str, value: str) -> None:
    """Upsert a setting value."""
    conn = get_db()
    conn.execute("INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, value))
    conn.commit()
    conn.close()


def log_action(user_id, username, action, status, details='', ip=''):
    """Insert an audit log entry."""
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO logs (user_id, username, action, status, details, ip_address) VALUES (?,?,?,?,?,?)",
            (user_id, username, action, status, details, ip)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
