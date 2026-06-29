"""
ARIS Goal & Habit Tracker
- Define goals with target dates and metrics
- Log daily habit completions
- Track streaks, progress, and accountability
- Stored in SQLite (backend/aris.db)
"""

import os
import sqlite3
from datetime import datetime, date, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(os.path.dirname(BASE_DIR), "aris.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_tables():
    """Create habits tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS habits (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            description TEXT    DEFAULT '',
            target      TEXT    DEFAULT '',
            frequency   TEXT    DEFAULT 'daily',
            created_at  TEXT    NOT NULL,
            active      INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS habit_logs (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id  INTEGER NOT NULL,
            log_date  TEXT    NOT NULL,
            notes     TEXT    DEFAULT '',
            logged_at TEXT    NOT NULL,
            FOREIGN KEY (habit_id) REFERENCES habits(id),
            UNIQUE(habit_id, log_date)
        );

        CREATE TABLE IF NOT EXISTS goals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            description TEXT    DEFAULT '',
            target_date TEXT    DEFAULT '',
            metric      TEXT    DEFAULT '',
            progress    REAL    DEFAULT 0.0,
            created_at  TEXT    NOT NULL,
            completed   INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()


# Initialize tables on import
init_tables()


# ── Habit CRUD ───────────────────────────────────────────────────────────────

def create_habit(name: str, description: str = "", target: str = "", frequency: str = "daily") -> dict:
    """Create a new habit to track."""
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO habits (name, description, target, frequency, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, description, target, frequency, now)
    )
    conn.commit()
    habit_id = cur.lastrowid
    conn.close()
    return {"status": "success", "id": habit_id, "name": name}


def list_habits(active_only: bool = True) -> list:
    """List all habits."""
    conn = _get_conn()
    if active_only:
        rows = conn.execute("SELECT * FROM habits WHERE active = 1 ORDER BY created_at DESC").fetchall()
    else:
        rows = conn.execute("SELECT * FROM habits ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_habit(habit_id: int) -> dict:
    """Deactivate a habit (soft delete)."""
    conn = _get_conn()
    conn.execute("UPDATE habits SET active = 0 WHERE id = ?", (habit_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "id": habit_id}


# ── Habit Logging ────────────────────────────────────────────────────────────

def log_habit(habit_id: int, log_date: str = "", notes: str = "") -> dict:
    """Log a habit completion for a given date (defaults to today)."""
    if not log_date:
        log_date = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat()

    conn = _get_conn()
    # Check habit exists
    habit = conn.execute("SELECT * FROM habits WHERE id = ? AND active = 1", (habit_id,)).fetchone()
    if not habit:
        conn.close()
        return {"status": "error", "message": f"Habit {habit_id} not found or inactive"}

    try:
        conn.execute(
            "INSERT OR REPLACE INTO habit_logs (habit_id, log_date, notes, logged_at) VALUES (?, ?, ?, ?)",
            (habit_id, log_date, notes, now)
        )
        conn.commit()
        conn.close()
        return {"status": "success", "habit_id": habit_id, "date": log_date}
    except Exception as e:
        conn.close()
        return {"status": "error", "message": str(e)}


def get_habit_status(habit_id: int) -> dict:
    """Get habit info with today's completion status and current streak."""
    conn = _get_conn()
    habit = conn.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)).fetchone()
    if not habit:
        conn.close()
        return {"status": "error", "message": "Habit not found"}

    today = date.today().isoformat()
    today_log = conn.execute(
        "SELECT * FROM habit_logs WHERE habit_id = ? AND log_date = ?",
        (habit_id, today)
    ).fetchone()

    # Calculate streak
    streak = _calculate_streak(conn, habit_id)

    # Total completions
    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM habit_logs WHERE habit_id = ?", (habit_id,)
    ).fetchone()["cnt"]

    conn.close()
    return {
        "habit": dict(habit),
        "completed_today": today_log is not None,
        "streak": streak,
        "total_completions": total
    }


def get_all_streaks() -> list:
    """Get streak info for all active habits."""
    conn = _get_conn()
    habits = conn.execute("SELECT * FROM habits WHERE active = 1").fetchall()
    results = []
    today = date.today().isoformat()
    for h in habits:
        streak = _calculate_streak(conn, h["id"])
        today_log = conn.execute(
            "SELECT * FROM habit_logs WHERE habit_id = ? AND log_date = ?",
            (h["id"], today)
        ).fetchone()
        results.append({
            "id": h["id"],
            "name": h["name"],
            "streak": streak,
            "completed_today": today_log is not None
        })
    conn.close()
    return results


def _calculate_streak(conn, habit_id: int) -> int:
    """Calculate current consecutive day streak for a habit."""
    rows = conn.execute(
        "SELECT log_date FROM habit_logs WHERE habit_id = ? ORDER BY log_date DESC",
        (habit_id,)
    ).fetchall()

    if not rows:
        return 0

    streak = 0
    check_date = date.today()

    for row in rows:
        log_d = date.fromisoformat(row["log_date"])
        if log_d == check_date:
            streak += 1
            check_date -= timedelta(days=1)
        elif log_d == check_date - timedelta(days=1):
            # Allow checking yesterday if today isn't logged yet
            if streak == 0:
                streak += 1
                check_date = log_d - timedelta(days=1)
            else:
                break
        else:
            break

    return streak


# ── Goals CRUD ───────────────────────────────────────────────────────────────

def create_goal(name: str, description: str = "", target_date: str = "", metric: str = "") -> dict:
    """Create a new goal with optional target date and metric."""
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO goals (name, description, target_date, metric, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, description, target_date, metric, now)
    )
    conn.commit()
    goal_id = cur.lastrowid
    conn.close()
    return {"status": "success", "id": goal_id, "name": name}


def list_goals(include_completed: bool = False) -> list:
    """List all goals."""
    conn = _get_conn()
    if include_completed:
        rows = conn.execute("SELECT * FROM goals ORDER BY created_at DESC").fetchall()
    else:
        rows = conn.execute("SELECT * FROM goals WHERE completed = 0 ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_goal_progress(goal_id: int, progress: float) -> dict:
    """Update goal progress (0.0 to 100.0). Auto-completes at 100."""
    conn = _get_conn()
    completed = 1 if progress >= 100.0 else 0
    conn.execute(
        "UPDATE goals SET progress = ?, completed = ? WHERE id = ?",
        (min(progress, 100.0), completed, goal_id)
    )
    conn.commit()
    conn.close()
    return {"status": "success", "id": goal_id, "progress": min(progress, 100.0), "completed": bool(completed)}


def delete_goal(goal_id: int) -> dict:
    """Delete a goal permanently."""
    conn = _get_conn()
    conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "id": goal_id}
