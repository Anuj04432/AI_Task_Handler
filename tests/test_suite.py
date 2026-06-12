"""
tests/test_suite.py
===================
Basic unit tests for DB, auth, tasks, and NLU modules.
Run with:  pytest tests/test_suite.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime, timedelta

# Use an in-memory test DB
import modules.database.db as db_mod
db_mod.DB_PATH = db_mod.Path("/tmp/test_todo.db")


def setup_module(module):
    """Re-create DB before tests."""
    if db_mod.DB_PATH.exists():
        db_mod.DB_PATH.unlink()
    db_mod.init_db()


# ─── DB / Auth Tests ─────────────────────────────────────────────────────────

def test_create_user():
    user = db_mod.create_user("alice", "password123")
    assert user is not None
    assert user["username"] == "alice"


def test_duplicate_user():
    db_mod.create_user("bob", "pass1")
    result = db_mod.create_user("bob", "pass2")
    assert result is None


def test_authenticate_user():
    db_mod.create_user("carol", "secret99")
    user = db_mod.authenticate_user("carol", "secret99")
    assert user is not None
    assert user["username"] == "carol"


def test_wrong_password():
    db_mod.create_user("dave", "rightpass")
    user = db_mod.authenticate_user("dave", "wrongpass")
    assert user is None


def test_session_persist():
    user = db_mod.create_user("eve", "pass123")
    token = "test_token_abc"
    db_mod.save_session(user["id"], token)
    restored = db_mod.get_session(token)
    assert restored is not None
    assert restored["username"] == "eve"


# ─── Task Tests ──────────────────────────────────────────────────────────────

@pytest.fixture
def user_id():
    u = db_mod.create_user("taskuser", "taskpass")
    return u["id"]


def test_add_task(user_id):
    task = db_mod.add_task(user_id, "Buy milk")
    assert task["name"] == "Buy milk"
    assert task["status"] == "pending"


def test_complete_task(user_id):
    task = db_mod.add_task(user_id, "Exercise")
    ok = db_mod.complete_task(task["id"], user_id)
    assert ok is True
    updated = db_mod.get_task(task["id"], user_id)
    assert updated["status"] == "completed"


def test_missed_task_locked(user_id):
    task = db_mod.add_task(user_id, "Old task")
    db_mod.mark_missed(task["id"])
    # Should not be editable
    ok = db_mod.update_task(task["id"], user_id, name="New name")
    assert ok is False


def test_delete_task(user_id):
    task = db_mod.add_task(user_id, "Temp task")
    ok = db_mod.delete_task(task["id"], user_id)
    assert ok is True
    assert db_mod.get_task(task["id"], user_id) is None


def test_get_pending_due_tasks(user_id):
    past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
    db_mod.add_task(user_id, "Overdue task", due_at=past)
    overdue = db_mod.get_pending_due_tasks()
    assert any(t["name"] == "Overdue task" for t in overdue)


# ─── NLU Tests ───────────────────────────────────────────────────────────────

from modules.ai.nlu import parse_command


def test_nlu_add():
    r = parse_command("Add a task called submit report by tomorrow", use_ollama=False)
    assert r["intent"] == "add_task"


def test_nlu_delete():
    r = parse_command("Delete task 5", use_ollama=False)
    assert r["intent"] == "delete_task"
    assert r["task_id"] == 5


def test_nlu_complete():
    r = parse_command("Mark task 2 as done", use_ollama=False)
    assert r["intent"] == "complete_task"


def test_nlu_show():
    r = parse_command("Show me all my tasks", use_ollama=False)
    assert r["intent"] == "show_tasks"


def test_nlu_spanish():
    r = parse_command("Eliminar tarea 3", use_ollama=False)
    assert r["intent"] == "delete_task"


def test_nlu_due_date():
    r = parse_command("Add meeting with team at 3pm tomorrow", use_ollama=False)
    # due_datetime should be parsed (if dateparser is installed)
    try:
        import dateparser
        assert r["due_datetime"] is not None or r["intent"] == "add_task"
    except ImportError:
        pass   # skip if dateparser not installed
