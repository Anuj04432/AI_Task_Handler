"""
tasks/task_manager.py
=====================
Business logic layer between the UI and the database.
Handles validation, locking rules, and status transitions.
"""

from datetime import datetime
from modules.database import db
from modules.voice import voice


# ─── Motivational message banks ──────────────────────────────────────────────

COMPLETION_MESSAGES = [
    "Excellent work! Consistency is the key to mastery.",
    "Task done! Every small win builds a great life.",
    "You crushed it! Discipline beats motivation every time.",
    "One more off the list! You're unstoppable.",
    "Well done! The secret of getting ahead is getting started — and you did!",
]

MISSED_MESSAGES = [
    "You missed this one. But champions use setbacks as setups for comebacks.",
    "Missed, not defeated. Reset, refocus, and go again.",
    "It slipped by — that's human. What matters is what you do next.",
    "A stumble is not a fall. Reflect, learn, and move forward.",
    "Even the best miss sometimes. The key is to never stop trying.",
]

_msg_counter = {"complete": 0, "missed": 0}


def _next_message(pool: list, counter_key: str) -> str:
    idx = _msg_counter[counter_key] % len(pool)
    _msg_counter[counter_key] += 1
    return pool[idx]


# ─── Task Manager ────────────────────────────────────────────────────────────

def add_task(user_id: int, name: str, due_at: str | None = None) -> dict:
    """
    Validate and add a task, then speak confirmation.
    Raises ValueError on bad input.
    """
    name = name.strip()
    if not name:
        raise ValueError("Task name cannot be empty.")

    if due_at:
        try:
            datetime.fromisoformat(due_at)          # validate format
        except ValueError:
            raise ValueError(f"Invalid due_at format: {due_at!r}. Use ISO-8601.")

    task = db.add_task(user_id, name, due_at)
    voice.announce("task_added")
    return task


def delete_task(task_id: int, user_id: int) -> bool:
    """Delete a task. Speaks result."""
    ok = db.delete_task(task_id, user_id)
    if ok:
        voice.announce("task_deleted")
    return ok


def complete_task(task_id: int, user_id: int) -> tuple[bool, str]:
    """
    Mark task complete. Returns (success, message).
    Speaks motivational message.
    """
    ok = db.complete_task(task_id, user_id)
    if not ok:
        task = db.get_task(task_id, user_id)
        if task and task["status"] == "missed":
            msg = voice.announce("task_locked")
            return False, msg
        return False, "Task not found or already completed."

    msg = _next_message(COMPLETION_MESSAGES, "complete")
    voice.announce(None, custom=msg)
    return True, msg


def update_task(task_id: int, user_id: int,
                name: str | None = None,
                due_at: str | None = None) -> tuple[bool, str]:
    """
    Update task name / due date. Missed tasks are locked.
    Returns (success, message).
    """
    task = db.get_task(task_id, user_id)
    if not task:
        return False, "Task not found."
    if task["status"] == "missed":
        voice.announce("task_locked")
        return False, "Missed tasks cannot be edited."

    ok = db.update_task(task_id, user_id, name=name, due_at=due_at)
    return (True, "Task updated.") if ok else (False, "Update failed.")


def get_tasks(user_id: int) -> list[dict]:
    """
    Return tasks, refreshing missed status for any overdue pending tasks first.
    """
    _auto_mark_missed()
    return db.get_tasks(user_id)


def _auto_mark_missed() -> None:
    """
    Check all pending tasks globally and mark overdue ones as missed.
    Called before every task listing so the UI always sees fresh statuses.
    """
    overdue = db.get_pending_due_tasks()
    for task in overdue:
        db.mark_missed(task["id"])
        # Motivational voice message (async, non-blocking via pyttsx3)
        msg = _next_message(MISSED_MESSAGES, "missed")
        voice.speak(msg)


def get_task_stats(user_id: int) -> dict:
    """Return counts by status for dashboard display."""
    tasks = db.get_tasks(user_id)
    stats = {"pending": 0, "completed": 0, "missed": 0, "total": len(tasks)}
    for t in tasks:
        stats[t["status"]] = stats.get(t["status"], 0) + 1
    return stats
