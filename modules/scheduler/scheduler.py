"""
scheduler/scheduler.py
======================
Background scheduler that:
  1. Every 60 seconds, checks for overdue tasks and marks them missed.
  2. Speaks motivational messages for newly-missed tasks.
  3. Triggers reminder voice alerts N minutes before due time.

Uses APScheduler (lightweight, works offline).
The scheduler runs in a daemon thread so it doesn't block Streamlit.
"""

import logging
import threading
from datetime import datetime, timedelta

from modules.database import db
from modules.voice   import voice
from modules.tasks.task_manager import MISSED_MESSAGES, _next_message

logger = logging.getLogger(__name__)

# Minutes before due time to send a reminder voice alert
REMINDER_ADVANCE_MINUTES = 10

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning("APScheduler not installed. Scheduler disabled.")


class TaskScheduler:
    """Singleton background scheduler."""

    _instance  = None
    _lock      = threading.Lock()
    _reminded  = set()   # track task IDs already reminded to avoid spam

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._scheduler = None
                cls._instance._started   = False
        return cls._instance

    def start(self) -> None:
        if self._started or not APSCHEDULER_AVAILABLE:
            return
        self._scheduler = BackgroundScheduler(daemon=True)
        self._scheduler.add_job(
            self._check_tasks, "interval", seconds=60, id="task_check",
            next_run_time=datetime.now()   # run immediately on start too
        )
        self._scheduler.start()
        self._started = True
        logger.info("TaskScheduler started.")

    def stop(self) -> None:
        if self._scheduler and self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False

    def _check_tasks(self) -> None:
        """Core job: mark overdue tasks missed + fire reminders."""
        now = datetime.now()
        reminder_threshold = (now + timedelta(minutes=REMINDER_ADVANCE_MINUTES)).isoformat(
            timespec="seconds"
        )
        conn_tasks = db.get_pending_due_tasks()   # already overdue

        for task in conn_tasks:
            db.mark_missed(task["id"])
            msg = _next_message(MISSED_MESSAGES, "missed")
            logger.info("Task #%d marked MISSED. Speaking: %s", task["id"], msg)
            voice.speak(msg)

        # Reminder: tasks due within REMINDER_ADVANCE_MINUTES but not yet due
        import sqlite3
        from pathlib import Path
        from modules.database.db import DB_PATH, get_connection

        try:
            conn = get_connection()
            upcoming = conn.execute(
                """SELECT * FROM tasks
                   WHERE status='pending'
                     AND due_at IS NOT NULL
                     AND due_at >  ?
                     AND due_at <= ?""",
                (now.isoformat(timespec="seconds"), reminder_threshold)
            ).fetchall()
            conn.close()

            for row in upcoming:
                task_id = row["id"]
                if task_id not in self._reminded:
                    self._reminded.add(task_id)
                    reminder_text = (
                        f"Reminder: '{row['name']}' is due in "
                        f"{REMINDER_ADVANCE_MINUTES} minutes. Get on it!"
                    )
                    logger.info("Firing reminder for task #%d", task_id)
                    voice.speak(reminder_text)
        except Exception as exc:
            logger.error("Scheduler reminder check failed: %s", exc)


# Module-level singleton
_scheduler = TaskScheduler()


def start_scheduler() -> None:
    """Start the background scheduler (safe to call multiple times)."""
    _scheduler.start()


def stop_scheduler() -> None:
    _scheduler.stop()
