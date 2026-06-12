"""
database/db.py
==============
SQLite database layer. Handles all schema creation, user CRUD, and task CRUD.
Uses bcrypt for password hashing (no plaintext passwords ever stored).
"""

import sqlite3
import bcrypt
import os
from datetime import datetime
from pathlib import Path

# Resolve DB path relative to project root so it works regardless of CWD
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "todo.db"


def get_connection() -> sqlite3.Connection:
    """Return a thread-safe SQLite connection with row_factory set."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row          # rows accessible as dicts
    conn.execute("PRAGMA foreign_keys = ON") # enforce FK constraints
    return conn


def init_db() -> None:
    """
    Create tables if they don't exist.
    Schema:
        users  : id, username, password_hash, created_at
        tasks  : id, user_id (FK), name, created_at, due_at, status
        sessions: id, user_id (FK), token, created_at  — for persistence
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name       TEXT    NOT NULL,
            created_at TEXT    NOT NULL DEFAULT (datetime('now')),
            due_at     TEXT,                          -- ISO-8601 or NULL
            status     TEXT    NOT NULL DEFAULT 'pending'
                                CHECK(status IN ('pending','completed','missed'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token      TEXT    NOT NULL UNIQUE,
            created_at TEXT    NOT NULL DEFAULT (datetime('now'))
        );
    """)

    conn.commit()
    conn.close()


# ─── USER OPERATIONS ──────────────────────────────────────────────────────────

def create_user(username: str, password: str) -> dict | None:
    """
    Register a new user. Returns the user row on success, None if username taken.
    Password is hashed with bcrypt before storage.
    """
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username.strip().lower(), hashed)
        )
        conn.commit()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip().lower(),)
        ).fetchone()
        return dict(user) if user else None
    except sqlite3.IntegrityError:
        return None          # username already taken
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> dict | None:
    """
    Verify credentials. Returns user dict on success, None on failure.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username.strip().lower(),)
    ).fetchone()
    conn.close()

    if row and bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
        return dict(row)
    return None


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ─── SESSION OPERATIONS ───────────────────────────────────────────────────────

def save_session(user_id: int, token: str) -> None:
    """Persist a login token so the user stays logged in across browser restarts."""
    conn = get_connection()
    # Remove old sessions for this user first (single-session policy)
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.execute(
        "INSERT INTO sessions (user_id, token) VALUES (?, ?)", (user_id, token)
    )
    conn.commit()
    conn.close()


def get_session(token: str) -> dict | None:
    """Return user dict if the session token is valid, else None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
        (token,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_session(token: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()


# ─── TASK OPERATIONS ──────────────────────────────────────────────────────────

def add_task(user_id: int, name: str, due_at: str | None = None) -> dict:
    """Insert a new task and return it."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO tasks (user_id, name, due_at) VALUES (?, ?, ?)",
        (user_id, name.strip(), due_at)
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM tasks WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,)
    ).fetchone()
    conn.close()
    return dict(row)


def get_tasks(user_id: int) -> list[dict]:
    """Return all tasks for a user, most recent first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE user_id = ? ORDER BY id DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_task(task_id: int, user_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_task(task_id: int, user_id: int, name: str | None = None,
                due_at: str | None = None) -> bool:
    """
    Update mutable fields. Returns False if task is missed (locked) or not found.
    """
    task = get_task(task_id, user_id)
    if not task or task["status"] == "missed":
        return False   # missed tasks are non-editable
    conn = get_connection()
    if name:
        conn.execute("UPDATE tasks SET name=? WHERE id=?", (name.strip(), task_id))
    if due_at is not None:
        conn.execute("UPDATE tasks SET due_at=? WHERE id=?", (due_at, task_id))
    conn.commit()
    conn.close()
    return True


def complete_task(task_id: int, user_id: int) -> bool:
    """Mark a task completed. Returns False if already missed."""
    task = get_task(task_id, user_id)
    if not task or task["status"] == "missed":
        return False
    conn = get_connection()
    conn.execute(
        "UPDATE tasks SET status='completed' WHERE id=? AND user_id=?",
        (task_id, user_id)
    )
    conn.commit()
    conn.close()
    return True


def mark_missed(task_id: int) -> None:
    """Mark a task as missed (called by scheduler)."""
    conn = get_connection()
    conn.execute(
        "UPDATE tasks SET status='missed' WHERE id=? AND status='pending'",
        (task_id,)
    )
    conn.commit()
    conn.close()


def delete_task(task_id: int, user_id: int) -> bool:
    """Delete a task. Returns False if not found or missed."""
    task = get_task(task_id, user_id)
    if not task:
        return False
    conn = get_connection()
    conn.execute("DELETE FROM tasks WHERE id=? AND user_id=?", (task_id, user_id))
    conn.commit()
    conn.close()
    return True


def get_pending_due_tasks() -> list[dict]:
    """Return all pending tasks whose due_at has passed — used by scheduler."""
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE status='pending' AND due_at IS NOT NULL AND due_at <= ?",
        (now,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
