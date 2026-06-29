"""
ARIS Health & Wellbeing Awareness
- Manual log: sleep hours, mood, energy level, water intake, exercise
- Trend analysis — Gemini spots patterns
- Burnout detection — if work sessions too long, suggests breaks
- Stored in SQLite (backend/aris.db)
"""

import os
import sqlite3
from datetime import datetime, date, timedelta, timezone
from google import genai
from google.genai import types

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(os.path.dirname(BASE_DIR), "aris.db")

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = os.getenv("PRIMARY_MODEL", "gemini-2.5-flash")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_tables():
    """Create health tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS health_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            log_date    TEXT    NOT NULL,
            sleep_hours REAL    DEFAULT NULL,
            mood        TEXT    DEFAULT NULL,
            energy      INTEGER DEFAULT NULL,
            water_litres REAL   DEFAULT NULL,
            exercise_mins INTEGER DEFAULT NULL,
            exercise_type TEXT   DEFAULT '',
            notes       TEXT    DEFAULT '',
            logged_at   TEXT    NOT NULL,
            UNIQUE(log_date)
        );

        CREATE TABLE IF NOT EXISTS work_sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT    NOT NULL,
            ended_at   TEXT    DEFAULT NULL,
            duration_mins REAL DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()


init_tables()


# ── Health Logging ───────────────────────────────────────────────────────────

def log_health(
    log_date: str = "",
    sleep_hours: float = None,
    mood: str = None,
    energy: int = None,
    water_litres: float = None,
    exercise_mins: int = None,
    exercise_type: str = "",
    notes: str = ""
) -> dict:
    """Log daily health metrics. Updates existing entry if same date."""
    if not log_date:
        log_date = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat()

    conn = _get_conn()
    existing = conn.execute("SELECT * FROM health_logs WHERE log_date = ?", (log_date,)).fetchone()

    if existing:
        # Merge: only update non-None fields
        updates = {}
        if sleep_hours is not None:
            updates["sleep_hours"] = sleep_hours
        if mood is not None:
            updates["mood"] = mood
        if energy is not None:
            updates["energy"] = energy
        if water_litres is not None:
            updates["water_litres"] = water_litres
        if exercise_mins is not None:
            updates["exercise_mins"] = exercise_mins
        if exercise_type:
            updates["exercise_type"] = exercise_type
        if notes:
            updates["notes"] = notes
        updates["logged_at"] = now

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [log_date]
        conn.execute(f"UPDATE health_logs SET {set_clause} WHERE log_date = ?", values)
        conn.commit()
        conn.close()
        return {"status": "updated", "date": log_date}
    else:
        conn.execute(
            """INSERT INTO health_logs 
               (log_date, sleep_hours, mood, energy, water_litres, exercise_mins, exercise_type, notes, logged_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (log_date, sleep_hours, mood, energy, water_litres, exercise_mins, exercise_type, notes, now)
        )
        conn.commit()
        conn.close()
        return {"status": "logged", "date": log_date}


def get_health_log(log_date: str = "") -> dict:
    """Get health log for a specific date."""
    if not log_date:
        log_date = date.today().isoformat()
    conn = _get_conn()
    row = conn.execute("SELECT * FROM health_logs WHERE log_date = ?", (log_date,)).fetchone()
    conn.close()
    if row:
        return {"status": "found", "log": dict(row)}
    return {"status": "not_found", "date": log_date}


def get_health_history(days: int = 7) -> list:
    """Get health logs for the past N days."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM health_logs WHERE log_date >= ? ORDER BY log_date DESC",
        (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Trend Analysis (Gemini-powered) ──────────────────────────────────────────

async def analyze_trends(days: int = 7) -> dict:
    """Use Gemini to analyze health trends and spot patterns."""
    history = get_health_history(days)

    if not history:
        return {"status": "no_data", "message": "No health data logged yet. Start logging to see trends!"}

    # Build data summary for Gemini
    data_text = "Health log data (most recent first):\n\n"
    for entry in history:
        data_text += f"Date: {entry['log_date']}\n"
        if entry.get("sleep_hours") is not None:
            data_text += f"  Sleep: {entry['sleep_hours']} hours\n"
        if entry.get("mood"):
            data_text += f"  Mood: {entry['mood']}\n"
        if entry.get("energy") is not None:
            data_text += f"  Energy: {entry['energy']}/10\n"
        if entry.get("water_litres") is not None:
            data_text += f"  Water: {entry['water_litres']} litres\n"
        if entry.get("exercise_mins") is not None:
            data_text += f"  Exercise: {entry['exercise_mins']} mins"
            if entry.get("exercise_type"):
                data_text += f" ({entry['exercise_type']})"
            data_text += "\n"
        if entry.get("notes"):
            data_text += f"  Notes: {entry['notes']}\n"
        data_text += "\n"

    prompt = (
        "You are ARIS, a personal AI health assistant. Analyze this health data and provide:\n\n"
        f"{data_text}\n"
        "1. **Patterns**: What patterns or correlations do you see? (e.g., sleep affects mood)\n"
        "2. **Strengths**: What's going well?\n"
        "3. **Concerns**: Any red flags or areas to improve?\n"
        "4. **Tip**: One actionable suggestion for tomorrow\n\n"
        "Keep your response concise (under 200 words), warm, and encouraging. Use bullet points."
    )

    try:
        response = gemini_client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=1024)
            )
        )
        return {
            "status": "success",
            "days_analyzed": len(history),
            "analysis": response.text.strip()
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def get_health_summary() -> dict:
    """Quick summary: today's status + recent averages."""
    today_log = get_health_log()
    history = get_health_history(7)

    # Compute averages
    sleep_vals = [h["sleep_hours"] for h in history if h.get("sleep_hours") is not None]
    energy_vals = [h["energy"] for h in history if h.get("energy") is not None]
    water_vals = [h["water_litres"] for h in history if h.get("water_litres") is not None]
    exercise_vals = [h["exercise_mins"] for h in history if h.get("exercise_mins") is not None]

    avg = lambda vals: round(sum(vals) / len(vals), 1) if vals else None

    return {
        "today": today_log.get("log") if today_log["status"] == "found" else None,
        "week_averages": {
            "sleep_hours": avg(sleep_vals),
            "energy": avg(energy_vals),
            "water_litres": avg(water_vals),
            "exercise_mins": avg(exercise_vals)
        },
        "days_logged": len(history),
        "total_days_in_range": 7
    }
