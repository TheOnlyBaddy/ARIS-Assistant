"""
ARIS Meal Planning
- Suggest meals based on preferences & dietary needs (Gemini-powered)
- Plan weekly meals
- Log meals eaten with calorie estimates
- Track daily nutrition
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
    """Create meal tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS meal_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_date   TEXT    NOT NULL,
            meal_type   TEXT    NOT NULL DEFAULT 'lunch',
            name        TEXT    NOT NULL,
            calories    INTEGER DEFAULT NULL,
            notes       TEXT    DEFAULT '',
            logged_at   TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS meal_preferences (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            key         TEXT    NOT NULL UNIQUE,
            value       TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        );
    """)
    conn.commit()
    conn.close()


init_tables()

MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"]


# ── Meal Logging ─────────────────────────────────────────────────────────────

def log_meal(
    name: str,
    meal_type: str = "lunch",
    calories: int = None,
    notes: str = "",
    meal_date: str = ""
) -> dict:
    """Log a meal eaten."""
    if not meal_date:
        meal_date = date.today().isoformat()
    meal_type = meal_type.lower().strip()
    if meal_type not in MEAL_TYPES:
        meal_type = "lunch"
    now = datetime.now(timezone.utc).isoformat()

    conn = _get_conn()
    cur = conn.execute(
        """INSERT INTO meal_logs (meal_date, meal_type, name, calories, notes, logged_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (meal_date, meal_type, name, calories, notes, now)
    )
    conn.commit()
    meal_id = cur.lastrowid
    conn.close()
    return {"status": "success", "id": meal_id, "meal": name, "type": meal_type, "date": meal_date}


def get_meals_today(meal_date: str = "") -> dict:
    """Get all meals logged for a specific date."""
    if not meal_date:
        meal_date = date.today().isoformat()

    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM meal_logs WHERE meal_date = ? ORDER BY meal_type",
        (meal_date,)
    ).fetchall()
    conn.close()

    meals = [dict(r) for r in rows]
    total_cal = sum(m["calories"] for m in meals if m.get("calories"))

    return {
        "date": meal_date,
        "meals": meals,
        "total_calories": total_cal,
        "meal_count": len(meals)
    }


def get_meal_history(days: int = 7) -> list:
    """Get meal history for the past N days."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM meal_logs WHERE meal_date >= ? ORDER BY meal_date DESC, meal_type",
        (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_meal(meal_id: int) -> dict:
    """Delete a meal log entry."""
    conn = _get_conn()
    conn.execute("DELETE FROM meal_logs WHERE id = ?", (meal_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "id": meal_id}


# ── Preferences ──────────────────────────────────────────────────────────────

def set_preference(key: str, value: str) -> dict:
    """Set a meal preference (diet, allergies, cuisine, etc.)."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    conn.execute(
        """INSERT INTO meal_preferences (key, value, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?""",
        (key, value, now, value, now)
    )
    conn.commit()
    conn.close()
    return {"status": "success", "key": key, "value": value}


def get_preferences() -> dict:
    """Get all meal preferences."""
    conn = _get_conn()
    rows = conn.execute("SELECT key, value FROM meal_preferences").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


# ── AI Meal Suggestions (Gemini-powered) ─────────────────────────────────────

async def suggest_meals(meal_type: str = "", preferences: str = "") -> dict:
    """Use Gemini to suggest meals based on preferences."""
    prefs = get_preferences()

    prompt = "You are ARIS, a personal meal planning assistant. Suggest 3-5 meal options"
    if meal_type:
        prompt += f" for {meal_type}"
    prompt += ".\n\n"

    if prefs:
        prompt += "User preferences:\n"
        for k, v in prefs.items():
            prompt += f"- {k}: {v}\n"
        prompt += "\n"

    if preferences:
        prompt += f"Additional request: {preferences}\n\n"

    prompt += (
        "For each meal, provide:\n"
        "- **Name**: Meal name\n"
        "- **Calories**: Approximate calorie count\n"
        "- **Ingredients**: Key ingredients (brief)\n"
        "- **Prep Time**: Estimated prep time\n\n"
        "Use Indian cuisine as default unless specified otherwise. Keep it practical and healthy."
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
            "meal_type": meal_type or "any",
            "suggestions": response.text.strip()
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def plan_weekly_meals() -> dict:
    """Use Gemini to generate a full weekly meal plan."""
    prefs = get_preferences()

    prompt = (
        "You are ARIS, a personal meal planning assistant. Create a 7-day meal plan "
        "(Monday to Sunday) with breakfast, lunch, dinner, and one snack per day.\n\n"
    )

    if prefs:
        prompt += "User preferences:\n"
        for k, v in prefs.items():
            prompt += f"- {k}: {v}\n"
        prompt += "\n"

    prompt += (
        "Rules:\n"
        "- Use Indian cuisine as default unless preferences say otherwise\n"
        "- Keep it balanced and varied\n"
        "- Include approximate calories per meal\n"
        "- Format as a clean table or structured list\n"
        "- Keep total daily calories around 2000-2200\n"
        "- Be practical — suggest meals that are easy to prepare\n"
    )

    try:
        response = gemini_client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=2048)
            )
        )
        return {
            "status": "success",
            "plan": response.text.strip()
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
